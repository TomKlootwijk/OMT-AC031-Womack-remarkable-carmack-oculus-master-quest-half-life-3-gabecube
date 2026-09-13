"""Counterexamples for exact novelty, oracle checks and immutable admission."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import knowledge_admission as admission
import program_bank as codec
import program_bank_reference as reference


def oracle(identity, inputs, outputs, function):
    return {"id": identity, "kind": "fixed-domain-oracle", "independent_of_candidate": True,
            "input_bits": inputs, "output_bits": outputs,
            "source": {"kind": "synthetic-independent-specification", "reference": identity},
            "cases": [{"input": x, "output": function(x)} for x in range(1 << inputs)]}


def proposal(name, circuit, oracle_id, seed="proposal"):
    return {"name": name, "oracle_id": oracle_id,
            "capsule": {"seed_hex": codec.seed_digest(seed), "circuit": circuit}}


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.base = self.directory / "base" / "bank.bin"
        self.identity = codec.compile_nor([["input", 0]], 2)
        codec.write_bank(self.base, [{"name": "identity", "seed_hex": codec.seed_digest("base"),
                                     "circuit": self.identity}], master_seed_hex=codec.seed_digest("master"))
        self.xor = codec.compile_nor([["xor", ["input", 0], ["input", 1]]], 2)
        self.xor_oracle = oracle("xor", 2, 1, lambda x: int(bool(x & 1) != bool(x & 2)))
        self.request = {"schema": admission.SCHEMA, "oracles": [self.xor_oracle],
                        "candidates": [proposal("xor", self.xor, "xor")]}

    def run_admission(self, request=None, name="accepted", base=None):
        return admission.admit_candidates(base or self.base, request or self.request, self.directory / name)

    def test_accepts_exact_novel_xor_and_preserves_existing_pages_links_and_seed(self):
        original = self.base.read_bytes()
        old = codec.load_bank(self.base)
        receipt = self.run_admission()
        result = self.directory / "accepted" / "bank.bin"
        self.assertEqual(receipt["accepted_capsules"], 1)
        self.assertEqual(receipt["status"], "prepared")
        self.assertEqual(self.base.read_bytes(), original)
        self.assertEqual(result.read_bytes()[56:len(original)], original[56:])
        bank = codec.load_bank(result)
        self.assertEqual(bank["master_seed_hex"], old["master_seed_hex"])
        self.assertEqual(bank["capsules"][0]["next_slot"], old["capsules"][0]["next_slot"])
        self.assertEqual(bank["capsules"][1]["next_slot"], 1)  # Valid self-reference, not rejected as a cycle.
        self.assertEqual(bank["capsules"][1]["seed_hex"], codec.seed_digest("proposal"))
        verified = reference.decode_bank(result, result.parent / "manifest.json")
        self.assertEqual([reference.evaluate(verified["capsules"][1], x) for x in range(4)], [0, 1, 1, 0])
        self.assertEqual(receipt["gpu_execution"], "not_run")
        self.assertFalse(receipt["new_active_bank_published"])

    def test_seed_version_name_and_routing_changes_do_not_admit_duplicate(self):
        old = copy.deepcopy(codec.load_bank(self.base)["capsules"][0])
        old.update(seed_hex=codec.seed_digest("different"), version=999, next_slot=1,
                   parent_sha256="ab" * 32, name="renamed")
        request = {"schema": admission.SCHEMA, "oracles": [oracle("identity", 2, 1, lambda x: x & 1)],
                   "candidates": [{"name": "new label", "oracle_id": "identity", "capsule": old}]}
        receipt = self.run_admission(request)
        self.assertEqual(receipt["accepted_capsules"], 0)
        self.assertEqual(receipt["decisions"][0]["reason"], "duplicate_semantics")
        self.assertFalse((self.directory / "accepted" / "bank.bin").exists())

    def test_different_live_nor_circuit_with_equal_function_is_rejected(self):
        equivalent = {"input_bits": 2, "output_bits": 1, "constant_zero_wire": 2,
                      "gates": [[0, 0], [3, 3]], "outputs": [4]}
        self.assertNotEqual(equivalent, self.identity)
        request = {"schema": admission.SCHEMA, "oracles": [oracle("identity", 2, 1, lambda x: x & 1)],
                   "candidates": [proposal("double negation", equivalent, "identity")]}
        self.assertEqual(self.run_admission(request)["decisions"][0]["reason"], "duplicate_semantics")

    def test_repeating_with_new_seeds_never_grows_the_program_bank(self):
        self.run_admission()
        request = copy.deepcopy(self.request)
        request["candidates"] *= 32
        for index in range(32):
            request["candidates"][index] = copy.deepcopy(request["candidates"][index])
            request["candidates"][index]["capsule"]["seed_hex"] = codec.seed_digest(str(index))
        receipt = self.run_admission(request, "repeat", self.directory / "accepted" / "bank.bin")
        self.assertEqual((receipt["status"], receipt["accepted_capsules"], receipt["result_capsules"]), ("no_growth", 0, 2))
        self.assertEqual({d["reason"] for d in receipt["decisions"]}, {"duplicate_semantics"})
        self.assertFalse((self.directory / "repeat" / "bank.bin").exists())

    def test_semantics_ignore_chart_shape_seed_origins_and_page_bytes(self):
        signatures = []
        contents = []
        for index, (rows, angles) in enumerate(((8, 256), (2, 1024), (9, 128), (17, 288))):
            path = self.directory / f"shape{index}" / "bank.bin"
            codec.write_bank(path, [{"circuit": self.xor, "seed_hex": codec.seed_digest(str(index))}],
                             master_seed_hex=codec.seed_digest("master"), rows=rows, angles=angles)
            capsule = codec.load_bank(path)["capsules"][0]
            signatures.append(admission.semantic_signature(capsule["circuit"]))
            contents.append(capsule["content_sha256"])
            receipt = self.run_admission(name=f"reject{index}", base=path)
            self.assertEqual(receipt["accepted_capsules"], 0)
        self.assertEqual(len(set(signatures)), 1)
        self.assertEqual(len(set(contents)), 4)

    def test_whole_domain_oracle_catches_last_input_counterexample(self):
        request = copy.deepcopy(self.request)
        request["oracles"][0]["cases"][-1]["output"] = 1
        receipt = self.run_admission(request)
        decision = receipt["decisions"][0]
        self.assertEqual(decision["reason"], "oracle_mismatch")
        self.assertEqual(decision["counterexample"], {"input": 3, "expected": 1, "actual": 0})

    def test_missing_partial_duplicate_and_undeclared_oracles_reject(self):
        mutations = [lambda q: q["candidates"][0].update(oracle_id="missing"),
                     lambda q: q["oracles"][0]["cases"].pop(),
                     lambda q: q["oracles"][0]["cases"].__setitem__(3, {"input": 0, "output": 0}),
                     lambda q: q["oracles"][0].update(independent_of_candidate=False),
                     lambda q: q["oracles"][0]["cases"][0].update(input=False)]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                request = copy.deepcopy(self.request)
                mutation(request)
                receipt = self.run_admission(request, f"oracle{index}")
                self.assertEqual(receipt["accepted_capsules"], 0)
                self.assertEqual(receipt["decisions"][0]["reason"], "missing_or_invalid_oracle")

    def test_unsupported_stateful_cyclic_wire_and_oversized_wire_candidates_reject(self):
        variants = []
        stateful = copy.deepcopy(self.request)
        stateful["candidates"][0]["kind"] = "stateful-policy"
        variants.append(stateful)
        cyclic = copy.deepcopy(self.request)
        cyclic["candidates"][0]["capsule"]["circuit"]["gates"][0] = [3, 0]
        variants.append(cyclic)
        large = copy.deepcopy(self.request)
        large["candidates"][0]["capsule"]["circuit"]["gates"] = [[0, 0]] * 1022
        variants.append(large)
        for index, request in enumerate(variants):
            receipt = self.run_admission(request, f"unsupported{index}")
            self.assertEqual(receipt["accepted_capsules"], 0)
            self.assertEqual(receipt["decisions"][0]["reason"], "invalid_or_unsupported_candidate")

    def test_interface_is_part_of_semantics_and_maximum_domain_is_exact(self):
        wide = {"input_bits": 12, "output_bits": 8, "constant_zero_wire": 12,
                "gates": [], "outputs": list(range(8))}
        request = {"schema": admission.SCHEMA,
                   "oracles": [oracle("low_byte", 12, 8, lambda x: x & 255)],
                   "candidates": [proposal("low byte", wide, "low_byte")]}
        receipt = self.run_admission(request)
        self.assertEqual(receipt["decisions"][0]["verified_cases"], 4096)
        self.assertEqual(receipt["accepted_capsules"], 1)
        two = codec.compile_nor([["input", 0]], 2)
        three = codec.compile_nor([["input", 0]], 3)
        self.assertNotEqual(admission.semantic_signature(two), admission.semantic_signature(three))

    def test_hash_collision_cannot_impersonate_semantic_equality(self):
        request = copy.deepcopy(self.request)
        and_circuit = codec.compile_nor([["and", ["input", 0], ["input", 1]]], 2)
        request["oracles"].append(oracle("and", 2, 1, lambda x: int((x & 3) == 3)))
        request["candidates"].append(proposal("and", and_circuit, "and", "and"))
        with mock.patch.object(admission, "_sha", return_value="00" * 32):
            receipt = self.run_admission(request)
        self.assertEqual(receipt["accepted_capsules"], 2)
        self.assertEqual(receipt["result_unique_functions"], 3)

    def test_bounds_fail_before_publication_and_do_not_silently_truncate(self):
        request = copy.deepcopy(self.request)
        request["candidates"] *= 2
        with self.assertRaisesRegex(ValueError, "candidate count"):
            admission.admit_candidates(self.base, request, self.directory / "bounded", candidate_limit=1)
        self.assertFalse((self.directory / "bounded").exists())
        with mock.patch.object(admission, "MAX_BOOLEAN_WORK", 1):
            with self.assertRaisesRegex(ValueError, "verification work"):
                self.run_admission(name="work_bound")
        self.assertFalse((self.directory / "work_bound").exists())

    def test_existing_output_is_never_overwritten(self):
        out = self.directory / "accepted"
        out.mkdir()
        (out / "keep").write_bytes(b"retained")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.run_admission()
        self.assertEqual((out / "keep").read_bytes(), b"retained")

    def test_changed_base_prevents_publishing_prepared_result(self):
        writer = codec.write_bank
        original = self.base.read_bytes()
        def mutate_after_write(*args, **kwargs):
            result = writer(*args, **kwargs)
            self.base.write_bytes(original + b"changed")
            return result
        with mock.patch.object(codec, "write_bank", side_effect=mutate_after_write):
            with self.assertRaisesRegex(ValueError, "changed during admission"):
                self.run_admission()
        self.assertFalse((self.directory / "accepted").exists())

    def test_corrupted_encoded_output_is_not_published(self):
        writer = codec.write_bank
        def corrupt_after_write(path, *args, **kwargs):
            result = writer(path, *args, **kwargs)
            raw = bytearray(Path(path).read_bytes())
            raw[-1] ^= 1
            Path(path).write_bytes(raw)
            return result
        with mock.patch.object(codec, "write_bank", side_effect=corrupt_after_write):
            with self.assertRaises(ValueError):
                self.run_admission()
        self.assertFalse((self.directory / "accepted").exists())

    def test_source_provenance_is_retained_without_truth_or_gpu_claim(self):
        receipt = self.run_admission()
        manifest = json.loads((self.directory / "accepted" / "manifest.json").read_text())
        provenance = manifest["capsules"][1]["knowledge_admission"]
        self.assertEqual(provenance["source"], self.xor_oracle["source"])
        self.assertIn("not authenticated", provenance["scope"])
        self.assertIn("declared, not authenticated", receipt["knowledge_scope"])

    def test_old_capsule_names_and_all_prior_metadata_survive_exactly(self):
        manifest_path = self.base.parent / "manifest.json"
        original = json.loads(manifest_path.read_text())
        original["custom_bank_note"] = "retained input configuration"
        original["capsules"][0]["name"] = "Human meaningful identity name"
        original["capsules"][0]["custom_provenance"] = {"source": "retained evidence", "revision": 7}
        manifest_path.write_text(json.dumps(original), encoding="utf-8")
        self.run_admission()
        after = json.loads((self.directory / "accepted" / "manifest.json").read_text())
        self.assertEqual(after["capsules"][:1], original["capsules"])
        self.assertEqual(after["custom_bank_note"], original["custom_bank_note"])

    def test_cli_demonstrates_real_learned_bank_append_and_repeat_without_growth(self):
        base = ROOT / "examples" / "program_bank" / "learned_v1" / "bank.bin"
        cli = ROOT / "tools" / "admit_program_knowledge.py"
        candidates = self.directory / "demo.json"
        commands = [
            [sys.executable, str(cli), "--base-bank", str(base), "--make-demo-candidates", str(candidates)],
            [sys.executable, str(cli), "--base-bank", str(base), "--candidates", str(candidates), "--out", str(self.directory / "demo")],
            [sys.executable, str(cli), "--base-bank", str(self.directory / "demo" / "bank.bin"), "--candidates", str(candidates), "--out", str(self.directory / "demo_repeat")],
        ]
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads((self.directory / "demo" / "admission.json").read_text())
        self.assertEqual((receipt["accepted_capsules"], receipt["rejected_candidates"]), (1, 4))
        self.assertEqual([d["reason"] for d in receipt["decisions"]], ["duplicate_semantics", "duplicate_semantics",
                         "oracle_mismatch", "verified_novel_function", "duplicate_semantics"])
        before = json.loads((base.parent / "manifest.json").read_text())
        after = json.loads((self.directory / "demo" / "manifest.json").read_text())
        self.assertEqual(after["capsules"][:3], before["capsules"])
        self.assertEqual(after["capsules"][3]["next_slot"], 0)
        repeat = json.loads((self.directory / "demo_repeat" / "admission.json").read_text())
        self.assertEqual((repeat["status"], repeat["result_capsules"]), ("no_growth", 4))
        self.assertFalse((self.directory / "demo_repeat" / "bank.bin").exists())


if __name__ == "__main__":
    unittest.main()
