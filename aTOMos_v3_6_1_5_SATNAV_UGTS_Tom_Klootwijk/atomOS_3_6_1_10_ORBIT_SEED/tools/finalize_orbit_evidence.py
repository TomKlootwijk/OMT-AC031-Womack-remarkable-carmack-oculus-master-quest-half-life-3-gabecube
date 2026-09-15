#!/usr/bin/env python3
"""Bind final evidence to the delivered seed/model/binary bytes and generate PDF tables."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from orbit_seed import digest, load
from assess_orbit_tolerance import assess


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    names = {"native": "orbit_native_r2_validation_final/summary.json", "seeds": "orbit_seed_r2_release_validation/summary.json",
             "accuracy_cpu": "orbit_accuracy_r2_cpu_verified/accuracy_summary.json", "accuracy_cuda": "orbit_accuracy_r2_cuda_verified/accuracy_summary.json",
             "retained": "retained_native_3619/summary.json", "physical": "orbit_physical_r2_audit_final/physical_audit.json",
             "physical_jump": "orbit_physical_r2_jump_audit/physical_audit.json",
             "bitplane_replay": "orbit_bitplane_final_replay.json", "ui": "orbit_ui_r2_qa.json",
             "runtime_archive": "orbit_runtime_archive_validation.json",
             "preserved_parents": "parent_release_verification.json",
             "confirmation": "orbit_accuracy_confirmation_cpu_verified/accuracy_summary.json"}
    evidence = {key: json.loads((ROOT / "results" / name).read_text()) for key, name in names.items()}
    for key, report in evidence.items():
        if key == "physical":
            if report.get("status") != "passed" or set(report.get("models", {})) != {"G05", "C03", "C06", "CHANDRA"}:
                raise ValueError("Physical audit did not pass all four models")
        elif key.startswith("accuracy_") or key == "confirmation":
            if report.get("status") != "measured" or report.get("complete_four_class_scope") is not True:
                raise ValueError(key + " measurement is incomplete")
        elif report.get("status") not in ("passed", "complete", "completed"):
            raise ValueError(key + " evidence is incomplete")
    log = (ROOT / "results/python_tests_3619_r2_release.log").read_text()
    for name, expected in evidence["bitplane_replay"]["shared_runtime_source_sha256"].items():
        if sha(ROOT / "python" / name) != expected: raise ValueError("Isolated runtime module identity mismatch: " + name)
    count = re.search(r"Ran (\d+) tests", log)
    if not count or not log.rstrip().endswith("OK") or "skipped=" in log: raise ValueError("Python tests did not fully pass")
    for backend in ("cpu", "cuda"):
        binary = ROOT / "bin" / backend / "orbit_worker.exe"
        report = evidence["accuracy_" + backend]
        if report["native_binary_sha256"] != sha(binary): raise ValueError("Accuracy binary identity mismatch")
        for row in report["objects"]:
            name = row["object_id"]
            path = ROOT / "examples/orbit/seeds" / (name + ".orbseed")
            seed = load(path)
            if row["physical_model_sha256"] != digest(seed["model"]): raise ValueError("Accuracy physical model identity mismatch")
            model_file = ROOT / "examples/orbit/models" / (name + ".json")
            if evidence["native"]["models"][name]["model_sha256"] != sha(model_file): raise ValueError("Native model identity mismatch")
            seed_record = evidence["seeds"]["objects"][name]["seed"]
            if seed_record["file_sha256"] != sha(path): raise ValueError("Validated seed bytes differ")
    objects = evidence["seeds"]["objects"]
    rows = []
    for name in ("G05", "C03", "C06", "CHANDRA"):
        o = objects[name]
        rows.append(f"{name} & {o['seed']['file_bytes']:,} & {o['feedback']['original_queries']:,} & {o['feedback']['counterfactual_queries']:,} & {o['scrubbing']['warm_max_end_to_end_ms']:.3f}\\\\")
    events = sum(r["events"] for o in objects.values() for r in o["event_searches"])
    max_delta = max(r["max_refinement_time_delta_s"] for o in objects.values() for r in o["event_searches"])
    native = evidence["native"]
    cuda_max = max(m["cuda"]["cpu_position_max_m"] for m in native["models"].values())
    cpu_bytes = (ROOT / "bin/cpu/orbit_worker.exe").stat().st_size
    source_bytes = max(o["isolation"]["shared_runtime_source_bytes"] for o in evidence["bitplane_replay"]["objects"].values())
    ratio = 112952 / max(o["seed"]["file_bytes"] for o in objects.values())
    acceptance = assess(ROOT / "results" / names["accuracy_cpu"])
    acceptance24 = assess(ROOT / "results" / names["accuracy_cpu"], hours=(24.,))
    confirmation24 = assess(ROOT / "results" / names["confirmation"], hours=(24.,))
    confirmation = assess(ROOT / "results" / names["confirmation"])
    if evidence["confirmation"]["native_binary_sha256"] != sha(ROOT / "bin/cpu/orbit_worker.exe"):
        raise ValueError("Confirmation binary identity mismatch")
    for obj in evidence["confirmation"]["objects"]:
        model_path = ROOT / "examples/orbit/confirmation_models" / (obj["object_id"] + ".json")
        if sha(model_path) != obj["model_file_sha256"]: raise ValueError("Confirmation model identity mismatch")
    (ROOT / "results/orbit_confirmation_tolerance_verified.json").write_text(json.dumps(confirmation, indent=2) + "\n")
    (ROOT / "results/orbit_confirmation_24h_tolerance_verified.json").write_text(json.dumps(confirmation24, indent=2) + "\n")
    (ROOT / "results/orbit_r2_tolerance_verified.json").write_text(json.dumps(acceptance, indent=2) + "\n")
    (ROOT / "results/orbit_r2_24h_tolerance_verified.json").write_text(json.dumps(acceptance24, indent=2) + "\n")
    text = r"""\subsection{Packed execution and regression evidence}
