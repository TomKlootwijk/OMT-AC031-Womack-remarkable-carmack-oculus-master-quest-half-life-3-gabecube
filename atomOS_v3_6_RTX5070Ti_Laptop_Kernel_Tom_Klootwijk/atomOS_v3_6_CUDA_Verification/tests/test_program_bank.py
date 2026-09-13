"""Semantic learning and packed-bank regressions, independent scalar assertions."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import program_bank as p


class DistillationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = p.builtin_examples("test-program-bank")
        cls.packages, cls.receipt = p.distill(cls.data, "test-program-bank")

    def test_learns_then_generalizes_to_every_withheld_input(self):
        self.assertEqual(self.receipt["status"], "passed")
        self.assertEqual(len(self.packages), 3)
        for result in self.receipt["skills"]:
            self.assertEqual(result["search"]["status"], "frozen")
            self.assertGreater(result["search"]["duplicate_behaviors_skipped"], 0)
            self.assertGreater(result["search"]["evaluated_candidates"], 100)
            for split, count in (("train", 40), ("holdout", 24), ("full_domain", 64)):
                self.assertEqual(result["audits"][split]["status"], "passed")
                self.assertEqual(result["audits"][split]["rows"], count)
        # Direct independent application meanings, not just expression self-consistency.
        for x in range(64):
            expected = [int(bool(x & 1) and bool(x & 6)),
                        int(bool(x & 1) and not bool(x & 2)),
                        (bool(x & 1) + bool(x & 2) + bool(x & 4)) % 2]
            self.assertEqual([p.evaluate_circuit(q["circuit"], x) for q in self.packages], expected)

    def test_seed_reproduces_exact_frozen_results(self):
        packages, receipt = p.distill(self.data, "test-program-bank")
        self.assertEqual(packages, self.packages)
        self.assertEqual(receipt, self.receipt)

    def test_holdout_labels_cannot_change_candidate_and_failure_is_rejected(self):
        data = {"schema": p.SCHEMA, "input_bits": 2, "output_bits": 1,
                "skills": [{"name": "external_policy", "train": [{"input": 0, "output": 0},
                    {"input": 1, "output": 1}, {"input": 2, "output": 0}],
                    "holdout": [{"input": 3, "output": 1}]}]}
        accepted, a = p.distill(data, "external", max_operators=1)
        changed = copy.deepcopy(data)
        changed["skills"][0]["holdout"][0]["output"] = 0
        rejected, b = p.distill(changed, "external", max_operators=1)
        self.assertEqual(a["skills"][0]["search"], b["skills"][0]["search"])
        self.assertEqual(a["skills"][0]["expressions"], b["skills"][0]["expressions"])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(rejected, [])
        self.assertEqual(b["status"], "incomplete")
        self.assertEqual(b["skills"][0]["audits"]["holdout"]["status"], "failed")

    def test_budget_and_missing_audits_are_explicit(self):
        records, receipt = p.synthesize([{ "input": x, "output": x.bit_count() % 2} for x in range(8)],
                                         3, 1, p.seed_digest("budget"), candidate_budget=1)
        self.assertIsNone(records)
        self.assertTrue(receipt["budget_exhausted"])
        self.assertEqual(receipt["evaluated_candidates"], 1)
        data = {"schema": p.SCHEMA, "input_bits": 1, "output_bits": 1,
                "skills": [{"name": "identity", "train": [{"input": 0, "output": 0}, {"input": 1, "output": 1}]}]}
        packages, receipt = p.distill(data, "no-audit")
        self.assertEqual(len(packages), 1)
        self.assertEqual(receipt["skills"][0]["audits"]["holdout"]["status"], "not_run")
        self.assertEqual(receipt["skills"][0]["audits"]["full_domain"]["status"], "not_run")

    def test_external_multiple_output_examples(self):
        data = {"schema": p.SCHEMA, "input_bits": 3, "output_bits": 2,
                "skills": [{"name": "route_and_invert", "train": [{"input": x, "output": (x & 1) | ((1 - ((x >> 1) & 1)) << 1)} for x in range(8)]}]}
        packages, receipt = p.distill(data, "multi", max_operators=1)
        self.assertEqual(receipt["status"], "passed")
        for x in range(8):
            self.assertEqual(p.evaluate_circuit(packages[0]["circuit"], x), (x & 1) | ((1 - ((x >> 1) & 1)) << 1))

    def test_nor_lowering_cancels_double_negation_and_dead_gates(self):
        expression = ["and", ["input", 0], ["not", ["input", 1]]]
        circuit = p.compile_nor([expression], 2)
        self.assertEqual(len(circuit["gates"]), 2)
        for x in range(4):
            self.assertEqual(p.evaluate_circuit(circuit, x), int(bool(x & 1) and not bool(x & 2)))
        identity = p.compile_nor([["not", ["not", ["input", 0]]]], 1)
        self.assertEqual(identity["gates"], [])
        self.assertEqual(identity["outputs"], [0])

    def test_reject_bad_teacher_data(self):
        data = copy.deepcopy(self.data)
        data["skills"][0]["holdout"].append(data["skills"][0]["train"][0])
        with self.assertRaisesRegex(ValueError, "disjoint"):
            p.validate_examples(data)
        data = copy.deepcopy(self.data)
        data["skills"][0]["train"][0]["output"] = True
        with self.assertRaises(ValueError):
            p.validate_examples(data)


class PackedBankTests(unittest.TestCase):
    def setUp(self):
        self.circuit = p.compile_nor([["xor", ["input", 0], ["input", 1]]], 2)
        self.capsule = {"name": "xor", "seed_hex": "e7" * 32, "circuit": self.circuit}

    def test_seed_halves_and_klein_are_bijective_with_reflected_seam(self):
        self.assertEqual(p.seed_origin("0" * 64, 8, 256), (0, 0))
        self.assertEqual(p.seed_origin("f" * 64, 8, 256), (7, 255))
        coords = [p.klein_cell(bit, 2, 255, 8, 256) for bit in range(2048)]
        self.assertEqual(len(set(coords)), 2048)
        self.assertEqual(coords[0], (2, 255))
        self.assertEqual(coords[1], (5, 0))
        self.assertEqual(coords[256], (3, 255))

    def test_roundtrip_all_inputs_and_full_hash_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bank.bin"
            manifest = p.write_bank(path, [self.capsule, self.capsule], master_seed_hex="17" * 32)
            bank = p.load_bank(path)
            self.assertTrue(bank["manifest_verified"])
            self.assertEqual(manifest["capsules"][0]["parent_sha256"], "0" * 64)
            self.assertEqual(manifest["capsules"][1]["parent_sha256"], manifest["capsules"][0]["content_sha256"])
            self.assertEqual(bank["capsules"][0]["next_slot"], 1)
            self.assertEqual(bank["capsules"][1]["next_slot"], 0)
            for capsule in bank["capsules"]:
                for x in range(4):
                    self.assertEqual(p.evaluate_circuit(capsule["circuit"], x), int(bool(x & 1) != bool(x & 2)))
            with self.assertRaisesRegex(ValueError, "overwrite"):
                p.write_bank(path, [self.capsule], master_seed_hex="17" * 32)

    def flip_logical(self, words, bit, descriptor):
        result = list(words)
        r, a = p.klein_cell(bit, descriptor["origin_row"], descriptor["origin_angle"], 8, 256)
        result[r * 8 + a // 32] ^= 1 << (a % 32)
        return result

    def test_reject_tail_reference_origin_and_reserved_field(self):
        words, d = p.encode_capsule(self.capsule, rows=8, angles=256, program_id=0, capsule_count=1)
        def decode(w, row=d["origin_row"], angle=d["origin_angle"]):
            return p.decode_capsule(w, rows=8, angles=256, origin_row=row, origin_angle=angle, capsule_count=1)
        with self.assertRaisesRegex(ValueError, "tail"):
            decode(self.flip_logical(words, d["bit_length"], d))
        with self.assertRaisesRegex(ValueError, "reserved"):
            decode(self.flip_logical(words, 11 * 32, d))
        # First reference currently input0 (zero). Set it to future wire4.
        with self.assertRaisesRegex(ValueError, "gate wire"):
            decode(self.flip_logical(words, 1026, d))
        with self.assertRaises(ValueError):
            decode(words, row=(d["origin_row"] + 1) % 8)

    def test_manifest_content_digest_and_bank_extent_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bank.bin"
            manifest = p.write_bank(path, [self.capsule], master_seed_hex="28" * 32)
            manifest["capsules"][0]["content_sha256"] = "0" * 64
            (path.parent / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content_sha256"):
                p.load_bank(path)
            raw = path.read_bytes() + b"\0"
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "byte count"):
                p.load_bank(path)

    def test_self_amendment_preserves_function_and_links_previous_content(self):
        with tempfile.TemporaryDirectory() as temp:
            before_path, after_path = Path(temp) / "before" / "bank.bin", Path(temp) / "after" / "bank.bin"
            p.write_bank(before_path, [self.capsule, self.capsule], master_seed_hex="42" * 32)
            before = p.load_bank(before_path)
            amended = copy.deepcopy(before["capsules"])
            amended[0]["version"] += 1
            amended[0]["parent_sha256"] = amended[0]["content_sha256"]
            amended[0]["next_slot"] = 0
            p.write_bank(after_path, amended, master_seed_hex=before["master_seed_hex"])
            after = p.load_bank(after_path)
            self.assertNotEqual(before["capsules"][0]["content_sha256"], after["capsules"][0]["content_sha256"])
            self.assertEqual(after["capsules"][0]["parent_sha256"], before["capsules"][0]["content_sha256"])
            self.assertEqual(after["capsules"][0]["circuit"], before["capsules"][0]["circuit"])
            self.assertEqual(after["capsules"][1]["content_sha256"], before["capsules"][1]["content_sha256"])

    def test_native_wire_and_padded_shape_limits(self):
        many = copy.deepcopy(self.capsule)
        many["circuit"] = {"input_bits": 2, "output_bits": 1, "constant_zero_wire": 2,
                           "gates": [[0, 0]] * 1022, "outputs": [0]}
        with self.assertRaisesRegex(ValueError, "1024-wire"):
            p.encode_capsule(many, rows=32, angles=1024, program_id=0, capsule_count=1)
        with self.assertRaisesRegex(ValueError, "shape"):
            p.encode_capsule(self.capsule, rows=60000, angles=544, program_id=0, capsule_count=1)


if __name__ == "__main__":
    unittest.main()
