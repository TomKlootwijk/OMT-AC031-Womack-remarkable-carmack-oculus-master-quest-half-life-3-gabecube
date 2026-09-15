#!/usr/bin/env python3
"""Verify packed-only replay, literal feedback, event refinement and timestamp scrubbing."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from orbit_native import NativeOrbit
from orbit_query import OrbitSession, record_digest, station_events
from orbit_seed import digest, inspect_bytes, load, pack_bytes, unpack_bytes
from verify_orbit_run import verify


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def isolated_probe(path, worker_path):
    """Child process denies every file read under the release directory.

    It receives only the packed seed, native binary and eight shared runtime
    modules in a system temporary directory. Numeric state never comes from the
    original examples, construction tables or reference trajectories.
    """
    with tempfile.TemporaryDirectory(prefix="atomos_seed_isolation_") as directory:
        tmp = Path(directory)
        modules = ["orbit_seed.py", "orbit_native.py", "orbit_dynamics.py", "orbit_precision.py", "orbit_query.py", "self_reference.py", "ugts.py", "geodesy.py"]
        for name in modules: shutil.copy2(ROOT / "python" / name, tmp / name)
        shutil.copy2(path, tmp / "input.orbseed")
        shutil.copy2(worker_path, tmp / "orbit_worker.exe")
        script = '''import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
denied=os.path.normcase(os.path.abspath(sys.argv[1]))+os.sep
def audit(event,args):
 if event=="open" and isinstance(args[0],(str,bytes,os.PathLike)):
  name=os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
  if name.startswith(denied):raise RuntimeError("Original release read forbidden: "+name)
sys.addaudithook(audit)
from orbit_seed import load,digest
from orbit_native import NativeOrbit
from orbit_query import OrbitSession
base=Path(__file__).resolve().parent;s=load(base/"input.orbseed")
with NativeOrbit(base/"orbit_worker.exe",s["model"]) as w:
 session=OrbitSession(s,w)
 rows=[session.query(t) for t in [0.,12345.678,s["query"]["end_s"],-123.45]]
 print(json.dumps({"seed_sha256":digest(s),"rows":[{"time_s":r["time_s"],"state":r["state_gcrs_m_mps"]} for r in rows],"original_release_reads":"denied_by_audit_hook"}))
'''
        (tmp / "probe.py").write_text(script, encoding="utf-8")
        completed = subprocess.run([sys.executable, "-I", str(tmp / "probe.py"), str(ROOT)], cwd=tmp,
                                   text=True, capture_output=True, timeout=60, check=True)
        result = json.loads(completed.stdout)
        result["shared_runtime_source_bytes"] = sum((tmp / name).stat().st_size for name in modules)
        result["shared_native_worker_bytes"] = (tmp / "orbit_worker.exe").stat().st_size
        result["shared_dependency_scope"] = "Python, NumPy/SciPy and OS/C++ runtime are installed shared dependencies, not charged as per-seed bytes"
        return result


def run(args):
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "objects": {}, "seed_format": "ORBIT-SEED-R1",
              "accuracy_scope": "Encoding, execution, feedback and visibility algorithms; real forecast accuracy is a separate report"}
    for path in sorted(args.seeds.glob("*.orbseed")):
        seed = load(path); name = seed["object"]["id"]
        seed_report = inspect_bytes(path.read_bytes())
        if pack_bytes(unpack_bytes(path.read_bytes())) != path.read_bytes(): raise ValueError("Nonexact seed round trip")
        isolation = isolated_probe(path, args.worker)
        with NativeOrbit(args.worker, seed["model"]) as worker:
            session = OrbitSession(seed, worker)
            baseline = {row["time_s"]: row["state"] for row in isolation["rows"]}
            for t, state in baseline.items():
                if session.query(t)["state_gcrs_m_mps"] != state: raise ValueError("Isolated reconstruction differs")
            # Alternating far/near fractional queries exercise nonmonotonic seeking.
            times = [0., 604799.875, 12.25, 90000.125, -321.75, 12345.678, 300., 1.] * 3
            canonical = {}
            cold_ms, warm_ms, steps = [], [], []
            worker.reset()
            for t in times:
                before = time.perf_counter(); row = session.query(t); elapsed = (time.perf_counter() - before) * 1000
                if t in canonical:
                    if row["state_gcrs_m_mps"] != canonical[t]: raise ValueError("Scrub order changes physical state")
                    warm_ms.append(elapsed)
                else:
                    canonical[t] = row["state_gcrs_m_mps"]; cold_ms.append(elapsed)
                steps.append(row["native"]["rk_steps"])
            scrub = {"queries": len(times), "unique_fractional_times": len(canonical),
                     "bit_exact_on_repeated_timestamp": True, "cold_max_end_to_end_ms": max(cold_ms),
                     "warm_max_end_to_end_ms": max(warm_ms), "rk_steps_per_query": steps, "cache": worker.stats()}
            # Ordered schedule is driven by native q; a changed literal JK equation selects fine cadence.
            records = list(session.schedule(0., 86400.))
            altered = deepcopy(seed)
            altered["feedback"]["equations"].update(j="1", k="0")
            other = list(OrbitSession(altered, worker).schedule(0., 86400.))
            if [r["time_s"] for r in records] == [r["time_s"] for r in other]:
                raise ValueError("Counterfactual JK equations failed to change actual schedule")
            common = {r["time_s"]: r["state_gcrs_m_mps"] for r in records}
            comparisons = 0
            for row in other:
                if row["time_s"] in common:
                    if row["state_gcrs_m_mps"] != common[row["time_s"]]: raise ValueError("q changed orbital dynamics")
                    comparisons += 1
            run_dir = args.out / (name + "_schedule")
            run_dir.mkdir()
            with (run_dir / "trace.jsonl").open("x", encoding="utf-8") as stream:
                for row in records: stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
            write_json(run_dir / "summary.json", {"seed": seed_report, "station": session.station,
                "queries": len(records), "start_s": 0., "end_s": 86400.,
                "final_record_sha256": records[-1]["record_sha256"]})
            write_json(run_dir / "counterfactual.json", {"equations": altered["feedback"]["equations"],
                "original_queries": len(records), "counterfactual_queries": len(other),
                "common_timestamp_orbit_comparisons": comparisons, "common_physical_states_bit_exact": True})
            # Include an absorbed second-set example with an independently compiled literal recurrence.
            absorbed = deepcopy(seed)
            absorbed["feedback"]["sets"][1]["boundary_mask"] = 8
            absorption_trace = list(OrbitSession(absorbed, worker).schedule(0., 3600.))
            write_json(run_dir / "second_set_absorption.json", {"mask_set_b": absorbed["feedback"]["sets"][1],
                "queries": len(absorption_trace), "hits": sum(r["feedback"]["stage_b"]["hits"] for r in absorption_trace),
                "trace": [{"time_s": r["time_s"], "feedback": r["feedback"]} for r in absorption_trace]})
            event_reports = []
            for station in seed["stations"]:
                event_session = OrbitSession(seed, worker, station["id"])
                coarse = station_events(event_session, 0., 604800., 120.)
                dense = station_events(event_session, 0., 604800., 30.)
                if [e["kind"] for e in coarse["events"]] != [e["kind"] for e in dense["events"]]:
                    raise ValueError("Event count/type differs under fourfold sampling refinement")
                differences = [abs(a["time_s"] - b["time_s"]) for a, b in zip(coarse["events"], dense["events"])]
                if max(differences, default=0.) > .05: raise ValueError("Event times fail refinement check")
                event_reports.append({"station": station, "coarse": coarse, "dense": dense,
                                      "max_event_time_difference_s": max(differences, default=0.)})
                print(name + " " + station["id"] + " seven-day event refinement passed", flush=True)
            write_json(args.out / (name + "_events.json"), event_reports)
        independent = verify(seed, run_dir, args.worker)
        write_json(run_dir / "independent_verification.json", independent)
        # 2017 samples, each timestamp plus six FP64 state components. Station/full trace output is larger.
        output_bytes = 2017 * 7 * 8
        result = {"seed": seed_report, "isolation": isolation, "scrubbing": scrub,
                  "feedback": {"original_queries": len(records), "counterfactual_queries": len(other),
                               "common_time_states_equal": comparisons}, "independent_run": independent,
                  "event_searches": [{"station": r["station"]["id"], "classification": r["coarse"]["classification"],
                                      "events": len(r["coarse"]["events"]), "max_refinement_time_delta_s": r["max_event_time_difference_s"]} for r in event_reports],
                  "storage_comparison": {"seven_day_300s_fp64_time_state_bytes": output_bytes,
                    "seed_bytes": len(path.read_bytes()), "state_table_to_seed_ratio": output_bytes / len(path.read_bytes()),
                    "scope": "Time+6state table vs complete seed; no claim of compressing arbitrary trajectories into initial conditions"}}
        report["objects"][name] = result
        write_json(args.out / (name + "_seed_validation.json"), result)
        print(name + " seed, isolation, scrubbing, feedback and events passed", flush=True)
    if len(report["objects"]) != 4: raise ValueError("Expected all four demonstration orbit classes")
    report["status"] = "passed"
    write_json(args.out / "summary.json", report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=Path, default=ROOT / "examples/orbit/seeds")
    p.add_argument("--worker", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    try: run(args)
    except Exception as exc:
        if args.out.exists():
            (args.out / "failure.json").write_text(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        raise


if __name__ == "__main__": main()
