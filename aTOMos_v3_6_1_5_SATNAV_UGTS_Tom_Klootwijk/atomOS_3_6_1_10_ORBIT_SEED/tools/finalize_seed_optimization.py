#!/usr/bin/env python3
"""Bind completed R10 evidence to delivered bytes; no numerical experiments run.

Requires the preserved R9 sibling and the runtime ZIP in ../output. Run before
build_package.py; that separate operation creates the final manifest/archive.
"""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent / "atomOS_3_6_1_9_ORBIT_SEED"
REPORTS = {
    "packing": "results/seed_word_optimization/benchmark_final.json",
    "packing_review": "results/seed_word_optimization/independent_review.json",
    "query_preparation": "results/query_overhead_comparison_final.json",
    "session_identity": "results/query_snapshot_independent_check.json",
    "native_build": "results/orbit_native_36110_build/summary.json",
    "native_validation": "results/orbit_native_36110_validation/summary.json",
    "cpu_replay": "results/optimization_replay_cpu_final/summary.json",
    "cuda_replay": "results/optimization_replay_cuda/summary.json",
    "wrapper_compatibility": "results/wrapper_compatibility/summary.json",
    "seed_execution": "results/seed_36110_final_validation/summary.json",
    "calendar": "results/calendar_phase_36110/summary.json",
    "retained_cpu": "results/retained_36110_cpu/satnav/independent_verification.json",
    "retained_gpu": "results/gpu_20260915_070915_949456/status.json",
    "runtime_archive": "results/runtime_36110_archive_validation.json",
    "ui": "results/orbit_ui_36110_qa.json",
    "pdf": "results/orbit_pdf_36110_qa/qa.json",
    "git": "results/git_delivery_36110.json",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_path(name):
    normalized = name.replace("\\", "/")
    for base in (ROOT, PARENT):
        token = base.name + "/"
        if token in normalized:
            return base / normalized.split(token, 1)[1]
    direct = ROOT / normalized
    return direct if direct.exists() or "/" in normalized else ROOT / "python" / normalized


def bind_sources(values, overrides=None):
    for name, expected in values.items():
        path = (overrides or {}).get(name, source_path(name))
        require(sha(path) == expected, "Source hash mismatch: " + name)


def main():
    reports = {key: json.loads((ROOT / path).read_text(encoding="utf-8"))
               for key, path in REPORTS.items()}
    for key, report in reports.items():
        if key == "pdf":
            require(report["visual_status"] == "passed", "PDF visual review incomplete")
        elif key == "retained_gpu":
            require(all(value == "passed" for value in report.values()), "GPU checks failed")
        else:
            require(report["status"] == "passed", key + " did not pass")
    for key in ("packing", "native_build", "cpu_replay", "calendar", "session_identity"):
        bind_sources(reports[key]["source_sha256"])
    bind_sources(reports["query_preparation"]["current"]["source_sha256"])
    require(sha(PARENT / "bin/cpu/orbit_worker.exe") == reports["query_preparation"]["native_binary_sha256"],
            "Query benchmark's fixed R9 worker changed")
    build = reports["native_build"]
    for backend, binaries in build["binaries"].items():
        for name, digest in binaries.items():
            require(sha(ROOT / "bin" / backend / name) == digest, "Binary mismatch: " + name)
        require(build[backend + "_ctest"]["passed"] == build[backend + "_ctest"]["total"] == 4,
                "Native CTest coverage changed")
    require(sum(map(len, build["binaries"].values())) == 10, "Expected ten native binaries")
    for backend in ("cpu", "cuda"):
        require(reports[backend + "_replay"]["worker_sha256"] == build["binaries"][backend]["orbit_worker.exe"],
                "Replay worker changed")
    wrapper = reports["wrapper_compatibility"]
    old_wrapper = ROOT / "results/wrapper_compatibility/previous_orbit_native.py"
    require(sha(old_wrapper) == wrapper["previous_wrapper_sha256"], "Historical wrapper missing")
    require(sha(ROOT / "python/orbit_native.py") == wrapper["current_wrapper_sha256"], "Final wrapper changed")
    require(wrapper["cuda_worker_sha256"] == build["binaries"]["cuda"]["orbit_worker.exe"], "Wrapper CUDA worker changed")
    require(len(wrapper["objects"]) == 8, "Wrapper coverage incomplete")
    for obj in wrapper["objects"].values():
        require(obj["numeric_model_payloads_byte_identical"] and obj["actual_worker_inputs_byte_identical"],
                "Wrapper transport changed")
        require(sha(ROOT / obj["seed_file"]) == obj["seed_file_sha256"], "Wrapper seed changed")
    bind_sources(reports["cuda_replay"]["source_sha256"], {"python/orbit_native.py": old_wrapper})
    seeds = reports["packing"]["seeds"]
    require(len(seeds) == 8, "Expected eight seeds")
    for seed in seeds:
        path = ROOT / seed["path"]
        require(sha(path) == seed["sha256"] == sha(PARENT / seed["path"]), "Seed bytes changed")
    for backend in ("cpu", "cuda"):
        replay = reports[backend + "_replay"]
        require(replay["total_samples"] == 15553, "Replay coverage changed")
        for name, obj in replay["objects"].items():
            require(sha(ROOT / obj["baseline_csv"]) == obj["baseline_csv_sha256"], "Replay reference changed")
            same_backend = backend == "cpu" or name.startswith("january:")
            if same_backend:
                require(obj["changed_prediction_rows"] == 0, "Exact replay changed")
            require(obj["max_prediction_difference_m"] <= .01, "Replay exceeds numerical tolerance")
            require(obj["first_day_max_reference_discrepancy_m"] < 10., "First-day sampled target failed")
    calendar = reports["calendar"]
    bind_sources(calendar["seed_sha256"])
    require(calendar["failure_count"] == 0 and calendar["checks"] == 9519315, "Calendar checks incomplete")
    require(calendar["calendar"]["dates_in_cycle"] == 146097, "Gregorian cycle incomplete")
    log_path = "results/python_tests_36110_calendar_final.log"
    log = (ROOT / log_path).read_text(encoding="utf-8")
    require(re.search(r"Ran 164 tests in [\d.]+s\s+OK\s*$", log) is not None, "Full Python suite incomplete")
    pdf_path = "output/pdf/aTOMos_v3_6_1_10_Orbital_Seed_Kernel_UGTS_Tom_Klootwijk.pdf"
    pdf = reports["pdf"]
    require(sha(ROOT / pdf_path) == pdf["pdf_sha256"] and pdf["page_count"] == 74, "Reviewed PDF changed")
    require(pdf["calendar_evidence"]["sha256"] == sha(ROOT / REPORTS["calendar"]), "PDF calendar evidence changed")
    runtime_path = ROOT.parent / "output/aTOMos_v3_6_1_10_Orbit_Runtime.zip"
    require(sha(runtime_path) == reports["runtime_archive"]["archive_sha256"], "Runtime archive changed")
    with zipfile.ZipFile(runtime_path) as archive:
        prefix = "aTOMos_3_6_1_10_Orbit_Runtime/"
        manifest = archive.read(prefix + "SHA256SUMS.txt").decode("utf-8").splitlines()
        require(len(manifest) == 39 and len(archive.namelist()) == 40, "Runtime inventory changed")
        for line in manifest:
            digest, name = line.split("  ", 1)
            data = archive.read(prefix + name)
            require(hashlib.sha256(data).hexdigest() == digest, "Runtime ZIP checksum failed")
            if name != "README.md":
                require(data == (ROOT / name).read_bytes(), "Runtime source changed: " + name)
    parent_manifest = PARENT / "SHA256SUMS.txt"
    require(sha(parent_manifest) == "17db828c7782b51d7ec05b61d3f8087b08538930743a80ad1152a0e9665da5c6", "Parent manifest changed")
    parent_lines = parent_manifest.read_text(encoding="utf-8").splitlines()
    require(len(parent_lines) == 775, "Parent inventory changed")
    for line in parent_lines:
        digest, name = line.split("  ", 1)
        require(sha(PARENT / name) == digest, "Parent changed: " + name)
    evidence = {key: {"path": path, "sha256": sha(ROOT / path)} for key, path in REPORTS.items()}
    evidence["python_tests"] = {"path": log_path, "sha256": sha(ROOT / log_path), "passed": 164}
    index = {
        "release": "3.6.1.10", "seed_schema_version": "3.6.1.9",
        "status": "implementation_passed_accuracy_preserved",
        "evidence": evidence, "parent_evidence": "source/baseline_3_6_1_9_validation.json",
        "parent_files_verified": 775, "seed_files_byte_identical": 8,
        "packing_speedup": {key: value["median_speedup"] for key, value in reports["packing"]["timings"].items()},
        "execution": {"cpu_exact_samples": 15553, "cuda_january_exact_samples": 8064,
                      "cuda_february_vs_cpu_samples": 7489,
                      "cuda_february_max_difference_m": max(x["max_prediction_difference_m"] for n, x in reports["cuda_replay"]["objects"].items() if n.startswith("february:")),
                      "cuda_wrapper_binding": "Historical full replay composed with byte-identical transport and final-wrapper CUDA checks; not a final-wrapper all-epoch rerun.",
                      "isolation_binding": "Original final isolation report records source byte counts and denied original-release reads; it does not contain a source hash map.",
                      "ui_binding": "Recorded UI check plus current byte-identical runtime ZIP members; original UI report does not contain source hashes."},
        "calendar": {"days": 146097, "checks": 9519315, "failures": 0,
                     "scope": "Calendar/address verification; absolute date and winding continue. No 400-year orbit or UTC leap-second claim."},
        "physical_accuracy": {"status": "inherited_frozen_measurements_preserved",
                              "sampled_first_day_engineering_target_m": 10,
                              "scope": "January reused development benchmark and independent February confirmation pass sampled first-day target. Longer horizons, gaps and reference discontinuities remain explicit. No universal physical accuracy bound; no refitting in R10.",
                              "reports": ["results/orbit_accuracy_r2_cpu_verified/accuracy_summary.json", "results/orbit_accuracy_confirmation_cpu_verified/accuracy_summary.json"]},
        "pdf": {"path": pdf_path, "sha256": pdf["pdf_sha256"], "pages": 74},
        "runtime_zip_sha256": sha(runtime_path),
        "archive_note": "Run build_package.py after this index. Final ZIP hash is recorded outside its own archive to avoid a circular hash.",
        "finalizer_sha256": sha(Path(__file__)),
    }
    (ROOT / "validation_results.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    version = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8"))
    require(version["seed_schema_version"] == "3.6.1.9", "Seed schema changed")
    version["status"] = "verified"
    (ROOT / "VERSION.json").write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
    print("PASS: final R10 evidence bound; 164 Python tests, 8 seeds, 10 binaries, 775 preserved parent files")


if __name__ == "__main__":
    main()
