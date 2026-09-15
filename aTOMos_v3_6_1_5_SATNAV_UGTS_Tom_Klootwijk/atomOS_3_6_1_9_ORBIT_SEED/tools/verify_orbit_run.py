#!/usr/bin/env python3
"""Independent ordered AST replay and fresh native reconstruction of an orbital trace."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from orbit_native import NativeOrbit
from orbit_query import OrbitSession, predicate_word, record_digest
from orbit_seed import digest, load, transition_ast
from ugts import otan2_source, wrap


def compare_value(expected, actual, key, tolerance):
    if type(expected) is dict:
        if type(actual) is not dict or set(actual) != set(expected): raise ValueError("Trace field shape differs: " + key)
        for k in expected: compare_value(expected[k], actual[k], key + "." + k, tolerance)
    elif type(expected) is list:
        if type(actual) is not list or len(actual) != len(expected): raise ValueError("Trace field shape differs: " + key)
        for a, b in zip(expected, actual): compare_value(a, b, key, tolerance)
    elif type(expected) is float:
        if type(actual) not in (float, int) or not math.isfinite(actual) or abs(actual - expected) > tolerance:
            raise ValueError("Trace numeric field differs: " + key)
    elif type(actual) is not type(expected) or actual != expected:
        raise ValueError("Trace field differs: " + key)


def verify(seed, run_dir, worker_path, backend="cpu"):
    summary = json.loads((run_dir / "summary.json").read_text())
    if summary["seed"]["seed_sha256"] != digest(seed): raise ValueError("Summary seed differs")
    q, t, previous, count = seed["feedback"]["q0"], summary["start_s"], "0" * 64, 0
    previous_chart = None
    max_error = 0.
    with NativeOrbit(worker_path, seed["model"], backend) as worker:
        session = OrbitSession(seed, worker, summary["station"]["id"])
        with (run_dir / "trace.jsonl").open() as stream:
            for line in stream:
                if count and t == summary["end_s"] and finished: raise ValueError("Extra trace row after endpoint")
                row = json.loads(line)
                if row["index"] != count or row["time_s"] != t: raise ValueError("Trace schedule/index differs from independent recurrence")
                if row["previous_sha256"] != previous or row["record_sha256"] != record_digest(row):
                    raise ValueError("Trace chain or content digest mismatch")
                predicted = session.query(t)
                if row["seed_sha256"] != session.seed_hash or row["model_sha256"] != session.model_hash:
                    raise ValueError("Trace seed/model identity differs")
                error = math.dist(predicted["state_gcrs_m_mps"][:3], row["state_gcrs_m_mps"][:3])
                velocity_error = math.dist(predicted["state_gcrs_m_mps"][3:], row["state_gcrs_m_mps"][3:])
                if error > .002 or velocity_error > 1.e-6: raise ValueError("Fresh native reconstruction differs")
                max_error = max(max_error, error)
                for key in predicted:
                    if key == "native": continue
                    tolerance = .002 if key in ("state_gcrs_m_mps", "ecef_m", "enu_m", "station_ecef_m", "up_m", "range_m") else 1.e-6 if key in ("range_rate_m_s", "ecef_velocity_m_s", "enu_velocity_m_s") else 1.e-9
                    if key not in row: raise ValueError("Missing trace field: " + key)
                    compare_value(predicted[key], row[key], key, tolerance)
                otan = {"status": "no_previous_chart", "value": None}
                chart = predicted["chart"]
                if previous_chart and chart["status"] == previous_chart["status"] == "defined":
                    otan = otan2_source(wrap(chart["theta_rad"] - previous_chart["theta_rad"]), chart["rho"] - previous_chart["rho"])
                compare_value(otan, row["otan2_source"], "otan2_source", 1.e-10)
                previous_chart = chart
                drive = predicate_word(seed["feedback"], predicted, t, session.station)
                expected = transition_ast(seed["feedback"], q, drive)
                actual = row["feedback"]
                if set(actual) != {"type", "before", "drive", "x", "stage_a", "stage_b", "j", "k", "after"} or actual["type"] != "transition":
                    raise ValueError("Unexpected native transition schema")
                if row["feedback_independent_ast"] != expected: raise ValueError("Recorded independent AST differs")
                for key in ("before", "drive", "x", "j", "k", "after"):
                    if actual[key] != expected[key]: raise ValueError("Native recurrence differs: " + key)
                for label, stage in zip(("stage_a", "stage_b"), expected["stages"]):
                    if any(actual[label][k] != stage[k] for k in ("asa", "na", "hits", "output")):
                        raise ValueError("Whole-word stage differs: " + label)
                q = expected["after"]
                cadence = seed["feedback"]["cadence"]
                next_dt = cadence["fine_s"] if q & cadence["fine_bits"] else cadence["coarse_s"]
                if row["chosen_next_dt_s"] != next_dt: raise ValueError("Feedback did not control cadence")
                previous, count = row["record_sha256"], count + 1
                finished = t == summary["end_s"]
                if not finished: t = min(summary["end_s"], t + next_dt)
        if count != summary["queries"] or not count or not finished or previous != summary["final_record_sha256"]:
            raise ValueError("Trace incomplete or final chain differs")
        return {"status": "passed", "queries": count, "max_fresh_position_difference_m": max_error,
                "seed_sha256": digest(seed), "final_record_sha256": previous,
                "scope": "Independent AST schedule, full mask stages, keys/time/geometry and fresh native state; physical accuracy validated separately"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--worker", type=Path, required=True)
    p.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    report = verify(load(args.seed), args.run, args.worker, args.backend)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream: json.dump(report, stream, indent=2)
    print(json.dumps(report))


if __name__ == "__main__": main()