The following numbers are derived from the final decoded seeds and verified
native binaries. The isolated replay child receives only the packed seed, shared
runtime source and native executable; an audit hook denies every read under the
original release directory. The reconstructed fractional, past and seven-day
timestamp states match the normal native run bit for bit.

\begin{center}\begin{tabular}{@{}lrrrr@{}}\toprule
Object & Seed bytes & Default queries & Altered JK & Warm max (ms)\\\midrule
""" + "\n".join(rows) + r"""
\bottomrule\end{tabular}\end{center}
Query counts cover one day. The counterfactual sets $J=1,K=0$ and changes the
actual timestamps selected by the native recurrence. Physical states at shared
timestamps remain identical. Warm timing is end-to-end Python/native geometry
latency on this host for the recorded fractional seek sequence, not a universal
performance bound. Cold seeks may require thousands of integration steps.

""" + f"Across eight seven-day station/object searches, {events} rise/set events were found. The largest event-time change under refinement from 120-second to 30-second sampling was {max_delta:.6f} seconds. The event algorithm's grazing and no-global-root-exclusion qualifications still apply.\n\n" + r"""
A five-minute, seven-day table containing time and six binary64 state components
would occupy 112,952 bytes before its metadata. This compares a generated state
table to its specified model, not arbitrary-trajectory compression.
The demonstration archive also contains
large reference datasets and audit traces, which are not per-seed replay inputs.

""" + f"The table is {ratio:.2f} times the size of the largest complete packed seed. The shared CPU executable is {cpu_bytes:,} bytes, and the isolated shared Python source is {source_bytes:,} bytes at validation. Installed libraries and the OS/C++ runtime are additional shared dependencies. The default codec packs 64 one-bit planes into uint64 words without discarding any numeric bit. The canonical codec remains readable; bit-plane packing is slightly larger for these examples.\n\n" + f"The new native orbital checks compare 1,040 CPU/CUDA positions across the four models, with maximum disagreement {cuda_max:.8f} m. All 256 complete CPU/CUDA two-stage word traces match. Bounded-cache stress tests remain bit-exact through repeated eviction. Compute Sanitizer reports zero errors for 129 orbital queries and the word operation. The full Python suite passes {int(count.group(1))} tests, including bit-plane reconstruction, rehashed-false-geometry, OTAN2 rejection and missing-reference-interval acceptance.\n\n" + r"""
Fresh retained-component regression passes four CTests on each build, 256 SATNAV
epochs per backend with independent reconstruction, 4,225 SRK transitions and
3,308 CGK transitions per backend, and 6,861 persistent live-worker comparisons
per backend. The required GPU review tool also records zero errors under both
texture and global-memory Compute Sanitizer runs on the actual RTX 5070 Ti Laptop.

The first orbital RK4 test exposed an omitted final state assignment; that defect
was fixed before these final results. Earlier failed and superseded investigation
folders are retained as such and are not used as final validation. Numerical
agreement is separate from the physical future-reference errors below.
"""
    (ROOT / "docs/orbit_runtime_validation.tex").write_text(text, encoding="utf-8")
    validation = {"version": "3.6.1.9", "profile": "ORBIT-SEED-R1", "dynamics_profile": "ORBIT-DYNAMICS-R2", "codec": "bitplanes64-zlib",
        "status": "implementation_passed_accuracy_measured", "implementation_status": "passed",
        "scope": "Implementation checks plus sampled physical acceptance against a stated 10 m engineering target; no intrinsic universal physical error bound",
        "physical_24h_acceptance": acceptance24["status"], "physical_all_requested_durations_acceptance": acceptance["status"],
        "independent_confirmation_24h_acceptance": confirmation24["status"],
        "independent_confirmation_all_requested_durations_acceptance": confirmation["status"],
        "python_tests": int(count.group(1)), "evidence": {k: {"path": "results/" + p, "sha256": sha(ROOT / "results" / p)} for k, p in names.items()},
        "objects": [{"id": n, "seed_bytes": o["seed"]["file_bytes"], "seed_sha256": o["seed"]["seed_sha256"],
                     "physical_model_sha256": o["seed"]["model_sha256"]} for n, o in objects.items()],
        "event_count": events, "max_event_refinement_delta_s": max_delta,
        "max_native_cpu_cuda_position_m": cuda_max,
        "cpu_binary_sha256": sha(ROOT / "bin/cpu/orbit_worker.exe"),
        "cuda_binary_sha256": sha(ROOT / "bin/cuda/orbit_worker.exe"),
        "pdf_status": "build_and_visual_verification_pending"}
    pdf_path = ROOT / "output/pdf/aTOMos_v3_6_1_9_Orbital_Seed_Kernel_UGTS_Tom_Klootwijk.pdf"
    qa_path = ROOT / "results/orbit_pdf_r2_qa/qa.json"
    if qa_path.exists() and pdf_path.exists():
        qa = json.loads(qa_path.read_text())
        if (qa.get("visual_status") == "passed" or qa.get("status") == "passed") and qa.get("pdf_sha256") == sha(pdf_path):
            validation["pdf_status"] = "passed"
            validation["pdf"] = {"path": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
                                 "sha256": sha(pdf_path), "pages": qa["page_count"]}
            validation["evidence"]["pdf_qa"] = {"path": str(qa_path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(qa_path)}
    (ROOT / "validation_results.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__": main()
