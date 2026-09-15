"""Declared follow-up: denser SPK sampling after the coarse Chandra failures."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

REVIEW = Path(__file__).resolve().parent
sys.path.insert(0, str(REVIEW.parent / "tools"))
sys.path.insert(0, "C:/aTOMosBuild/orbitdeps/python")
from compare_spice_ephemeris import (R10, pin, write_json, setup_spice, time_coordinates,
                                     native_states, spice_states, stats)
import numpy as np
sys.path.insert(0, str(R10 / "python"))
from orbit_native import NativeOrbit


def main():
    args = SimpleNamespace(python_dependencies=Path("C:/aTOMosBuild/orbitdeps/python"),
                           lsk=Path("C:/aTOMosBuild/orbitdeps/naif0012.tls"))
    spice, dependencies = setup_spice(args)
    output = REVIEW / "r18_spice_chandra_refinement.json"
    artifact_dir = REVIEW / "r18_spice_data"
    paths = [(date, R10 / "examples/orbit" / folder / "CHANDRA.json") for date, folder in
             (("2025-01-02", "precision_models"), ("2025-02-02", "confirmation_models"))]
    protocol = {"profile": "ATOMOS-SPICE-CHANDRA-REFINEMENT-R1",
                "frozen_before_followup_evaluation_utc": datetime.now(timezone.utc).isoformat(),
                "reason": "Adaptive investigation after reading the original 72-case results: coarse fixed sampling failed near the eccentric orbit's fast motion. This is not a blind or preregistered confirmation of that first experiment",
                "previous_results": pin(REVIEW / "r18_spice_comparison.json"),
                "horizon_s": 604800, "native_reference_grid_s": 15,
                "node_spacing_s": [30, 60, 120], "spk_degrees": [9, 15],
                "target": "Document configurations whose sampled maximum position reconstruction error is <=0.001 m, <=0.01 m, <=0.1 m or <=1 m; no continuous guarantee",
                "scope": "Same frozen native Chandra model states; no external observations, refitting, physical accuracy claim or extrapolation",
                "time_frame_units": "Identical to r18_spice_protocol.json; native GPST/TT derivatives converted to ET derivatives and back, J2000 label is identity transport of model GCRS axes",
                "harness": pin(__file__),
                "shared_harness": pin(REVIEW.parent / "tools/compare_spice_ephemeris.py"),
                "inputs": [dict(period=date, **pin(path)) for date, path in paths],
                "worker": pin(R10 / "bin/cpu/orbit_worker.exe"), "dependencies": dependencies}
    protocol_path = REVIEW / "r18_spice_chandra_refinement_protocol.json"
    write_json(protocol_path, protocol)
    result = {"profile": protocol["profile"], "protocol": pin(protocol_path),
              "complete": False, "models": [], "cases": []}
    write_json(output, result)
    grid = np.arange(0., 604800. + 15., 15.)
    try:
        for index, (date, path) in enumerate(paths):
            model = json.loads(path.read_text(encoding="utf-8"))["model"]
            tt, et, derivative, roundtrip = time_coordinates(np, spice, model["epoch_gpst_s"], grid)
            with NativeOrbit(R10 / "bin/cpu/orbit_worker.exe", model) as worker:
                start = time.perf_counter()
                reference = native_states(np, worker, grid)
                evaluation_wall = time.perf_counter()-start
                print(f"{date} Chandra dense native grid {len(grid)}, {evaluation_wall:.3f} s", flush=True)
                npz_path = artifact_dir / f"{date}_CHANDRA_frozen_native_15s.npz"
                np.savez_compressed(npz_path, offsets_gpst_s=grid, et_tdb_j2000_s=et,
                                    dtt_det=derivative, state_gcrs_m=reference)
                coarse_path = artifact_dir / f"{date}_CHANDRA_frozen_native.npz"
                with np.load(coarse_path) as coarse:
                    if not np.array_equal(reference[::10], coarse["state_gcrs_m"]):
                        raise AssertionError("Denser native query grid changed existing reference states")
                result["models"].append({"period": date, "input": pin(path), "native_states": pin(npz_path),
                                         "state_count": len(grid), "native_evaluation_wall_s": evaluation_wall,
                                         "coarse_reference_preserved_exactly": True,
                                         "time_roundtrip_max_s": roundtrip})
                for spacing in protocol["node_spacing_s"]:
                    stride = spacing//15
                    ni = np.arange(0, len(grid), stride)
                    qi = np.arange(stride//2, len(grid)-1, stride)
                    nodes = reference[ni].copy()/1000.
                    nodes[:, 3:] *= derivative[ni, None]
                    for degree in protocol["spk_degrees"]:
                        body = -1900000-index*1000-spacing-degree
                        path_spk = artifact_dir / f"{date}_CHANDRA_{spacing}s_d{degree}.bsp"
                        if path_spk.exists():
                            path_spk.unlink()
                        start = time.perf_counter()
                        handle = spice.spkopn(str(path_spk.resolve()), "R18 Chandra refinement", 0)
                        try:
                            spice.spkw09(handle, body, 399, "J2000", float(et[0]), float(et[-1]),
                                         f"R18 followup {date} {spacing} d{degree}", degree,
                                         len(nodes), nodes, et[ni])
                        finally:
                            spice.spkcls(handle)
                        build_wall = time.perf_counter()-start
                        spice.furnsh(str(path_spk.resolve()))
                        try:
                            start = time.perf_counter()
                            actual = spice_states(np, spice, body, et[qi], derivative[qi])
                            query_wall = time.perf_counter()-start
                            node_actual = spice_states(np, spice, body, et[ni], derivative[ni])
                            position = np.linalg.norm(actual[:, :3]-reference[qi, :3], axis=1)
                            velocity = np.linalg.norm(actual[:, 3:]-reference[qi, 3:], axis=1)
                            node_error = np.linalg.norm(node_actual[:, :3]-reference[ni, :3], axis=1)
                            if float(node_error.max()) > 1e-6:
                                raise AssertionError("SPK failed native node preservation")
                            for outside in (float(et[0]-1.), float(et[-1]+1.)):
                                try:
                                    spice.spkezr(str(body), outside, "J2000", "NONE", "399")
                                except spice.utils.exceptions.SpiceSPKINSUFFDATA:
                                    pass
                                else:
                                    raise AssertionError("SPK unexpectedly extrapolated")
                            worst = int(np.argmax(position))
                            result["cases"].append({"period": date, "satellite": "CHANDRA", "orbit_class": "HEO",
                                                    "spacing_s": spacing, "degree": degree, "input_nodes": len(nodes),
                                                    "midpoint_queries": len(qi), "spk": pin(path_spk),
                                                    "spk_write_wall_s": build_wall,
                                                    "single_spice_query_api_wall_s": query_wall,
                                                    "position_reconstruction_error_m": stats(np, position),
                                                    "velocity_reconstruction_error_m_s": stats(np, velocity),
                                                    "node_position_transport_error_m": stats(np, node_error),
                                                    "outside_coverage_refused": True,
                                                    "worst_midpoint_offset_s": float(grid[qi[worst]]),
                                                    "radius_at_worst_midpoint_m": float(np.linalg.norm(reference[qi[worst], :3])),
                                                    "sampled_position_thresholds_m": {str(bound): bool(np.max(position) <= bound)
                                                                                     for bound in (.001, .01, .1, 1.)}})
                        finally:
                            spice.unload(str(path_spk.resolve()))
                write_json(output, result)
    finally:
        spice.kclear()
    result["complete"] = True
    result["completed_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output, result)
    print(f"Completed {len(result['cases'])} refinement cases", flush=True)


if __name__ == "__main__":
    main()
