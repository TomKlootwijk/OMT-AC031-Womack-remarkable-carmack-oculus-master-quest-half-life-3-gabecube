#!/usr/bin/env python3
"""Replay every preserved accuracy epoch and compare the frozen prediction bytes."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
RUNTIME_NAMES = ("orbit_seed", "orbit_native", "orbit_dynamics", "orbit_precision", "orbit_query")
START_SOURCE_SHA256 = {"python/" + n + ".py": hashlib.sha256((ROOT / "python" / (n + ".py")).read_bytes()).hexdigest()
                       for n in RUNTIME_NAMES}
from orbit_dynamics import state_to_ecef
from orbit_native import NativeOrbit
from orbit_seed import digest, load


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worker", type=Path, required=True)
    p.add_argument("--backend", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    sets = [("january", "seeds", "orbit_accuracy_r2_" + a.backend + "_verified"),
            ("february", "confirmation_seeds", "orbit_accuracy_confirmation_cpu_verified")]
    report = {"status": "running", "backend": a.backend, "worker_sha256": sha(a.worker),
              "scope": "Same frozen models and all archived reference epochs; no fitting or new reference claims", "objects": {}}
    for label, directory, previous in sets:
        for path in sorted((ROOT / "examples/orbit" / directory).glob("*.orbseed")):
            seed = load(path)
            name = seed["object"]["id"]
            source = ROOT / "results" / previous / (name + "_holdout.csv")
            with source.open(newline="") as f:
                rows = list(csv.DictReader(f))
            times = [float(r["seconds_after_cutoff"]) for r in rows]
            start = time.perf_counter()
            with NativeOrbit(a.worker, seed["model"], backend=a.backend) as native:
                replies = native.batch(times)
            mismatch, maximum, first_day = 0, 0., 0.
            for t, old, reply in zip(times, rows, replies):
                if reply.get("status") != "ok":
                    raise AssertionError(reply)
                state = reply["state_gcrs"]
                predicted = np.asarray(state[:3]) if old["reference_frame"] == "ICRF_geocentric" else np.asarray(state_to_ecef(seed["model"], t, state)[:3])
                before = np.array([float(old["predicted_" + k + "_m"]) for k in "xyz"])
                mismatch += int(struct.pack("<3d", *predicted) != struct.pack("<3d", *before))
                maximum = max(maximum, float(np.linalg.norm(predicted - before)))
                reference = np.array([float(old["reference_" + k + "_m"]) for k in "xyz"])
                if t <= 86400.:
                    first_day = max(first_day, float(np.linalg.norm(predicted - reference)))
            item = {"samples": len(rows), "model_sha256": digest(seed["model"]), "seed_sha256": sha(path),
                    "baseline_csv_sha256": sha(source), "baseline_csv": source.relative_to(ROOT).as_posix(),
                    "changed_prediction_rows": mismatch, "max_prediction_difference_m": maximum,
                    "first_day_max_reference_discrepancy_m": first_day, "elapsed_s": time.perf_counter() - start}
            # The February preserved predictions use CPU. Their CUDA comparison
            # therefore uses the existing 1 cm CPU/CUDA contract, not bit equality.
            if a.backend == "cpu" or label == "january":
                if mismatch:
                    raise AssertionError((label, name, "Frozen same-backend prediction changed", item))
            elif maximum > .01:
                raise AssertionError((label, name, "CPU/CUDA tolerance exceeded", item))
            if first_day > 10.:
                raise AssertionError((label, name, "First-day adopted budget exceeded", item))
            report["objects"][label + ":" + name] = item
            (a.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
            print(label, name, len(rows), maximum, flush=True)
    report["status"] = "passed"
    report["total_samples"] = sum(x["samples"] for x in report["objects"].values())
    report["source_sha256"] = START_SOURCE_SHA256
    report["source_sha256_at_completion"] = {"python/" + n + ".py": sha(ROOT / "python" / (n + ".py")) for n in RUNTIME_NAMES}
    if report["source_sha256"] != report["source_sha256_at_completion"]:
        report["status"] = "source_changed_during_execution"
    (a.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "passed":
        raise RuntimeError("Runtime source changed during replay; retain this evidence and rerun against a frozen source snapshot")
    print("passed", report["total_samples"], flush=True)


if __name__ == "__main__":
    main()
