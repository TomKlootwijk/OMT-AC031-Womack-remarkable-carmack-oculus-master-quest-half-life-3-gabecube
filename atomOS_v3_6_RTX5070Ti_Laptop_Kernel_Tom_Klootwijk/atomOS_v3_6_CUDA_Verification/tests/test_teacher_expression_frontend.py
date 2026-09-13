"""Hand-authored V2 grammar fixtures only; no fixture claims model execution."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import knowledge_admission as admission
import program_bank as codec
import teacher_expression_frontend as frontend
import teacher_knowledge as original


FIXTURES = {
    "full_adder_1bit_v1": ["(a ^ b) ^ carry_in", "(a & b) | (carry_in & (a ^ b))"],
    "unsigned_compare_2bit_v1": ["(~a1 & b1) | (~(a1 ^ b1) & (~a0 & b0))",
                                 "~(a0 ^ b0) & ~(a1 ^ b1)",
                                 "(a1 & ~b1) | (~(a1 ^ b1) & (a0 & ~b0))"],
    "unsigned_add_2bit_v1": ["a0 ^ b0", "(a1 ^ b1) ^ (a0 & b0)",
                            "(a1 & b1) | ((a1 ^ b1) & (a0 & b0))"],
    "binary_to_gray_4bit_v1": ["binary0 ^ binary1", "binary1 ^ binary2", "binary2 ^ binary3", "binary3"],
    "absolute_difference_2bit_v1": ["a0 ^ b0", "(a1 ^ b1) & ((a1 & (a0 | ~b0)) | (b1 & (b0 | ~a0)))"],
    "mux_2bit_v1": ["(a0 & ~select_b) | (b0 & select_b)", "(a1 & ~select_b) | (b1 & select_b)"],
}


def response(identity, outputs=None):
    profile = next(p for p in original.profiles() if p["profile_id"] == identity)
    return {"schema": frontend.RESPONSE_SCHEMA, "profile_id": identity,
            "procedures": [{"name": identity, "input_bits": profile["input_bits"],
                            "output_bits": profile["output_bits"],
                            "outputs": list(FIXTURES[identity]) if outputs is None else outputs}]}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ExpressionFrontendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic_expression_frontend_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old, self.new = self.root / "original", self.root / "expressions"
        self.original_manifest = original.prepare_curriculum(self.old)
        self.manifest = frontend.freeze_curriculum(self.new, self.old)
        self.base = ROOT / "examples/program_bank/learned_v1/bank.bin"

    def retained(self, identity, outputs=None, suffix="", repair=None):
        folder = self.root / (identity + suffix)
        folder.mkdir()
        raw = json.dumps(response(identity, outputs)).encode("utf-8")
        (folder / "response.txt").write_bytes(raw)
        profile = next(p for p in self.manifest["profiles"] if p["profile_id"] == identity)
        prompt_hash = profile["prompt_sha256"]
        if repair is not None:
            previous = Path(repair["previous_response_path"]).read_bytes()
            prompt_hash = frontend.repair_prompt(identity, previous, repair["counterexample"], repair["round"])["prompt_sha256"]
        provenance = {"model_repo": "synthetic-fixture/no-model-run", "model_revision": "a" * 40,
                      "model_revision_status": "pinned_huggingface_commit",
                      "model_artifact_sha256": sha(b"synthetic fixture identifier"),
                      "prompt_sha256": prompt_hash, "response_sha256": sha(raw)}
        run = dict(provenance, scope="synthetic fixture only", suffix=suffix)
        if repair is not None:
            run["repair"] = copy.deepcopy(repair)
        run_raw = json.dumps(run).encode("utf-8")
        (folder / "run.json").write_bytes(run_raw)
        provenance["run_sha256"] = sha(run_raw)
        record = {"profile_id": identity, "response_path": str(folder / "response.txt"),
                  "run_path": str(folder / "run.json"), "provenance": provenance}
        if repair is not None:
            record["repair"] = copy.deepcopy(repair)
        return record

    def test_v2_freeze_preserves_every_original_oracle_byte_and_interface(self):
        loaded = frontend.load_curriculum(self.new)
        self.assertEqual(len(loaded["profiles"]), 6)
        self.assertEqual((self.new / "source_curriculum.json").read_bytes(), (self.old / "curriculum.json").read_bytes())
        for new, old in zip(self.manifest["profiles"], self.original_manifest["profiles"]):
            self.assertEqual((self.new / new["oracle_file"]).read_bytes(), (self.old / old["oracle_file"]).read_bytes())
            self.assertEqual(new["oracle_sha256"], old["oracle_sha256"])
            self.assertEqual(new["source_oracle_sha256"], old["oracle_sha256"])
            for field in ("profile_id", "input_bits", "output_bits", "input_labels", "output_labels", "specification"):
                self.assertEqual(new[field], old[field])
            self.assertNotEqual(new["prompt_sha256"], old["prompt_sha256"])
        with self.assertRaisesRegex(ValueError, "overwrite"):
            frontend.freeze_curriculum(self.new, self.old)

    def test_format_and_initial_prompt_define_only_representation(self):
        for profile in original.profiles():
            identity = profile["profile_id"]
            schema = frontend.response_format(identity)
            outputs = schema["properties"]["procedures"]["items"]["properties"]["outputs"]
            self.assertEqual(outputs["items"]["type"], "string")
            self.assertEqual(outputs["minItems"], profile["output_bits"])
            prompt = frontend.prompt(identity)
            self.assertNotIn('"cases"', prompt)
            self.assertNotIn("single_counterexample", prompt)
            self.assertIn("existing algorithm knowledge", prompt)

    def test_all_synthetic_expression_fixtures_match_all_original_cases(self):
        records = [self.retained(p["profile_id"]) for p in original.profiles()]
        request, adapted = frontend.build_request(self.new, records)
        self.assertEqual(adapted["compiled_candidates"], 6)
        result = admission.admit_candidates(self.base, request, self.root / "accepted")
        self.assertEqual(result["accepted_capsules"], 6)
        self.assertEqual(sum(d["verified_cases"] for d in result["decisions"]), 104)
        self.assertEqual(result["gpu_execution"], "not_run")
        self.assertTrue(all(c["capsule"]["next_slot"] == 0 for c in request["candidates"]))

    def test_not_and_invert_have_one_bit_semantics_without_python_execution(self):
        identity = "full_adder_1bit_v1"
        with patch("builtins.eval", side_effect=AssertionError("no evaluation")), patch("builtins.exec", side_effect=AssertionError("no execution")):
            parsed = frontend.parse_response(json.dumps(response(identity, ["~0", "not 1"])), identity)
        self.assertEqual(parsed["canonical_ast"], [["not", ["constant", 0]], ["not", ["constant", 1]]])
        self.assertEqual([codec.evaluate_circuit(parsed["circuit"], x) for x in range(8)], [1] * 8)

    def test_boolean_words_and_bit_operators_have_identical_finite_behavior(self):
        identity = "full_adder_1bit_v1"
        words = ["(a and b) or (carry_in and (not a))", "a or b or carry_in"]
        symbols = ["(a & b) | (carry_in & ~a)", "a | b | carry_in"]
        a = frontend.parse_response(json.dumps(response(identity, words)), identity)
        b = frontend.parse_response(json.dumps(response(identity, symbols)), identity)
        self.assertEqual([codec.evaluate_circuit(a["circuit"], x) for x in range(8)],
                         [codec.evaluate_circuit(b["circuit"], x) for x in range(8)])

    def test_calls_attributes_indices_arithmetic_shifts_and_control_syntax_reject(self):
        identity = "full_adder_1bit_v1"
        malicious = ["eval(a)", "__import__(a)", "a.real", "a[0]", "a+b", "a<<1", "a<b", "a if b else carry_in",
                     "lambda a: a", "(a:=1)", "[a for a in b]", "a # run hidden instructions", "sum", "True", "2"]
        for text in malicious:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    frontend.parse_response(json.dumps(response(identity, [text, "0"])), identity)

    def test_v1_tree_outputs_unknown_keys_and_duplicate_json_keys_reject(self):
        identity = "full_adder_1bit_v1"
        with self.assertRaises(ValueError):
            frontend.parse_response(json.dumps(response(identity, [["input", 0], "0"])), identity)
        extra = response(identity)
        extra["code"] = "do something"
        with self.assertRaises(ValueError):
            frontend.parse_response(json.dumps(extra), identity)
        raw = json.dumps(response(identity)).replace('"schema":', '"schema":"duplicate", "schema":', 1)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            frontend.parse_response(raw, identity)

    def test_expression_size_depth_and_global_node_count_are_bounded(self):
        identity = "full_adder_1bit_v1"
        for text in ("a" * (frontend.MAX_EXPR_BYTES + 1), "~" * (frontend.MAX_AST_DEPTH + 1) + "a"):
            with self.assertRaises(ValueError):
                frontend.parse_response(json.dumps(response(identity, [text, "0"])), identity)
        # Two individually shallow strings together exceed the procedure budget.
        term = " or ".join(["a"] * 300)
        with self.assertRaisesRegex(ValueError, "node/depth"):
            frontend.parse_response(json.dumps(response(identity, [term, term])), identity)

    def test_wrong_teacher_formula_is_not_replaced_with_the_oracle(self):
        records = [self.retained("full_adder_1bit_v1", ["0", "0"])]
        request, adapted = frontend.build_request(self.new, records)
        self.assertEqual(adapted["compiled_candidates"], 1)
        self.assertEqual(request["candidates"][0]["capsule"]["circuit"]["gates"], [])
        result = admission.admit_candidates(self.base, request, self.root / "wrong")
        self.assertEqual(result["accepted_capsules"], 0)
        self.assertEqual(result["decisions"][0]["reason"], "oracle_mismatch")

    def test_different_expression_spelling_and_seed_do_not_create_novelty(self):
        identity = "full_adder_1bit_v1"
        first = self.retained(identity, suffix="first")
        expressions = ["~~((a ^ b) ^ carry_in)", "(a and b) or (carry_in and (a ^ b))"]
        second = self.retained(identity, expressions, suffix="second")
        request, _ = frontend.build_request(self.new, [first, second])
        self.assertNotEqual(request["candidates"][0]["capsule"]["seed_hex"], request["candidates"][1]["capsule"]["seed_hex"])
        result = admission.admit_candidates(self.base, request, self.root / "duplicates")
        self.assertEqual((result["accepted_capsules"], result["rejected_candidates"]), (1, 1))

    def test_repair_contains_exactly_one_genuine_counterexample_and_caps_rounds(self):
        identity = "full_adder_1bit_v1"
        previous = json.dumps(response(identity, ["0", "0"]))
        case = {"input": 1, "expected": 1, "actual": 0}
        feedback = frontend.repair_prompt(identity, previous, case, 1)
        self.assertEqual(feedback["counterexample_count"], 1)
        self.assertEqual(feedback["counterexample"], case)
        self.assertEqual(feedback["previous_response_sha256"], sha(previous.encode("utf-8")))
        self.assertNotIn('"cases"', feedback["prompt"])
        for index in (0, 3):
            with self.assertRaises(ValueError):
                frontend.repair_prompt(identity, previous, case, index)
        for bad in ({"input": 1, "expected": 3, "actual": 0}, {"input": 1, "expected": 1, "actual": 2},
                    {"input": 0, "expected": 0, "actual": 0}):
            with self.assertRaisesRegex(ValueError, "real mismatch"):
                frontend.repair_prompt(identity, previous, bad, 1)

    def test_repair_parent_case_and_prompt_are_bound_by_retained_run(self):
        identity = "full_adder_1bit_v1"
        previous = self.retained(identity, ["0", "0"], suffix="wrong")
        repair = {"round": 1, "previous_response_path": previous["response_path"],
                  "previous_response_sha256": previous["provenance"]["response_sha256"],
                  "counterexample": {"input": 1, "expected": 1, "actual": 0}}
        record = self.retained(identity, suffix="repair", repair=repair)
        request, adapted = frontend.build_request(self.new, [record])
        self.assertEqual(adapted["compiled_candidates"], 1)
        self.assertEqual(request["oracles"][0]["source"]["repair"], repair)
        self.assertEqual(adapted["decisions"][0]["repair_round"], 1)
        tampered = copy.deepcopy(record)
        tampered["repair"]["previous_response_sha256"] = "f" * 64
        _, rejected = frontend.build_request(self.new, [tampered])
        self.assertEqual(rejected["compiled_candidates"], 0)
        # Same model/profile/round is not a route to unlimited repair attempts.
        _, repeated = frontend.build_request(self.new, [record, record, record])
        self.assertEqual((repeated["compiled_candidates"], repeated["rejected_responses"]), (1, 2))

    def test_changed_original_oracle_is_rejected_by_inherited_hash(self):
        record = self.manifest["profiles"][0]
        path = self.new / record["oracle_file"]
        value = json.loads(path.read_bytes())
        value["cases"][0]["output"] = 1
        raw = json.dumps(value).encode("utf-8")
        path.write_bytes(raw)
        manifest = copy.deepcopy(self.manifest)
        manifest["profiles"][0]["oracle_sha256"] = sha(raw)
        (self.new / "curriculum.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inherited-byte"):
            frontend.load_curriculum(self.new)

    def test_frozen_source_hashes_and_strict_manifest_json_are_enforced(self):
        path = self.new / "curriculum.json"
        original_raw = path.read_bytes()
        for field in ("frontend_source_sha256", "original_frontend_sha256"):
            value = json.loads(original_raw)
            value[field] = "f" * 64
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source changed"):
                frontend.load_curriculum(self.new)
        text = original_raw.decode("utf-8").replace('"schema":', '"schema":"duplicate", "schema":', 1)
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            frontend.load_curriculum(self.new)
        value = json.loads(original_raw)
        value["unexpected_number"] = float("nan")
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            frontend.load_curriculum(self.new)


if __name__ == "__main__":
    unittest.main()
