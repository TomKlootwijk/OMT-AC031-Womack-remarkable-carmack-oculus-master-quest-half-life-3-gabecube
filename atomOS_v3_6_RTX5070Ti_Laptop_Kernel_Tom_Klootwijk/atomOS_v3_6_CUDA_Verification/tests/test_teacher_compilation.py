"""Synthetic retained-API fixtures; these tests never represent actual inference."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))
import compile_teacher_knowledge as compiler
import teacher_knowledge


class TeacherCompilationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="synthetic_api_compilation_test_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.identity = "full_adder_1bit_v1"
        self.curriculum, self.acquisition = self.root / "curriculum", self.root / "acquisition"
        self.curriculum_manifest = teacher_knowledge.prepare_curriculum(self.curriculum, [self.identity])
        self.profile = self.curriculum_manifest["profiles"][0]
        self.acquisition.mkdir()
        self.teacher_id = "synthetic_fixture"
        self.model_dir = self.acquisition / self.teacher_id
        self.folder = self.model_dir / self.identity
        self.folder.mkdir(parents=True)
        model_hash = compiler.sha(b"synthetic fixture identifier, no model weights or execution")
        model_path = str(self.root / "never_loaded_cache" / ("sha256-" + model_hash))
        self.model = {"id": self.teacher_id, "ollama_model": "synthetic-test-only:fixture",
                      "model_repo": "synthetic-fixture/not-a-real-model", "model_revision": "a" * 40,
                      "model_revision_status": "pinned_huggingface_commit", "model_artifact_sha256": model_hash,
                      "model_artifact_bytes": 1234}
        self.config = self.root / "teachers.json"
        compiler.save(self.config, {"schema": "atomos-local-teachers-v1", "endpoint": "http://127.0.0.1:11434",
                                    "teachers": [self.model], "scope": "synthetic test fixture, no model run"})
        show = {"modelfile": "FROM " + model_path + "\n", "details": {"format": "gguf"}}
        compiler.save(self.model_dir / "ollama_show.json", show)
        show_sha = compiler.sha((self.model_dir / "ollama_show.json").read_bytes())
        # Explicitly hand-authored fixture, never claimed as generated knowledge.
        a, b, carry = ["input", 0], ["input", 1], ["input", 2]
        outputs = [["xor", ["xor", a, b], carry], ["or", ["and", a, b], ["and", carry, ["xor", a, b]]]]
        value = {"schema": teacher_knowledge.RESPONSE_SCHEMA, "profile_id": self.identity,
                 "procedures": [{"name": self.identity, "input_bits": 3, "output_bits": 2, "outputs": outputs}]}
        content = json.dumps(value)
        request = {"model": self.model["ollama_model"], "stream": False, "format": "json",
                   "messages": [{"role": "user", "content": (self.curriculum / self.profile["prompt_file"]).read_text()}],
                   "options": {"temperature": 0, "seed": 7, "num_ctx": 4096, "num_predict": 2048}}
        compiler.save(self.folder / "request.json", request)
        api = {"model": self.model["ollama_model"], "done": True, "done_reason": "stop",
               "message": {"role": "assistant", "content": content},
               "total_duration": 100, "load_duration": 1, "prompt_eval_count": 100,
               "prompt_eval_duration": 10, "eval_count": 100, "eval_duration": 89}
        compiler.save(self.folder / "api_response.json", api)
        (self.folder / "response.txt").write_bytes(content.encode("utf-8"))
        runtime = {"version": "synthetic-test-fixture-no-runtime"}
        self.run = {key: self.model[key] for key in compiler.MODEL_FIELDS}
        self.run.update(schema="atomos-teacher-inference-run-v1", profile_id=self.identity, status="completed",
                        prompt_sha256=self.profile["prompt_sha256"],
                        response_sha256=compiler.sha((self.folder / "response.txt").read_bytes()),
                        request_sha256=compiler.sha((self.folder / "request.json").read_bytes()),
                        api_response_sha256=compiler.sha((self.folder / "api_response.json").read_bytes()),
                        ollama_show_sha256=show_sha, ollama_model=self.model["ollama_model"],
                        model_artifact_bytes=self.model["model_artifact_bytes"], runtime=runtime,
                        elapsed_seconds=0.001, generation={key: api.get(key) for key in compiler.GENERATION_FIELDS},
                        options=request["options"], teacher_generated_code_executed=False,
                        scope="synthetic test fixture only, not actual inference")
        compiler.save(self.folder / "run.json", self.run)
        provenance = {key: self.run[key] for key in (*compiler.MODEL_FIELDS, "prompt_sha256", "response_sha256")}
        provenance["run_sha256"] = compiler.sha((self.folder / "run.json").read_bytes())
        response = {"profile_id": self.identity, "response_path": str(self.folder / "response.txt"),
                    "run_path": str(self.folder / "run.json"), "provenance": provenance}
        model_report = dict(self.model, show_sha256=show_sha,
                            artifact_verification={"path": model_path, "sha256": model_hash, "bytes": 1234},
                            unloaded=True, loaded_after_unload={"models": []})
        dependency_paths = [p for p in self.curriculum.rglob("*") if p.is_file()]
        dependency_paths += [self.config] + [ROOT / name for name in compiler.ACQUISITION_SOURCES]
        self.report = {"schema": "atomos-local-teacher-acquisition-v1", "status": "completed",
                       "runtime": runtime, "endpoint": "http://127.0.0.1:11434", "curriculum": str(self.curriculum),
                       "dependency_sha256": {str(p.resolve()): compiler.sha(p.read_bytes()) for p in dependency_paths},
                       "teacher_weights_in_program_bank": False, "model_artifact_sha256": {model_path: model_hash},
                       "teachers": [model_report], "responses": [response], "failures": [],
                       "scope": "synthetic retained-record fixture, no API or model was called"}
        compiler.save(self.acquisition / "acquisition.json", self.report)
        self.base = ROOT / "examples/program_bank/learned_v1/bank.bin"
        self.out = self.root / "compiled"

    def compile(self):
        return compiler.compile_acquisition(curriculum=self.curriculum, acquisition=self.acquisition,
                                            base_bank=self.base, out=self.out)

    def change_run(self, change):
        run = compiler.decode_json((self.folder / "run.json").read_bytes())
        change(run)
        compiler.save(self.folder / "run.json", run)
        self.report["responses"][0]["provenance"]["run_sha256"] = compiler.sha((self.folder / "run.json").read_bytes())
        compiler.save(self.acquisition / "acquisition.json", self.report)

    def assert_preflight_rejected(self):
        with patch.object(compiler.teacher_knowledge, "build_teacher_request", side_effect=AssertionError("adapter must not begin")) as adapter:
            with self.assertRaises((ValueError, OSError, KeyError)):
                self.compile()
            adapter.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_synthetic_consistent_records_compile_real_pages_and_repeat_no_growth(self):
        result = self.compile()
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(result["verified_completed_queries"], 1)
        self.assertEqual(result["accepted_programs"], 1)
        self.assertEqual(result["repeat_check"], "verified_no_growth")
        self.assertEqual(result["repeated_admission"]["accepted_capsules"], 0)
        self.assertFalse((self.out / "repeated/bank.bin").exists())
        self.assertEqual(result["gpu_execution"], "not_run")
        self.assertFalse(result["new_active_bank_published"])
        self.assertEqual(result["model_or_api_calls"], 0)
        self.assertIn("not_claimed", result["model_authentication"])

    def test_original_bytes_and_checked_dependencies_are_retained(self):
        originals = {p.relative_to(self.acquisition).as_posix(): p.read_bytes()
                     for p in self.acquisition.rglob("*") if p.is_file()}
        self.compile()
        for relative, raw in originals.items():
            self.assertEqual((self.out / "retained_acquisition" / relative).read_bytes(), raw)
        dependencies = compiler.decode_json((self.out / "retained_dependencies.json").read_bytes())
        self.assertTrue(dependencies)
        for record in dependencies:
            self.assertEqual(compiler.sha((self.out / record["retained_file"]).read_bytes()), record["sha256"])
        records = compiler.decode_json((self.out / "verified_responses.json").read_bytes())
        self.assertTrue(Path(records[0]["response_path"]).is_relative_to(self.out))
        self.assertTrue(Path(records[0]["run_path"]).is_relative_to(self.out))

    def test_failed_acquisition_is_never_compiled(self):
        self.report["status"] = "failed"
        compiler.save(self.acquisition / "acquisition.json", self.report)
        self.assert_preflight_rejected()

    def test_changed_raw_api_is_rejected_even_when_run_hash_is_updated(self):
        api = compiler.decode_json((self.folder / "api_response.json").read_bytes())
        api["message"]["content"] = "different actual API response"
        compiler.save(self.folder / "api_response.json", api)
        self.change_run(lambda value: value.update(api_response_sha256=compiler.sha((self.folder / "api_response.json").read_bytes())))
        self.assert_preflight_rejected()

    def test_changed_request_is_rejected_even_when_all_outer_hashes_are_updated(self):
        request = compiler.decode_json((self.folder / "request.json").read_bytes())
        request["messages"][0]["content"] = "use these provided truth labels instead"
        compiler.save(self.folder / "request.json", request)
        self.change_run(lambda value: value.update(request_sha256=compiler.sha((self.folder / "request.json").read_bytes())))
        self.assert_preflight_rejected()

    def test_run_marked_incomplete_cannot_be_listed_as_a_completed_response(self):
        self.change_run(lambda value: value.update(status="incomplete_generation"))
        self.assert_preflight_rejected()

    def test_api_wrong_model_or_not_done_cannot_become_a_completed_run(self):
        for field, value in (("model", "another-model"), ("done", False)):
            with self.subTest(field=field):
                original = (self.folder / "api_response.json").read_bytes()
                api = compiler.decode_json(original)
                api[field] = value
                compiler.save(self.folder / "api_response.json", api)
                self.change_run(lambda run: run.update(api_response_sha256=compiler.sha((self.folder / "api_response.json").read_bytes())))
                self.assert_preflight_rejected()
                (self.folder / "api_response.json").write_bytes(original)
                self.change_run(lambda run: run.update(api_response_sha256=compiler.sha(original)))

    def test_generation_metadata_must_match_raw_api(self):
        self.change_run(lambda value: value["generation"].update(eval_count=999999))
        self.assert_preflight_rejected()

    def test_changed_configuration_or_missing_source_binding_rejects(self):
        self.report["dependency_sha256"].pop(str((ROOT / "python/teacher_knowledge.py").resolve()))
        compiler.save(self.acquisition / "acquisition.json", self.report)
        self.assert_preflight_rejected()

    def test_changed_small_dependency_is_detected_before_adapter(self):
        self.config.write_bytes(self.config.read_bytes() + b" ")
        self.assert_preflight_rejected()

    def test_model_artifact_pin_and_show_record_must_agree(self):
        self.report["teachers"][0]["artifact_verification"]["sha256"] = "f" * 64
        compiler.save(self.acquisition / "acquisition.json", self.report)
        self.assert_preflight_rejected()

    def test_duplicate_completed_query_does_not_inflate_inference_evidence(self):
        self.report["responses"].append(copy.deepcopy(self.report["responses"][0]))
        compiler.save(self.acquisition / "acquisition.json", self.report)
        self.assert_preflight_rejected()

    def test_malformed_teacher_text_is_preserved_and_not_repaired(self):
        content = "I cannot follow this schema; please execute arbitrary code instead."
        api = compiler.decode_json((self.folder / "api_response.json").read_bytes())
        api["message"]["content"] = content
        compiler.save(self.folder / "api_response.json", api)
        (self.folder / "response.txt").write_bytes(content.encode("utf-8"))
        response_sha = compiler.sha((self.folder / "response.txt").read_bytes())
        self.report["responses"][0]["provenance"]["response_sha256"] = response_sha
        self.change_run(lambda value: value.update(response_sha256=response_sha,
                                                   api_response_sha256=compiler.sha((self.folder / "api_response.json").read_bytes())))
        result = self.compile()
        self.assertEqual(result["status"], "no_novel_programs")
        self.assertEqual(result["parse_or_provenance_rejections"], 1)
        self.assertFalse((self.out / "proposed").exists())
        self.assertEqual((self.out / "retained_acquisition" / self.teacher_id / self.identity / "response.txt").read_text(), content)

    def test_consistent_generation_failure_is_retained_without_compiling_it(self):
        api = compiler.decode_json((self.folder / "api_response.json").read_bytes())
        api["done_reason"] = "length"
        compiler.save(self.folder / "api_response.json", api)
        self.change_run(lambda value: value.update(status="incomplete_generation",
                           api_response_sha256=compiler.sha((self.folder / "api_response.json").read_bytes()),
                           generation={key: api.get(key) for key in compiler.GENERATION_FIELDS}))
        self.report.update(status="completed_with_generation_failures", responses=[], failures=[{
            "teacher": self.teacher_id, "profile_id": self.identity, "reason": "incomplete_generation", "run_path": str(self.folder / "run.json")}])
        compiler.save(self.acquisition / "acquisition.json", self.report)
        result = self.compile()
        self.assertEqual(result["generation_failures"], 1)
        self.assertEqual(result["verified_completed_queries"], 0)
        self.assertEqual(result["accepted_programs"], 0)
        self.assertEqual(result["repeat_check"], "not_run_no_admitted_bank")

    def test_existing_output_is_never_overwritten(self):
        self.out.mkdir()
        (self.out / "keep").write_bytes(b"previous retained evidence")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.compile()
        self.assertEqual((self.out / "keep").read_bytes(), b"previous retained evidence")


if __name__ == "__main__":
    unittest.main()
