"""Verify retained local teacher acquisition and prepare novel packed procedures.

This tool makes no model/API calls, executes no teacher code and repairs no
responses. It checks acquisition-record consistency, not cryptographic model
authentication. GPU validation and active-bank publication are separate steps.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import knowledge_admission
import teacher_knowledge


MAX_FILE_BYTES = 16 << 20
MAX_ACQUISITION_BYTES = 64 << 20
MAX_ACQUISITION_FILES = 512
MAX_DEPENDENCIES = 64
MODEL_FIELDS = ("model_repo", "model_revision", "model_revision_status", "model_artifact_sha256")
CONFIG_FIELDS = ("id", "ollama_model", *MODEL_FIELDS, "model_artifact_bytes")
GENERATION_FIELDS = ("done_reason", "total_duration", "load_duration", "prompt_eval_count",
                     "prompt_eval_duration", "eval_count", "eval_duration")
ACQUISITION_SOURCES = ("tools/acquire_teacher_knowledge.py", "python/teacher_knowledge.py",
                       "python/program_bank.py", "python/knowledge_admission.py")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bytes(path, limit=MAX_FILE_BYTES):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError("retained artifact byte bound: " + str(path))
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError("retained artifact byte bound: " + str(path))
    return raw


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate retained JSON key")
        value[key] = item
    return value


def reject_constant(value):
    raise ValueError("nonfinite retained JSON number: " + value)


def decode_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(value, field):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("invalid SHA256 field: " + field)
    return value


def require_unchanged(bindings):
    for name, expected in bindings.items():
        if not Path(name).is_file() or sha(read_bytes(name)) != expected:
            raise ValueError("compilation dependency changed: " + name)


def _captured_acquisition(folder):
    snapshots, total = {}, 0
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(folder):
            raise ValueError("acquisition contains a symlink or external artifact")
        if not path.is_file():
            continue
        if len(snapshots) >= MAX_ACQUISITION_FILES:
            raise ValueError("acquisition file count bound")
        raw = read_bytes(path)
        total += len(raw)
        if total > MAX_ACQUISITION_BYTES:
            raise ValueError("acquisition total byte bound")
        snapshots[path.relative_to(folder).as_posix()] = raw
    if "acquisition.json" not in snapshots:
        raise ValueError("missing completed acquisition receipt")
    return snapshots


def verify_acquisition(curriculum, acquisition):
    """Fail before output creation on inconsistent acquisition evidence."""
    curriculum, acquisition = Path(curriculum).resolve(), Path(acquisition).resolve()
    frozen = teacher_knowledge.load_curriculum(curriculum)
    snapshots = _captured_acquisition(acquisition)
    report = decode_json(snapshots["acquisition.json"])
    if (not isinstance(report, dict) or report.get("schema") != "atomos-local-teacher-acquisition-v1" or
            report.get("status") not in ("completed", "completed_with_generation_failures") or
            report.get("teacher_weights_in_program_bank") is not False or
            report.get("endpoint") not in ("http://127.0.0.1:11434", "http://localhost:11434")):
        raise ValueError("acquisition is not a completed supported local-teacher run")
    if Path(report.get("curriculum", "")).resolve() != curriculum:
        raise ValueError("acquisition names a different frozen curriculum")
    dependencies = report.get("dependency_sha256")
    if not isinstance(dependencies, dict) or not 1 <= len(dependencies) <= MAX_DEPENDENCIES:
        raise ValueError("acquisition dependency list bound")
    dependency_snapshots = {}
    for name, expected in dependencies.items():
        digest(expected, "dependency_sha256")
        if not isinstance(name, str) or not Path(name).is_absolute():
            raise ValueError("acquisition dependency path must be absolute")
        raw = read_bytes(name)
        if sha(raw) != expected:
            raise ValueError("acquisition dependency changed: " + name)
        dependency_snapshots[name] = raw
    required = {str((ROOT / name).resolve()) for name in ACQUISITION_SOURCES}
    required.update(str(path.resolve()) for path in curriculum.rglob("*") if path.is_file())
    if not required.issubset(dependencies):
        raise ValueError("acquisition omits required source/curriculum bindings")
    if dependencies[str(curriculum / "curriculum.json")] != frozen["curriculum_sha256"]:
        raise ValueError("acquisition curriculum hash differs")
    configs = []
    for name in set(dependencies) - required:
        try:
            value = decode_json(dependency_snapshots[name])
        except (ValueError, UnicodeError):
            continue
        if isinstance(value, dict) and value.get("schema") == "atomos-local-teachers-v1":
            configs.append(value)
    if len(configs) != 1 or configs[0].get("endpoint") != report["endpoint"]:
        raise ValueError("acquisition needs one unchanged matching teacher configuration")
    models = configs[0].get("teachers")
    teachers = report.get("teachers")
    if not isinstance(models, list) or not 1 <= len(models) <= 4 or not isinstance(teachers, list) or len(teachers) != len(models):
        raise ValueError("acquisition teacher inventory mismatch")
    if (any(not isinstance(m, dict) or not isinstance(m.get("id"), str) or
            re.fullmatch(r"[a-z0-9_]{1,80}", m["id"]) is None for m in models) or
            len({m["id"] for m in models}) != len(models)):
        raise ValueError("invalid teacher identities")
    expected_models = {m["id"]: m for m in models}
    by_id, by_model, artifact_pins = {}, {}, {}
    for model in teachers:
        if not isinstance(model, dict) or model.get("id") not in expected_models or model["id"] in by_id:
            raise ValueError("acquisition duplicates or invents a teacher")
        wanted = expected_models[model["id"]]
        if any(field not in model or model[field] != wanted.get(field) for field in CONFIG_FIELDS):
            raise ValueError("teacher pins differ from unchanged configuration")
        model_hash = digest(model["model_artifact_sha256"], "model_artifact_sha256")
        if type(model["model_artifact_bytes"]) is not int or model["model_artifact_bytes"] <= 0:
            raise ValueError("model artifact size is invalid")
        name = model["ollama_model"]
        if not isinstance(name, str) or not 1 <= len(name) <= 512 or name in by_model:
            raise ValueError("teacher model names must be bounded and unique")
        artifact = model.get("artifact_verification")
        if (not isinstance(artifact, dict) or artifact.get("sha256") != model_hash or
                artifact.get("bytes") != model["model_artifact_bytes"] or
                not isinstance(artifact.get("path"), str) or
                Path(artifact["path"]).name != "sha256-" + model_hash):
            raise ValueError("acquisition artifact verification disagrees with model pin")
        show_raw = snapshots.get(model["id"] + "/ollama_show.json")
        if show_raw is None or sha(show_raw) != model.get("show_sha256"):
            raise ValueError("teacher show metadata hash mismatch")
        show = decode_json(show_raw)
        matches = re.findall(r"^FROM (.+)$", show.get("modelfile", ""), re.MULTILINE)
        if (show.get("details", {}).get("format") != "gguf" or len(matches) != 1 or
                Path(matches[0].strip().strip('"')).resolve() != Path(artifact["path"]).resolve()):
            raise ValueError("retained model show data does not identify the pinned artifact")
        if (model.get("unloaded") is not True or
                any(m.get("name") == name or m.get("model") == name
                    for m in model.get("loaded_after_unload", {}).get("models", []))):
            raise ValueError("acquisition lacks completed selected-teacher unload evidence")
        artifact_pins[artifact["path"]] = model_hash
        by_id[model["id"]], by_model[name] = model, model
    if report.get("model_artifact_sha256") != artifact_pins:
        raise ValueError("acquisition aggregate model artifact pins differ")
    responses, failures = report.get("responses"), report.get("failures")
    if not isinstance(responses, list) or not isinstance(failures, list) or len(responses) > teacher_knowledge.MAX_RESPONSES:
        raise ValueError("acquisition response/failure list bound")
    if (report["status"] == "completed" and failures) or (report["status"] == "completed_with_generation_failures" and not failures):
        raise ValueError("acquisition completion status contradicts generation failures")
    expected_count = len(models) * len(frozen["profiles"])
    if len(responses) + len(failures) != expected_count:
        raise ValueError("acquisition does not account for every teacher/profile query")
    verified, seen = [], set()

    def retained_run(run_path, expected_profile=None):
        path = Path(run_path).resolve()
        if not path.is_relative_to(acquisition):
            raise ValueError("response/run artifact outside retained acquisition")
        relative = path.relative_to(acquisition).as_posix()
        parts = relative.split("/")
        if len(parts) != 3 or parts[2] != "run.json" or parts[0] not in by_id or parts[1] not in frozen["profiles"]:
            raise ValueError("noncanonical teacher/profile run artifact")
        teacher_id, profile_id = parts[:2]
        if expected_profile is not None and profile_id != expected_profile:
            raise ValueError("response profile differs from retained run path")
        pair = (teacher_id, profile_id)
        if pair in seen:
            raise ValueError("duplicate teacher/profile query receipt")
        seen.add(pair)
        prefix = teacher_id + "/" + profile_id + "/"
        required_files = {key: prefix + filename for key, filename in
                          (("request", "request.json"), ("api", "api_response.json"),
                           ("response", "response.txt"), ("run", "run.json"))}
        if any(name not in snapshots for name in required_files.values()):
            raise ValueError("missing retained request/API/content/run artifact")
        raw = {key: snapshots[name] for key, name in required_files.items()}
        request, api, run = [decode_json(raw[key]) for key in ("request", "api", "run")]
        if not all(isinstance(value, dict) for value in (request, api, run)):
            raise ValueError("retained request/API/run must be JSON objects")
        model, profile = by_id[teacher_id], frozen["profiles"][profile_id]
        if (run.get("schema") != "atomos-teacher-inference-run-v1" or run.get("profile_id") != profile_id or
                run.get("ollama_model") != model["ollama_model"] or
                any(run.get(key) != model[key] for key in MODEL_FIELDS) or
                run.get("model_artifact_bytes") != model["model_artifact_bytes"] or
                run.get("runtime") != report.get("runtime") or
                run.get("ollama_show_sha256") != model["show_sha256"] or
                run.get("teacher_generated_code_executed") is not False):
            raise ValueError("teacher run identity/runtime/artifact metadata mismatch")
        for key, actual in (("prompt_sha256", profile["prompt_sha256"]), ("response_sha256", sha(raw["response"])),
                            ("request_sha256", sha(raw["request"])), ("api_response_sha256", sha(raw["api"]))):
            if run.get(key) != actual:
                raise ValueError("teacher run artifact binding mismatch: " + key)
        if (request.get("model") != model["ollama_model"] or request.get("stream") is not False or
                request.get("messages") != [{"role": "user", "content": profile["prompt"]}] or
                request.get("options") != run.get("options") or
                not (request.get("format") == "json" or isinstance(request.get("format"), dict))):
            raise ValueError("retained request differs from frozen prompt/model/options")
        if (api.get("model") != model["ollama_model"] or api.get("done") is not True or
                api.get("message", {}).get("role") != "assistant" or
                not isinstance(api.get("message", {}).get("content"), str) or
                api["message"]["content"].encode("utf-8") != raw["response"]):
            raise ValueError("retained raw API response does not match completed model/content")
        if run.get("generation") != {key: api.get(key) for key in GENERATION_FIELDS}:
            raise ValueError("run generation metadata differs from raw API response")
        elapsed = run.get("elapsed_seconds")
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("run elapsed time is invalid")
        return profile_id, model, run, api, required_files, raw

    for record in responses:
        if not isinstance(record, dict) or not isinstance(record.get("provenance"), dict):
            raise ValueError("missing response provenance")
        identity, model, run, api, paths, raw = retained_run(record["run_path"], record.get("profile_id"))
        if run.get("status") != "completed" or api.get("done_reason") != "stop":
            raise ValueError("accepted response is not a completed stop generation")
        if Path(record["response_path"]).resolve() != acquisition / paths["response"]:
            raise ValueError("response content path differs from retained run")
        provenance = record["provenance"]
        if (any(provenance.get(key) != run.get(key) for key in (*MODEL_FIELDS, "prompt_sha256", "response_sha256")) or
                provenance.get("run_sha256") != sha(raw["run"])):
            raise ValueError("acquisition response provenance differs from retained run")
        verified.append({"record": copy.deepcopy(record), "relative_paths": paths,
                         "teacher_id": model["id"], "profile_id": identity,
                         "request_sha256": sha(raw["request"]), "api_response_sha256": sha(raw["api"])})
    for failure in failures:
        if not isinstance(failure, dict):
            raise ValueError("invalid incomplete-generation record")
        identity, model, run, api, _, _ = retained_run(failure["run_path"], failure.get("profile_id"))
        if (failure.get("teacher") != model["id"] or failure.get("reason") != "incomplete_generation" or
                run.get("status") != "incomplete_generation" or api.get("done_reason") == "stop"):
            raise ValueError("generation failure is inconsistent with retained API/run")
    bindings = dict(dependencies)
    bindings.update({str(acquisition / name): sha(raw) for name, raw in snapshots.items()})
    require_unchanged(bindings)
    return {"acquisition": report, "snapshots": snapshots, "dependency_snapshots": dependency_snapshots,
            "bindings": bindings, "verified_responses": verified,
            "verified_completed_queries": len(verified), "generation_failures": len(failures),
            "curriculum_sha256": frozen["curriculum_sha256"], "model_artifact_pins": artifact_pins}


def compile_acquisition(*, curriculum, acquisition, base_bank, out):
    curriculum, acquisition, base_bank, out = [Path(value).resolve() for value in (curriculum, acquisition, base_bank, out)]
    if out.exists():
        raise ValueError("refusing to overwrite teacher compilation output")
    checked = verify_acquisition(curriculum, acquisition)
    # Bind source code and the actual base before retaining/compiling proposals.
    bindings = checked["bindings"]
    for path in (Path(__file__).resolve(), base_bank, base_bank.parent / "manifest.json"):
        bindings[str(path)] = sha(read_bytes(path))
    out.mkdir(parents=True, exist_ok=False)
    report = {"schema": "atomos-teacher-compilation-v1", "status": "running",
              "source_acquisition": str(acquisition), "curriculum": str(curriculum),
              "curriculum_sha256": checked["curriculum_sha256"],
              "verified_completed_queries": checked["verified_completed_queries"],
              "generation_failures": checked["generation_failures"],
              "model_artifact_pins": checked["model_artifact_pins"], "dependency_sha256": bindings,
              "teacher_code_executed": False, "model_or_api_calls": 0, "gpu_execution": "not_run",
              "new_active_bank_published": False,
              "model_authentication": "not_claimed; retained acquisition/request/API/artifact-record consistency checked",
              "model_weight_rehash": "not_run_by_compiler; acquisition records before/after artifact checks",
              "knowledge_scope": "teacher-returned bounded algorithms compiled and checked against independently frozen integer cases"}
    def retain():
        save(out / "compilation.json", report)
    retain()
    try:
        for name, raw in checked["snapshots"].items():
            path = out / "retained_acquisition" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        dependency_records = []
        (out / "dependency_snapshots").mkdir()
        for index, (name, raw) in enumerate(sorted(checked["dependency_snapshots"].items())):
            relative = "dependency_snapshots/" + str(index).zfill(3) + "_" + Path(name).name
            (out / relative).write_bytes(raw)
            dependency_records.append({"original_path": name, "retained_file": relative, "sha256": sha(raw)})
        save(out / "retained_dependencies.json", dependency_records)
        responses = []
        for verified in checked["verified_responses"]:
            record = verified["record"]
            for key, retained_key in (("run_path", "run"), ("response_path", "response")):
                record[key] = str(out / "retained_acquisition" / verified["relative_paths"][retained_key])
            responses.append(record)
        save(out / "verified_responses.json", responses)
        require_unchanged(bindings)
        if responses:
            request, adapter = teacher_knowledge.build_teacher_request(curriculum, responses)
        else:
            request = {"schema": knowledge_admission.SCHEMA, "oracles": [], "candidates": []}
            adapter = {"schema": "atomos-teacher-adapter-receipt-v1", "status": "no_completed_responses",
                       "compiled_candidates": 0, "rejected_responses": 0, "decisions": []}
        save(out / "adapter.json", adapter)
        save(out / "candidates.json", request)
        report.update(compiled_candidates=adapter["compiled_candidates"],
                      parse_or_provenance_rejections=adapter["rejected_responses"],
                      response_decisions=adapter["decisions"], accepted_programs=0,
                      semantic_rejections=[], repeat_check="not_run_no_admitted_bank")
        if request["candidates"]:
            admitted = knowledge_admission.admit_candidates(base_bank, request, out / "proposed",
                                                            candidate_limit=teacher_knowledge.MAX_RESPONSES)
            report.update(accepted_programs=admitted["accepted_capsules"],
                          semantic_rejections=[d for d in admitted["decisions"] if d["status"] == "rejected"],
                          admitted_programs=[d for d in admitted["decisions"] if d["status"] == "accepted"],
                          admission=admitted)
            if admitted["accepted_capsules"]:
                repeated = knowledge_admission.admit_candidates(out / "proposed/bank.bin", request, out / "repeated",
                                                                candidate_limit=teacher_knowledge.MAX_RESPONSES)
                if (repeated["status"] != "no_growth" or repeated["accepted_capsules"] != 0 or
                        repeated["result_capsules"] != admitted["result_capsules"] or
                        (out / "repeated/bank.bin").exists()):
                    raise ValueError("repeated teacher batch allocated new semantic program storage")
                report.update(repeat_check="verified_no_growth", repeated_admission=repeated,
                              proposed_bank_sha256=admitted["proposed_bank_sha256"])
        require_unchanged(bindings)
        # Freeze every retained output except the report that is about to finish.
        report["artifact_sha256"] = {path.relative_to(out).as_posix(): sha(read_bytes(path))
                                     for path in sorted(out.rglob("*")) if path.is_file() and path.name != "compilation.json"}
        report["status"] = "prepared" if report["accepted_programs"] else "no_novel_programs"
        retain()
        return report
    except Exception as error:
        report.update(status="failed", reason=str(error))
        retain()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="freeze independent cases and prompts before teacher acquisition")
    prepare.add_argument("--out", type=Path, required=True)
    compile_parser = commands.add_parser("compile", help="verify retained acquisition, compile and admit novel procedures")
    for field in ("curriculum", "acquisition", "base-bank", "out"):
        compile_parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = teacher_knowledge.prepare_curriculum(args.out)
            print(json.dumps({"status": "frozen", "profiles": len(result["profiles"]),
                              "curriculum": str(args.out / "curriculum.json")}))
            return 0
        result = compile_acquisition(curriculum=args.curriculum, acquisition=args.acquisition,
                                     base_bank=args.base_bank, out=args.out)
        print(json.dumps({"status": result["status"], "verified_completed_queries": result["verified_completed_queries"],
                          "compiled_candidates": result["compiled_candidates"], "accepted_programs": result["accepted_programs"],
                          "repeat_check": result["repeat_check"], "report": str(args.out / "compilation.json")}))
        return 0
    except (OSError, KeyError, TypeError, ValueError, RecursionError) as error:
        print(json.dumps({"status": "rejected", "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
