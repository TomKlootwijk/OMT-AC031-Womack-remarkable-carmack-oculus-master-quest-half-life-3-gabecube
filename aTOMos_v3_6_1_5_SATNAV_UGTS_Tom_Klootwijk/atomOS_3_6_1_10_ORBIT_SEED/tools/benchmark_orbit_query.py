"""Compare query preparation against unchanged R9 using one fixed native adapter.

This isolates Python query/frame/feedback work from separate native-kernel changes.
Both child processes receive exactly the same R9 numerical seed and native binary.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time


def child(release, baseline, worker, repeats):
    sys.path.insert(0, str(release / "python"))
    import numpy as np
    from orbit_dynamics import frame_matrix, state_to_ecef
    from orbit_query import OrbitSession, station_geometry
    from orbit_seed import _encode, digest, feedback_luts, transition_ast
    # Fixed adapter/protocol makes this a Python-overhead comparison, even if
    # the new release adds transport features incompatible with the R9 worker.
    spec = importlib.util.spec_from_file_location("fixed_r9_native", baseline / "python/orbit_native.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    seeds = {name: json.loads((baseline / "examples/orbit/seeds" / (name + ".json")).read_text(encoding="utf-8"))
             for name in ("G05", "C03", "C06", "CHANDRA")}
    def signature(value): return hashlib.sha256(_encode(value)).hexdigest()
    def timed(fn, before=None):
        durations = []; result = None
        for _ in range(repeats):
            if before is not None: before()
            begin = time.perf_counter(); result = fn(); durations.append(time.perf_counter() - begin)
        return {"seconds": durations, "median_seconds": statistics.median(durations), "output_sha256": signature(result)}
    report = {"release": str(release), "scope": __doc__, "workloads": {}, "objects": {}}
    seed = seeds["G05"];model = seed["model"];state = model["state_gcrs"];feedback = seed["feedback"]
    times = np.linspace(-691200., 604800., 257).tolist()
    times += [s["t0_s"] for s in model["frame"]["eop_segments"] if model["domain_s"][0] <= s["t0_s"] <= model["domain_s"][1]]
    report["workloads"]["frame_state_272_times"] = timed(lambda: [state_to_ecef(model, t, state).tolist() for t in times])
    report["workloads"]["station_geometry_512_calls"] = timed(lambda: [station_geometry(model, (i % 128) * 600., state, seed["stations"][i % 2]) for i in range(512)])
    report["workloads"]["feedback_2000_transitions"] = timed(lambda: [[feedback_luts(feedback), transition_ast(feedback, i % 32, (7 * i) % 32)] for i in range(2000)])
    def stable(row): return {key: value for key, value in row.items() if key != "native"}
    for name, seed in seeds.items():
        with adapter.NativeOrbit(worker, seed["model"]) as native:
            # The unchanged R9 adapter predates the explicit snapshot digest.
            # Bind the known, unmodified construction input for this comparison.
            native.model_sha256 = digest(seed["model"])
            session = OrbitSession(seed, native)
            queries = [0., 86400., 12.25, 90000.125, -321.75, 12345.678, 300., 1.] * 32
            probe = timed(lambda: [stable(session.query(t)) for t in queries], native.reset)
            schedule = timed(lambda: [stable(row) for row in session.schedule(0., 86400.)], native.reset)
            report["objects"][name] = {"query_256": probe, "schedule_24h": schedule}
    report["source_sha256"] = {name: hashlib.sha256((release / "python" / name).read_bytes()).hexdigest()
                                for name in ("orbit_query.py", "orbit_seed.py", "orbit_dynamics.py", "orbit_precision.py")}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--child", type=Path)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(child(args.child.resolve(), args.baseline.resolve(), args.worker.resolve(), args.repeats)))
        return
    results = {}
    for label, release in (("baseline", args.baseline), ("current", args.current)):
        cmd = [sys.executable, str(Path(__file__).resolve()), "--baseline", str(args.baseline.resolve()),
               "--worker", str(args.worker.resolve()), "--child", str(release.resolve()), "--repeats", str(args.repeats)]
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode: raise RuntimeError(completed.stderr)
        results[label] = json.loads(completed.stdout)
    comparisons = {}
    for label in results["baseline"]["workloads"]:
        a, b = (results[k]["workloads"][label] for k in ("baseline", "current"))
        comparisons[label] = {"speedup": a["median_seconds"] / b["median_seconds"], "output_exact": a["output_sha256"] == b["output_sha256"]}
    for name in results["baseline"]["objects"]:
        for label in ("query_256", "schedule_24h"):
            a, b = (results[k]["objects"][name][label] for k in ("baseline", "current"))
            comparisons[name + "_" + label] = {"speedup": a["median_seconds"] / b["median_seconds"], "output_exact": a["output_sha256"] == b["output_sha256"]}
    results["comparisons"] = comparisons
    results["native_binary_sha256"] = hashlib.sha256(args.worker.read_bytes()).hexdigest()
    results["status"] = "passed" if all(row["output_exact"] for row in comparisons.values()) else "failed"
    if args.out is None: parser.error("--out is required for comparison")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": results["status"], "comparisons": comparisons}, indent=2))
    if results["status"] != "passed": raise SystemExit("Query output differs from R9")


if __name__ == "__main__": main()
