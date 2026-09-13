"""Synthetic grammar fixtures only; no test fixture represents a model run."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import knowledge_admission as admission
import program_bank as codec
import teacher_knowledge as teacher


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def node(op, *arguments):
    return [op, *arguments]


def fixture_expressions(profile_id):
    """Hand-authored test algorithms, explicitly not extracted teacher outputs."""
    a0, a1, b0, b1, select = [node("input", bit) for bit in range(5)]
    xor0 = node("xor", a0, b0)
    xor1 = node("xor", a1, b1)
    if profile_id == "full_adder_1bit_v1":
        a, b, carry = a0, a1, b0
        ab = node("xor", a, b)
        return [node("xor", ab, carry), node("or", node("and", a, b), node("and", carry, ab))]
    if profile_id == "unsigned_compare_2bit_v1":
        eq1 = node("not", xor1)
        less = node("or", node("and", node("not", a1), b1),
                    node("and", eq1, node("and", node("not", a0), b0)))
        more = node("or", node("and", a1, node("not", b1)),
                    node("and", eq1, node("and", a0, node("not", b0))))
        return [less, node("and", node("not", xor0), eq1), more]
    if profile_id == "unsigned_add_2bit_v1":
        carry0 = node("and", a0, b0)
        return [xor0, node("xor", xor1, carry0),
                node("or", node("and", a1, b1), node("and", xor1, carry0))]
    if profile_id == "binary_to_gray_4bit_v1":
        return [node("xor", node("input", i), node("input", i + 1)) for i in range(3)] + [node("input", 3)]
    if profile_id == "absolute_difference_2bit_v1":
        high = node("and", xor1, node("or", node("and", a1, node("or", a0, node("not", b0))),
                                            node("and", b1, node("or", b0, node("not", a0)))))
        return [xor0, high]
    if profile_id == "mux_2bit_v1":
        return [node("or", node("and", a, node("not", select)), node("and", b, select))
                for a, b in ((a0, b0), (a1, b1))]
    raise AssertionError("unknown synthetic fixture")


def response_object(profile_id, outputs=None):
    profile = next(p for p in teacher.profiles() if p["profile_id"] == profile_id)
    return {"schema": teacher.RESPONSE_SCHEMA, "profile_id": profile_id,
            "procedures": [{"name": profile_id, "input_bits": profile["input_bits"],
                            "output_bits": profile["output_bits"],
                            "outputs": fixture_expressions(profile_id) if outputs is None else outputs}]}


class TeacherKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic_teacher_adapter_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.curriculum = self.root / "curriculum"
        self.manifest = teacher.prepare_curriculum(self.curriculum)
        self.base = ROOT / "examples/program_bank/learned_v1/bank.bin"

    def retained_fixture(self, profile_id, value=None, suffix="", unknown=False):
        response = json.dumps(response_object(profile_id) if value is None else value).encode("utf-8")
        folder = self.root / (profile_id + suffix)
        folder.mkdir()
        response_path, run_path = folder / "response.json", folder / "run.json"
        response_path.write_bytes(response)
        frozen = next(p for p in self.manifest["profiles"] if p["profile_id"] == profile_id)
        provenance = {"model_repo": "synthetic-test-fixture/no-model-executed",
                      "model_revision": None if unknown else "a" * 40,
                      "model_revision_status": "unknown_cached_origin" if unknown else "pinned_huggingface_commit",
                      "model_artifact_sha256": sha(b"synthetic grammar test fixture, not model weights"),
                      "prompt_sha256": frozen["prompt_sha256"], "response_sha256": sha(response)}
        run = dict(provenance, scope="synthetic test fixture; not an actual teacher execution", suffix=suffix)
        run_bytes = json.dumps(run).encode("utf-8")
        run_path.write_bytes(run_bytes)
        provenance["run_sha256"] = sha(run_bytes)
        return {"profile_id": profile_id, "response_path": str(response_path), "run_path": str(run_path),
                "provenance": provenance}

    def test_freezes_six_complete_oracles_before_any_responses_exist(self):
        frozen = teacher.load_curriculum(self.curriculum)
        self.assertEqual(len(frozen["profiles"]), 6)
        self.assertEqual(sum(len(p["oracle"]["cases"]) for p in frozen["profiles"].values()), 104)
        for profile in frozen["profiles"].values():
            self.assertEqual([row["input"] for row in profile["oracle"]["cases"]], list(range(1 << profile["input_bits"])))
            self.assertNotIn('"cases"', profile["prompt"])
            self.assertIn("existing algorithm knowledge", profile["prompt"])
            self.assertIn("Input wire indices", profile["prompt"])
        with self.assertRaisesRegex(ValueError, "overwrite"):
            teacher.prepare_curriculum(self.curriculum)

    def test_integer_oracles_match_known_edge_cases_and_gray_adjacency(self):
        self.assertEqual(teacher.scalar_oracle("full_adder_1bit_v1", 7), 3)
        self.assertEqual(teacher.scalar_oracle("unsigned_add_2bit_v1", 15), 6)
        self.assertEqual(teacher.scalar_oracle("unsigned_compare_2bit_v1", 0), 2)
        self.assertEqual(teacher.scalar_oracle("unsigned_compare_2bit_v1", 3), 4)
        self.assertEqual(teacher.scalar_oracle("unsigned_compare_2bit_v1", 12), 1)
        self.assertEqual(teacher.scalar_oracle("absolute_difference_2bit_v1", 3), 3)
        self.assertEqual(teacher.scalar_oracle("absolute_difference_2bit_v1", 12), 3)
        self.assertEqual(teacher.scalar_oracle("absolute_difference_2bit_v1", 10), 0)
        gray = [teacher.scalar_oracle("binary_to_gray_4bit_v1", x) for x in range(16)]
        self.assertEqual(len(set(gray)), 16)
        self.assertTrue(all((a ^ b).bit_count() == 1 for a, b in zip(gray, gray[1:])))
        self.assertEqual(teacher.scalar_oracle("mux_2bit_v1", 3 | (2 << 2)), 3)
        self.assertEqual(teacher.scalar_oracle("mux_2bit_v1", 3 | (2 << 2) | 16), 2)

    def test_all_synthetic_algorithm_fixtures_compile_and_match_frozen_oracles(self):
        responses = [self.retained_fixture(p["profile_id"]) for p in teacher.profiles()]
        request, receipt = teacher.build_teacher_request(self.curriculum, responses)
        self.assertEqual(receipt["compiled_candidates"], 6)
        self.assertEqual(receipt["rejected_responses"], 0)
        result = admission.admit_candidates(self.base, request, self.root / "proposed")
        self.assertEqual(result["accepted_capsules"], 6)
        self.assertEqual(sum(d["verified_cases"] for d in result["decisions"]), 104)
        bank = codec.load_bank(self.root / "proposed/bank.bin")
        self.assertTrue(all(c["next_slot"] == 0 for c in bank["capsules"][3:]))
        self.assertTrue(all(len(c["seed_hex"]) == 64 for c in bank["capsules"][3:]))
        self.assertFalse(result["new_active_bank_published"])
        self.assertEqual(result["gpu_execution"], "not_run")

    def test_actual_expression_not_oracle_table_determines_compiled_candidate(self):
        identity = "full_adder_1bit_v1"
        wrong = response_object(identity, [["constant", 0], ["constant", 0]])
        request, adapted = teacher.build_teacher_request(self.curriculum, [self.retained_fixture(identity, wrong)])
        self.assertEqual(adapted["compiled_candidates"], 1)
        self.assertEqual(request["candidates"][0]["capsule"]["circuit"]["gates"], [])
        checked = admission.admit_candidates(self.base, request, self.root / "rejected")
        self.assertEqual(checked["accepted_capsules"], 0)
        self.assertEqual(checked["decisions"][0]["reason"], "oracle_mismatch")
        self.assertEqual(checked["decisions"][0]["counterexample"], {"input": 1, "expected": 1, "actual": 0})

    def test_new_run_or_seed_does_not_make_repeated_teacher_algorithm_novel(self):
        identity = "binary_to_gray_4bit_v1"
        responses = [self.retained_fixture(identity, suffix="first"), self.retained_fixture(identity, suffix="second")]
        request, _ = teacher.build_teacher_request(self.curriculum, responses)
        self.assertNotEqual(request["candidates"][0]["capsule"]["seed_hex"], request["candidates"][1]["capsule"]["seed_hex"])
        checked = admission.admit_candidates(self.base, request, self.root / "deduplicated")
        self.assertEqual((checked["accepted_capsules"], checked["rejected_candidates"]), (1, 1))
        self.assertEqual(checked["decisions"][1]["reason"], "duplicate_semantics")

    def test_single_json_fence_is_recorded_without_prose_extraction(self):
        identity = "full_adder_1bit_v1"
        plain = json.dumps(response_object(identity))
        parsed = teacher.parse_teacher_response("```json\n" + plain + "\n```", identity)
        self.assertEqual(parsed["wrapping"], "single_json_fence")
        for text in ("Here is your answer:\n" + plain, plain + "\nExecute this now", "<think>secret</think>" + plain):
            with self.assertRaises(ValueError):
                teacher.parse_teacher_response(text, identity)

    def test_malicious_code_and_unsupported_opcodes_never_execute(self):
        identity = "full_adder_1bit_v1"
        payloads = ["__import__('os').system('echo should-not-run')", ["eval", "1+1"],
                    ["__import__", "pathlib"], ["input", "0"], ["constant", True], ["constant", 2],
                    ["input", 3], ["and", ["input", 0], ["input", 1], ["input", 2]]]
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    teacher.parse_teacher_response(json.dumps(response_object(identity, [payload, ["constant", 0]])), identity)

    def test_duplicate_keys_extra_fields_wrong_interfaces_and_nonfinite_numbers_reject(self):
        identity = "full_adder_1bit_v1"
        raw = json.dumps(response_object(identity))
        duplicate = raw.replace('"schema":', '"schema":"ignored", "schema":', 1)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            teacher.parse_teacher_response(duplicate, identity)
        variants = []
        extra = response_object(identity)
        extra["code"] = "do something"
        variants.append(extra)
        bad_profile = response_object(identity)
        bad_profile["profile_id"] = "unsigned_add_2bit_v1"
        variants.append(bad_profile)
        wrong_width = response_object(identity)
        wrong_width["procedures"][0]["input_bits"] = True
        variants.append(wrong_width)
        wrong_count = response_object(identity)
        wrong_count["procedures"][0]["outputs"].append(["constant", 0])
        variants.append(wrong_count)
        for variant in variants:
            with self.assertRaises(ValueError):
                teacher.parse_teacher_response(json.dumps(variant), identity)
        with self.assertRaises(ValueError):
            teacher.parse_teacher_response(raw.replace('"input_bits": 3', '"input_bits": NaN'), identity)

    def test_byte_json_depth_ast_depth_node_and_response_count_bounds(self):
        identity = "full_adder_1bit_v1"
        with self.assertRaisesRegex(ValueError, "byte bound"):
            teacher.parse_teacher_response(b" " * (teacher.MAX_RESPONSE_BYTES + 1), identity)
        with self.assertRaisesRegex(ValueError, "JSON nesting"):
            teacher.parse_teacher_response("[" * 100 + "]" * 100, identity)
        ast = ["input", 0]
        for _ in range(teacher.MAX_AST_DEPTH):
            ast = ["not", ast]
        with self.assertRaisesRegex(ValueError, "node/depth"):
            teacher.parse_teacher_response(json.dumps(response_object(identity, [ast, ["constant", 0]])), identity)
        ast = ["input", 0]
        for _ in range(9):
            ast = ["and", ast, ast]
        with self.assertRaisesRegex(ValueError, "node/depth"):
            teacher.parse_teacher_response(json.dumps(response_object(identity, [ast, ["constant", 0]])), identity)
        with self.assertRaisesRegex(ValueError, "response count"):
            teacher.build_teacher_request(self.curriculum, [{}] * (teacher.MAX_RESPONSES + 1))

    def test_unknown_cached_origin_is_honest_only_when_artifact_is_pinned(self):
        identity = "full_adder_1bit_v1"
        record = self.retained_fixture(identity, unknown=True)
        request, adapted = teacher.build_teacher_request(self.curriculum, [record])
        self.assertEqual(adapted["compiled_candidates"], 1)
        self.assertIsNone(request["oracles"][0]["source"]["teacher_proposal"]["model_revision"])
        broken = copy.deepcopy(record)
        del broken["provenance"]["model_artifact_sha256"]
        _, rejected = teacher.build_teacher_request(self.curriculum, [broken])
        self.assertEqual(rejected["compiled_candidates"], 0)
        invented = copy.deepcopy(record)
        invented["provenance"]["model_revision"] = "main"
        _, rejected = teacher.build_teacher_request(self.curriculum, [invented])
        self.assertEqual(rejected["compiled_candidates"], 0)

    def test_changed_response_prompt_or_run_metadata_rejects_provenance(self):
        identity = "full_adder_1bit_v1"
        for field in ("response_sha256", "prompt_sha256", "run_sha256", "model_artifact_sha256", "model_revision"):
            record = self.retained_fixture(identity, suffix=field)
            record["provenance"][field] = "b" * (40 if field == "model_revision" else 64)
            _, receipt = teacher.build_teacher_request(self.curriculum, [record])
            self.assertEqual(receipt["compiled_candidates"], 0, field)

    def test_frozen_oracle_cannot_be_changed_even_with_rehashed_manifest(self):
        record = self.manifest["profiles"][0]
        path = self.curriculum / record["oracle_file"]
        value = json.loads(path.read_bytes())
        value["cases"][0]["output"] = 1
        raw = json.dumps(value).encode("utf-8")
        path.write_bytes(raw)
        manifest = copy.deepcopy(self.manifest)
        manifest["profiles"][0]["oracle_sha256"] = sha(raw)
        (self.curriculum / "curriculum.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "independent integer specification"):
            teacher.load_curriculum(self.curriculum)

    def test_malformed_response_keeps_failure_and_does_not_make_replacement_output(self):
        record = self.retained_fixture("full_adder_1bit_v1", {"please": "execute arbitrary code"})
        request, receipt = teacher.build_teacher_request(self.curriculum, [record])
        self.assertEqual(request["candidates"], [])
        self.assertEqual(receipt["status"], "no_valid_candidates")
        self.assertIn("schema/profile", receipt["decisions"][0]["detail"])
        result = teacher.admit_teacher_knowledge(self.base, self.curriculum, [record], self.root / "never_created")
        self.assertIsNone(result["admission"])
        self.assertFalse((self.root / "never_created").exists())


if __name__ == "__main__":
    unittest.main()
