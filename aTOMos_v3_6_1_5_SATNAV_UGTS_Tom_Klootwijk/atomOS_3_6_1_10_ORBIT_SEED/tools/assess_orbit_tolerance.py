#!/usr/bin/env python3
"""Explicit physical-position acceptance against measured later reference samples.

This does not adjust a model, hide failing epochs or transform the numerical
CPU/CUDA tolerance into physical accuracy. It reports every requested duration.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path


def assess(accuracy_path, budget_m=10., hours=(.25, 1., 6., 24., 72., 168.)):
    if not math.isfinite(budget_m) or budget_m <= 0: raise ValueError("Positive finite budget required")
    evidence = json.loads(Path(accuracy_path).read_text())
    if evidence.get("status") != "measured": raise ValueError("Complete measured accuracy report required")
    if not evidence.get("objects"): raise ValueError("Measured objects required")
    report = {"profile": "ORBIT-PHYSICAL-ACCEPTANCE-R1", "budget_m": budget_m,
              "budget_origin": "Explicit engineering acceptance budget; separate from native functional tolerances",
              "reference_sampling": "Discrete external product epochs; no continuous-time or true-orbit guarantee",
              "source_report_sha256": hashlib.sha256(Path(accuracy_path).read_bytes()).hexdigest(), "objects": []}
    for obj in evidence["objects"]:
        path = Path(accuracy_path).parent / obj["curve_file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != obj["curve_sha256"]:
            raise ValueError("Reference curve bytes differ from report")
        with path.open(newline="") as stream: rows = list(csv.DictReader(stream))
        times = [float(r["seconds_after_cutoff"]) for r in rows]
        errors = [float(r["position_error_m"]) for r in rows]
        if len(times) < 2 or any(not math.isfinite(v) for v in times + errors) or any(b <= a for a, b in zip(times, times[1:])) or times[0] <= 0 or any(e < 0 for e in errors):
            raise ValueError("Invalid chronological finite measurement curve")
        nominal_gap = statistics.median(b - a for a, b in zip(times, times[1:]))
        trials = []
        for horizon in hours:
            end = float(horizon) * 3600.
            if not math.isfinite(end) or end <= 0: raise ValueError("Positive horizon required")
            indices = [i for i, t in enumerate(times) if 0 < t <= end]
            sample_gaps = [times[0]] + [times[i] - times[i - 1] for i in indices if i > 0]
            covered = bool(indices) and end - times[indices[-1]] <= 1.01 * nominal_gap and max(sample_gaps) <= 1.01 * nominal_gap
            maximum = max((errors[i] for i in indices), default=None)
            worst = max(indices, key=lambda i: errors[i]) if indices else None
            trials.append({"requested_hours": horizon, "samples": len(indices), "last_tested_seconds": times[indices[-1]] if indices else None,
                           "max_error_m": maximum, "worst_sample_seconds": times[worst] if worst is not None else None,
                           "coverage_complete_at_nominal_cadence": covered, "nominal_sample_gap_seconds": nominal_gap,
                           "maximum_gap_in_prefix_seconds": max(sample_gaps),
                           "status": "failed" if maximum is not None and maximum > budget_m else "passed_at_tested_samples" if covered else "insufficient_coverage",
                           "margin_m": budget_m - maximum if maximum is not None else None})
        first = next((i for i, e in enumerate(errors) if e > budget_m), None)
        report["objects"].append({"object_id": obj["object_id"], "physical_model_sha256": obj["physical_model_sha256"],
            "first_sample_exceedance_seconds": times[first] if first is not None else None,
            "previous_sample_seconds": times[first - 1] if first is not None and first else None,
            "maximum_over_full_test_window_m": max(errors), "durations": trials})
    report["all_requested_durations_within_budget_at_samples"] = all(t["status"] == "passed_at_tested_samples" for o in report["objects"] for t in o["durations"])
    report["status"] = "passed_at_tested_samples" if report["all_requested_durations_within_budget_at_samples"] else "not_met_for_all_requested_durations"
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--accuracy", type=Path, required=True)
    p.add_argument("--budget-m", type=float, default=10.)
    p.add_argument("--hours", type=float, nargs="+", default=[.25, 1., 6., 24., 72., 168.])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--require-all", action="store_true", help="Return failure when any requested duration exceeds the budget")
    args = p.parse_args()
    report = assess(args.accuracy, args.budget_m, args.hours)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream: json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({"status": report["status"], "budget_m": args.budget_m,
                      "objects": [{"object_id": o["object_id"], "durations": o["durations"]} for o in report["objects"]]}, indent=2))
    return int(args.require_all and not report["all_requested_durations_within_budget_at_samples"])


if __name__ == "__main__": raise SystemExit(main())
