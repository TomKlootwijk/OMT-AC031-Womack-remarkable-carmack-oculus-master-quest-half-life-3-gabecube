#!/usr/bin/env python3
"""Measure SPK reconstruction of frozen aTOMos forecasts, never SPICE prediction.

The protocol is written before native state evaluation. No future observation
file is read. State sample spacing and polynomial degree are a declared grid,
not fitted against the resulting interpolation errors.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
R10 = ROOT.parent / "atomOS_3_6_1_10_ORBIT_SEED"
SATELLITES = {"G05": "MEO", "C03": "GEO", "C06": "IGSO", "CHANDRA": "HEO"}
LSK_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls"
LSK_SHA = "678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b"
TT_GPS_OFFSET_S = 51.184
GPS_EPOCH_FROM_J2000_S = (2444244.5 - 2451545.0) * 86400.0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path):
    path = Path(path).resolve()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def stats(np, values):
    v = np.asarray(values, dtype=float)
    if not len(v) or not np.all(np.isfinite(v)):
        raise ValueError("Statistics require nonempty finite values")
    return {"count": len(v), "rms": float(np.sqrt(np.mean(v*v))),
            "median": float(np.median(v)), "p95": float(np.quantile(v, .95)),
            "max": float(np.max(v))}


def setup_spice(args):
    sys.path.insert(0, str(args.python_dependencies))
    import spiceypy as spice
    from spiceypy.utils.libspicehelper import libspice_path
    if not args.lsk.exists():
        args.lsk.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(LSK_URL, timeout=60) as response:
            args.lsk.write_bytes(response.read())
    if sha(args.lsk) != LSK_SHA:
        raise ValueError("The pinned NAIF LSK differs; do not silently change the protocol")
    spice.kclear()
    spice.furnsh(str(args.lsk.resolve()))
    return spice, {"SpiceyPy": spice.__version__, "CSPICE": spice.tkvrsn("TOOLKIT"),
                   "cspice_library": pin(libspice_path),
                   "spiceypy_interface": pin(Path(spice.__file__).parent / "spiceypy.py"),
                   "lsk": {**pin(args.lsk), "source": LSK_URL}}


def time_coordinates(np, spice, epoch_gpst, offsets):
    # Integer-day epoch differences avoid cancellation from first summing a
    # full Julian date. The remaining ET double has about 0.12 us resolution.
    tt = (GPS_EPOCH_FROM_J2000_S + epoch_gpst) + TT_GPS_OFFSET_S + offsets
    et = np.asarray([spice.unitim(float(t), "TDT", "TDB") for t in tt])
    inverse = np.asarray([spice.unitim(float(t), "TDB", "TDT") for t in et])
    # The LSK defines TT=ET-K*sin(E), E=M+EB*sin(M), M=M0+M1*ET.
    # Velocities must be derivatives w.r.t. ET in an SPK, not TT/GPST.
    k = float(spice.gdpool("DELTET/K", 0, 1)[0])
    eb = float(spice.gdpool("DELTET/EB", 0, 1)[0])
    m0, m1 = spice.gdpool("DELTET/M", 0, 2)
    m = m0 + m1*et
    e = m + eb*np.sin(m)
    dtt_det = 1.0 - k*np.cos(e)*m1*(1.0 + eb*np.cos(m))
    if not np.all(np.diff(et) > 0) or np.max(abs(inverse-tt)) > 2e-7:
        raise ValueError("SPICE time conversion order or round trip failed")
    return tt, et, dtt_det, float(np.max(abs(inverse-tt)))


def spice_states(np, spice, body, epochs, derivative):
    states, _ = spice.spkezr(str(body), epochs, "J2000", "NONE", "399")
    states = np.asarray(states, dtype=float) * 1000.0
    states[:, 3:] /= derivative[:, None]
    if states.shape != (len(epochs), 6) or not np.all(np.isfinite(states)):
        raise ValueError("Malformed SPICE state result")
    return states


def native_states(np, worker, offsets):
    rows = worker.batch(offsets)
    if any(row.get("status") != "ok" for row in rows):
        raise ValueError("Native worker returned a failed query")
    states = np.asarray([row["state_gcrs"] for row in rows], dtype=float)
    if states.shape != (len(offsets), 6) or not np.all(np.isfinite(states)):
        raise ValueError("Malformed native state result")
    return states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-dependencies", type=Path, default=Path("C:/aTOMosBuild/orbitdeps/python"))
    parser.add_argument("--lsk", type=Path, default=Path("C:/aTOMosBuild/orbitdeps/naif0012.tls"))
    parser.add_argument("--output", type=Path, default=ROOT / "review/r18_spice_comparison.json")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("At least one timing repeat is required")
    sys.path.insert(0, str(args.python_dependencies))
    import numpy as np
    import erfa
    sys.path.insert(0, str(R10 / "python"))
    from orbit_native import NativeOrbit
    worker_path = R10 / "bin/cpu/orbit_worker.exe"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    artifact_dir = args.output.parent / "r18_spice_data"
    artifact_dir.mkdir(exist_ok=True)
    spice, dependencies = setup_spice(args)
    copied_lsk = artifact_dir / "naif0012.tls"
    shutil.copyfile(args.lsk, copied_lsk)
    input_paths = [(label, folder, sat, R10 / "examples/orbit" / folder / (sat + ".json"))
                   for label, folder in (("2025-01-02", "precision_models"),
                                         ("2025-02-02", "confirmation_models"))
                   for sat in SATELLITES]
    protocol = {
        "profile": "ATOMOS-SPICE-EPHEMERIS-COMPARISON-R1",
        "frozen_before_evaluation_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "SPK representation and query of the same frozen forecast, not independent physical accuracy or forward propagation by SPICE",
        "horizon_s": 604800, "native_reference_grid_s": 150,
        "node_spacing_s": [300, 900, 1800], "spk_degrees": [7, 9, 15],
        "query_design": "Every midpoint between adjacent input nodes, plus every node as a preservation check; no extrapolation",
        "model_fit": "No fitting or model changes; both historical periods were inspected in earlier releases and are reused",
        "observations": "None read. Every SPK input state is computed by the same frozen native model at its declared epoch",
        "time": "GPST+51.184 s gives TT; CSPICE UNITIM with pinned NAIF LSK converts TT to TDB seconds past J2000. SPK velocity uses dTT/dTDB from that same LSK; outputs are converted back",
        "frame": "Earth-centered model GCRS numerical axes transported under identity orientation to the SPICE J2000 label; no independent relativistic GCRS/ICRF coordinate transformation or physical frame validation is claimed",
        "units": "Model m and m/s; SPK km and km/TDB-second; comparison m and m/GPST-second",
        "aberration": "NONE; geometric state relative to Earth, no light-time or stellar aberration",
        "timing": {"repeats": args.repeats, "case": "300 s, degree 9",
                   "order": "Deterministic shuffled midpoint epochs, seed 1809; alternating native/SPICE order between repeats",
                   "scope": "Warm full Python APIs: native persistent-worker BATCH IPC/JSON plus remaining RK4 steps, versus SpiceyPy SPKEZR iterable API plus CSPICE SPK query. Epoch conversion and input precomputation excluded from warm query times and reported separately",
                   "limits": "Different algorithms/storage and interfaces; not matched arithmetic, native GPU throughput, or a superiority claim. Host load is uncontrolled"},
        "inputs": [dict(period=label, satellite=sat, **pin(path)) for label, _, sat, path in input_paths],
        "native_worker": pin(worker_path),
        "harness": pin(__file__),
        "python_adapters": [pin(R10 / "python" / name) for name in
                            ("orbit_native.py", "orbit_dynamics.py", "orbit_precision.py", "orbit_seed.py")],
        "dependencies": dependencies,
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "numpy": np.__version__, "pyerfa": erfa.__version__},
        "references": ["https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/spkw09_c.html",
                       "https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/unitim_c.html",
                       LSK_URL]}
    protocol_path = args.output.parent / "r18_spice_protocol.json"
    write_json(protocol_path, protocol)
    results = {"profile": protocol["profile"], "protocol": pin(protocol_path),
               "started_utc": datetime.now(timezone.utc).isoformat(), "cases": [], "models": [],
               "scope": protocol["purpose"], "complete": False}
    write_json(args.output, results)
    grid = np.arange(0., 604800. + 150., 150.)
    body_base = -1800000
    try:
        for model_index, (label, folder, sat, path) in enumerate(input_paths):
            model = json.loads(path.read_text(encoding="utf-8"))["model"]
            if model["profile"] != "ORBIT-DYNAMICS-R2" or model["domain_s"][1] < grid[-1]:
                raise ValueError("Frozen model does not cover the declared protocol")
            start_time = time.perf_counter()
            tt, et, derivative, roundtrip = time_coordinates(np, spice, model["epoch_gpst_s"], grid)
            # Geocentric SOFA model differs from the shorter CSPICE LSK series;
            # report disagreement rather than silently mixing conventions.
            erfa_delta = erfa.dtdb(2451545., tt/86400., 0., 0., 0., 0.)
            delta_error = (et-tt)-erfa_delta
            time_wall = time.perf_counter()-start_time
            with NativeOrbit(worker_path, model) as worker:
                start_time = time.perf_counter()
                reference = native_states(np, worker, grid)
                propagation_wall = time.perf_counter()-start_time
                npz_path = artifact_dir / f"{label}_{sat}_frozen_native.npz"
                np.savez_compressed(npz_path, offsets_gpst_s=grid, tt_j2000_s=tt,
                                    et_tdb_j2000_s=et, dtt_det=derivative, state_gcrs_m=reference)
                model_result = {"period": label, "satellite": sat, "orbit_class": SATELLITES[sat],
                                "model_sha256": worker.model_sha256, "input": pin(path),
                                "native_states": pin(npz_path), "state_count": len(grid),
                                "native_reference_evaluation_wall_s": propagation_wall,
                                "time_conversion_wall_s": time_wall,
                                "time_conversion_roundtrip_max_s": roundtrip,
                                "spice_minus_erfa_tdb_tt_s": stats(np, abs(delta_error)),
                                "epoch_json_jd_tt_rounding_s": float((model["epoch_jd_tt"]-2451545.)*86400.-tt[0]),
                                "spk_time_rate_max_difference_from_one": float(np.max(abs(derivative-1.))),
                                "initial_native_stats": worker.stats()}
                results["models"].append(model_result)
                print(f"{label} {sat}: native grid {len(grid)}, {propagation_wall:.3f} s", flush=True)
                for spacing in protocol["node_spacing_s"]:
                    stride = spacing // 150
                    node_indices = np.arange(0, len(grid), stride)
                    query_indices = np.arange(stride//2, len(grid)-1, stride)
                    nodes = reference[node_indices].copy() / 1000.
                    nodes[:, 3:] *= derivative[node_indices, None]
                    for degree in protocol["spk_degrees"]:
                        body = body_base-model_index*100-spacing//300*10-degree
                        spk_path = artifact_dir / f"{label}_{sat}_{spacing}s_d{degree}.bsp"
                        if spk_path.exists():
                            # Only this exact, task-owned output file is replaced.
                            spk_path.unlink()
                        start_time = time.perf_counter()
                        handle = spice.spkopn(str(spk_path.resolve()), "aTOMos R18 frozen model", 0)
                        try:
                            spice.spkw09(handle, body, 399, "J2000", float(et[0]), float(et[-1]),
                                         f"R18 {label} {sat} {spacing} d{degree}", degree,
                                         len(nodes), nodes, et[node_indices])
                        finally:
                            spice.spkcls(handle)
                        build_wall = time.perf_counter()-start_time
                        spice.furnsh(str(spk_path.resolve()))
                        try:
                            actual = spice_states(np, spice, body, et[query_indices], derivative[query_indices])
                            node_actual = spice_states(np, spice, body, et[node_indices], derivative[node_indices])
                            position = np.linalg.norm(actual[:, :3]-reference[query_indices, :3], axis=1)
                            velocity = np.linalg.norm(actual[:, 3:]-reference[query_indices, 3:], axis=1)
                            node_error = np.linalg.norm(node_actual[:, :3]-reference[node_indices, :3], axis=1)
                            node_velocity_error = np.linalg.norm(node_actual[:, 3:]-reference[node_indices, 3:], axis=1)
                            if float(node_error.max()) > 1e-6 or float(node_velocity_error.max()) > 1e-9:
                                raise AssertionError("SPK failed to preserve its own native input nodes within transport rounding")
                            refused = []
                            for outside in (float(et[0]-1.), float(et[-1]+1.)):
                                try:
                                    spice.spkezr(str(body), outside, "J2000", "NONE", "399")
                                except spice.utils.exceptions.SpiceSPKINSUFFDATA:
                                    refused.append(True)
                                else:
                                    raise AssertionError("SPK unexpectedly extrapolated outside coverage")
                            worst = int(np.argmax(position))
                            case = {"period": label, "satellite": sat, "orbit_class": SATELLITES[sat],
                                    "spacing_s": spacing, "degree": degree,
                                    "input_nodes": len(nodes), "midpoint_queries": len(query_indices),
                                    "spk": pin(spk_path), "spk_write_wall_s": build_wall,
                                    "position_reconstruction_error_m": stats(np, position),
                                    "velocity_reconstruction_error_m_s": stats(np, velocity),
                                    "node_position_transport_error_m": stats(np, node_error),
                                    "node_velocity_transport_error_m_s": stats(np, node_velocity_error),
                                    "worst_midpoint_offset_s": float(grid[query_indices[worst]]),
                                    "outside_coverage_refused": all(refused),
                                    "per_day_max_position_error_m": [float(np.max(position[(grid[query_indices] > day*86400.) &
                                                                                                          (grid[query_indices] <= (day+1)*86400.)]))
                                                                           for day in range(7)]}
                            if spacing == 300 and degree == 9:
                                permutation = np.random.default_rng(1809).permutation(len(query_indices))
                                qi = query_indices[permutation]
                                # Untimed warmup of each complete interface.
                                native_states(np, worker, grid[qi])
                                spice_states(np, spice, body, et[qi], derivative[qi])
                                timings = []
                                for repeat in range(args.repeats):
                                    row = {"repeat": repeat+1}
                                    for which in (("native", "spice") if repeat % 2 == 0 else ("spice", "native")):
                                        start_time = time.perf_counter()
                                        measured = (native_states(np, worker, grid[qi]) if which == "native" else
                                                    spice_states(np, spice, body, et[qi], derivative[qi]))
                                        row[which + "_wall_s"] = time.perf_counter()-start_time
                                        expected = reference[qi] if which == "native" else actual[permutation]
                                        if not np.array_equal(measured, expected):
                                            raise AssertionError("Warm shuffled query output changed")
                                    timings.append(row)
                                case["warm_query_timing"] = {
                                    "queries": len(qi), "runs": timings,
                                    "native_wall_s_median": float(np.median([row["native_wall_s"] for row in timings])),
                                    "spice_wall_s_median": float(np.median([row["spice_wall_s"] for row in timings])),
                                    "qualification": protocol["timing"]["scope"] + ". " + protocol["timing"]["limits"]}
                            results["cases"].append(case)
                        finally:
                            spice.unload(str(spk_path.resolve()))
                model_result["final_native_stats"] = worker.stats()
                write_json(args.output, results)
    finally:
        spice.kclear()
    results["complete"] = True
    results["completed_utc"] = datetime.now(timezone.utc).isoformat()
    results["case_count"] = len(results["cases"])
    results["all_node_preservation_and_coverage_checks_passed"] = True
    results["artifacts"] = [pin(copied_lsk)]
    write_json(args.output, results)
    print(f"Completed {len(results['cases'])} cases: {args.output}", flush=True)


if __name__ == "__main__":
    main()
