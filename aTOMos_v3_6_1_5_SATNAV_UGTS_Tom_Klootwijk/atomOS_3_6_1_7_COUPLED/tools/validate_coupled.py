#!/usr/bin/env python3
"""Reproducible complete native CGK-R1 replay and independent causal/mechanical checks.

Includes 257 variable-length stress trajectories in addition to targeted fixtures.
The native trace is compared with direct original-equation interpretation and NumPy
mechanics, then checked against analytic mechanics and both directions of feedback.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import math
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from coupled import (PROFILE, VERSION, compare_trace_row, file_digest, parse_document,
                     read_json, replay, write_compiled)


def free_trajectory(identifier, steps=5, dt=.25):
    return {"id": identifier, "initial": {"time": 0., "p": [10., 2., 3.], "v": [1., -2., .5], "q": 0, "phi": 0.},
            "mass": [2., 3., 4.], "damping": [0., 0., 0.], "stiffness_base": [[0., 0., 0.], [0., 0., 0.], [0., 0., 0.]],
            "chart": {"r0": 100., "core": .001, "blend_weight": .5, "axis": 0.}, "hoop": {"rate": .25},
            "masks": {"present": 0, "asa": 4294967295, "na": 4294967295, "boundary": 0}, "channels": [],
            "equations": {"d": "0", "x": "0", "j": "0", "k": "0"}, "samples": [
                {"epoch_id": i, "time": (i + 1) * dt, "valid": False, "target": [0., 0., 0.],
                 "observed_ecef": [3920000., 343000., 5000000.], "clock_bias_m": 5., "force": [0., 0., 0.]}
                for i in range(steps)]}


def model():
    doc = read_json(ROOT / "examples/coupled/model.json")
    doc["description"] = "CGK-R1 native verification fixtures: analytic mechanics, causal counterfactuals, failure domains, 257 variable-length trajectories."
    records = doc["trajectories"]
    changed_geometry = deepcopy(records[0])
    changed_geometry["id"] = 3
    changed_geometry["samples"][0]["target"] = list(changed_geometry["initial"]["p"])
    records.append(changed_geometry)
    equation_edit = deepcopy(records[0])
    equation_edit["id"] = 4
    equation_edit["equations"] = {"j": "0"}
    records.append(equation_edit)
    records.append(free_trajectory(10))
    constant = free_trajectory(11, 8, .25)
    for sample in constant["samples"]:
        sample["force"] = [2., -6., 1.]
    records.append(constant)
    spring = free_trajectory(12, 1, .25)
    spring["mass"] = [1., 1., 1.]
    spring["initial"]["v"] = [0., 0., 0.]
    spring["stiffness_base"] = np.diag([4., 9., 16.]).tolist()
    spring["samples"][0]["valid"] = True
    records.append(spring)
    singular = free_trajectory(13, 3, 1.)
    singular["damping"] = [-2., -3., -4.]
    singular["masks"]["present"] = 1 << 31
    channel = deepcopy(records[0]["channels"][0])
    channel.update(index=31, direction=[1., 0., 0.], stiffness={"off": 0., "on": 0.}, force={"off": 0., "on": 0.})
    singular["channels"] = [channel]
    singular["equations"]["j"] = "1"
    records.append(singular)
    overflow = free_trajectory(14, 2, 2.)
    overflow["samples"][0]["force"] = [1e308, 0., 0.]
    records.append(overflow)
    geometry_overflow = free_trajectory(15, 2, 1.)
    geometry_overflow["initial"]["p"] = [1e308, 1e308, 0.]
    geometry_overflow["chart"] = {"r0": 1e-200, "core": 1e-250, "blend_weight": 0., "axis": 0.}
    records.append(geometry_overflow)
    unavailable = deepcopy(records[0])
    unavailable["id"] = 16
    unavailable["samples"] = unavailable["samples"][:4]
    for sample in unavailable["samples"]:
        sample["valid"] = False
    unavailable["equations"] = {"d": "~valid", "x": "d", "j": "y", "k": "0"}
    records.append(unavailable)
    absorption = deepcopy(unavailable)
    absorption["id"] = 17
    absorption["masks"]["boundary"] = 1
    absorption["equations"]["j"] = "~valid"
    records.append(absorption)
    core = free_trajectory(18, 3, 1.)
    core["initial"]["p"], core["initial"]["v"] = [0., 0., 0.], [0., 0., 0.]
    records.append(core)
    negative = free_trajectory(19, 3, .1)
    negative["stiffness_base"] = [[-.5, .1, 0.], [.1, .2, .01], [0., .01, .1]]
    negative["damping"] = [-.1, -.2, -.3]
    records.append(negative)
    for i in range(257):
        stress = deepcopy(records[i % 3])
        stress["id"] = 1000 + i
        stress["initial"]["q"] = i % 8
        stress["initial"]["phi"] = (i % 17 - 8) * math.pi / 7
        stress["mass"] = [mass * (1 + .01 * (i % 11)) for mass in stress["mass"]]
        stress["samples"] = stress["samples"][:1 + i % 24]
        for sample in stress["samples"]:
            sample["epoch_id"] += i * 100
        if i % 19 == 0:
            stress["masks"]["boundary"] = 1 << (i % 3)
        records.append(stress)
    return doc


def verify_native_invariants(document, rows):
    by_id = {}
    for row in rows:
        by_id.setdefault(row["trajectory_id"], []).append(row)
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(f"Native invariant failed: {name}")
        checks.append(name)

    base, changed_state, changed_geometry, edited = (by_id[i] for i in (0, 1, 3, 4))
    check("q0_changes_native_position_and_velocity", base[0]["p_after"] != changed_state[0]["p_after"] and base[0]["v_after"] != changed_state[0]["v_after"])
    check("q0_changes_later_geometry_drive", any(a["drive"] != b["drive"] for a, b in zip(base[1:], changed_state[1:])))
    check("observation_geometry_changes_drive_and_q", base[0]["drive"] != changed_geometry[0]["drive"] and base[0]["q_after"] != changed_geometry[0]["q_after"])
    check("changed_geometry_q_changes_next_physical_state", base[1]["p_before"] != changed_geometry[1]["p_before"])
    check("edited_equation_changes_native_q_and_physics", base[0]["q_after"] != edited[0]["q_after"] and base[0]["p_after"] != edited[0]["p_after"])
    check("edited_equation_changes_later_predicates", any(a["limit"] != b["limit"] for a, b in zip(base, edited)))
    p0, v0 = np.array([10., 2., 3.]), np.array([1., -2., .5])
    for row in by_id[10]:
        np.testing.assert_allclose(row["p_after"], p0 + row["time_after"] * v0, atol=2e-12, rtol=2e-12)
        np.testing.assert_allclose(row["v_after"], v0, atol=2e-12, rtol=2e-12)
    checks.append("free_motion_closed_form")
    acceleration = np.array([1., -2., .25])
    for n, row in enumerate(by_id[11], 1):
        np.testing.assert_allclose(row["v_after"], v0 + n * .25 * acceleration, atol=2e-12, rtol=2e-12)
        np.testing.assert_allclose(row["p_after"], p0 + n * .25 * v0 + .5 * n * (n + 1) * .25**2 * acceleration, atol=2e-12, rtol=2e-12)
    checks.append("constant_force_backward_euler_closed_form")
    expected_v = -.25 * np.array([4., 9., 16.]) * p0 / (1 + .25**2 * np.array([4., 9., 16.]))
    np.testing.assert_allclose(by_id[12][0]["v_after"], expected_v, atol=2e-12, rtol=2e-12)
    np.testing.assert_allclose(by_id[12][0]["p_after"], p0 + .25 * expected_v, atol=2e-12, rtol=2e-12)
    checks.append("diagonal_spring_known_discrete_step")
    check("singular_numeric_failure_then_frozen", [r["status"] for r in by_id[13]] == ["numeric_failure", "previous_failure", "previous_failure"])
    check("singular_failure_commits_bit31", all(r["q_after"] == 1 << 31 for r in by_id[13]))
    check("failed_time_and_physics_remain_last_valid", all(r["time_before"] == 0. and r["p_after"] == p0.tolist() for r in by_id[13]))
    check("overflow_is_failure_with_null_diagnostic", by_id[14][0]["status"] == "numeric_failure" and by_id[14][0]["mechanical_rhs"][0] is None)
    check("geometry_overflow_is_explicit_failure", by_id[15][0]["status"] == "numeric_failure" and by_id[15][0]["rho"] is None)
    check("unavailable_observation_still_updates_q_and_physics", by_id[16][0]["q_after"] == 7 and by_id[16][0]["p_after"] != by_id[16][0]["p_before"])
    check("whole_word_absorption_preserves_supplied_j_equation", by_id[17][0]["na"] == 7 and by_id[17][0]["output"] == 0 and by_id[17][0]["q_after"] == 7)
    check("origin_chart_domain_status", [r["otan_status"] for r in by_id[18]] == ["first_observation", "origin_core", "origin_core"])
    check("negative_eigenvalue_is_retained", all(r["eigenvalues"][0] < 0 and r["status"] == "advanced" for r in by_id[19]))
    check("257_variable_length_trajectories_present", sum(key >= 1000 for key in by_id) == 257 and {len(value) for key, value in by_id.items() if key >= 1000} == set(range(1, 25)))
    source_by_id = {t["id"]: t for t in document["trajectories"]}
    for row in base:
        matrix = np.array(row["stiffness"]).reshape(3, 3)
        vectors = np.array(row["eigenvectors"]).reshape(3, 3)
        mass = np.array(source_by_id[0]["mass"])
        modes = vectors / np.sqrt(mass)[:, None]
        np.testing.assert_allclose(matrix @ modes, mass[:, None] * modes * row["eigenvalues"], atol=2e-10, rtol=2e-10)
    checks.append("native_offdiagonal_generalized_modes")
    return checks


def run(args):
    args.out.mkdir(parents=True, exist_ok=False)
    document = model()
    source = args.out / "model.json"
    source.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    trajectories = parse_document(document)
    compiled = args.out / "compiled"
    write_compiled(trajectories, compiled)
    binary = args.binary.resolve(strict=True)
    native = args.out / "native"
    report = {"version": VERSION, "profile": PROFILE, "status": "failed", "backend": args.backend,
              "input_sha256": file_digest(source), "native_binary_sha256": file_digest(binary),
              "trajectory_count": len(trajectories), "native_trace_verified": False}
    try:
        command = [str(binary), "--input", str(compiled.resolve()), "--out", str(native.resolve()),
                   "--backend", args.backend, "--device", str(args.device)]
        report["native_command"] = command
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        (args.out / "native.stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (args.out / "native.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        report["native_returncode"] = completed.returncode
        if completed.returncode:
            raise RuntimeError(f"Native validation returned {completed.returncode}")
        reference = args.out / "reference_trace.jsonl"
        report.update(replay(trajectories, trace_path=reference, actual_path=native / "trace.jsonl"))
        native_rows = [json.loads(line) for line in (native / "trace.jsonl").read_text().splitlines()]
        report["invariants"] = verify_native_invariants(document, native_rows)
        first = native_rows[3]
        mutations = []
        for field in ("q_after", "drive", "time_after", "p_after", "stiffness", "mechanical_rhs", "eigenvalues", "eigenvectors"):
            corrupted = deepcopy(first)
            if isinstance(corrupted[field], list):
                corrupted[field][0] += .5
            else:
                corrupted[field] += 1
            try:
                compare_trace_row(first, corrupted)
            except ValueError:
                mutations.append(field)
            else:
                raise AssertionError(f"Trace mutation was accepted: {field}")
        report.update(trace_mutations_rejected=mutations, native_trace_sha256=file_digest(native / "trace.jsonl"),
                      reference_trace_sha256=file_digest(reference), status="passed")
        return report
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        (args.out / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, ValueError, RuntimeError, AssertionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 1
    print(json.dumps({key: report[key] for key in ("status", "trajectory_count", "transitions", "field_comparisons", "native_trace_verified", "invariants", "trace_mutations_rejected")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
