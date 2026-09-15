#!/usr/bin/env python3
"""Independently audit published CGK-R1 records against actual solver/native files.

Uses only the Python standard library: no handoff, coupled-reference, geodesy or
key-codec functions are imported. The existing native replay report is bound by
file hashes; this audit additionally reconstructs publication algebra and lineage.

Example:
  python tools/audit_coupled_handoff.py --input examples/demo \
      --run results/satnav_cpu --handoff results/handoff_cpu_final

The resulting publication_audit.json is regenerated on each invocation. Optional
--binary and --coupled-profile resolve external files after moving a release.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "atomOS:CGK-R1:3.6.1.7:handoff"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, message, relative=1e-9, absolute=1e-9):
    require(math.isfinite(actual) and math.isfinite(expected) and
            abs(actual - expected) <= absolute + relative * max(abs(actual), abs(expected)), message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def matching_file(candidates, expected_hash, label):
    for candidate in candidates:
        if candidate is not None and Path(candidate).is_file() and sha(candidate) == expected_hash:
            return Path(candidate)
    raise ValueError(f"No available {label} matches recorded SHA256 {expected_hash}")


def audit(input_dir, run_dir, handoff_dir, *, binary=None, coupled_profile=None):
    input_dir, run_dir, base = Path(input_dir), Path(run_dir), Path(handoff_dir)
    events = [json.loads(line) for line in (base / "ugts_events.jsonl").read_text(encoding="utf-8").splitlines()]
    trace_path = base / "coupled" / "native" / "trace.jsonl"
    trace = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    model = read_json(base / "coupled_model.json")
    summary = read_json(base / "ugts_summary.json")
    replay = read_json(base / "coupled" / "summary.json")
    native_run_path = base / "coupled" / "native" / "run.json"
    native_run = read_json(native_run_path)
    profile = read_json(input_dir / "profile.json")
    solver, epochs = read_csv(run_dir / "solutions.csv"), read_csv(input_dir / "epochs.csv")
    residuals = {}
    for row in read_csv(run_dir / "residuals.csv"):
        residuals.setdefault(int(row["epoch_id"]), []).append(row)
    require(len(events) == len(trace) == len(solver) == len(epochs) > 0, "sample counts differ or input is empty")
    require(replay["native_execution"] == "passed" and replay["native_trace_verified"] and
            replay["status"] == "passed", "complete native replay is required")
    require(summary["native_execution"] == "passed" and summary["native_trace_verified"], "handoff claims no native verification")
    require(replay["input_sha256"] == sha(base / "coupled_model.json") == summary["model_sha256"], "model hash mismatch")
    require(replay["native_trace_sha256"] == sha(trace_path), "native trace hash mismatch")
    require(summary["replay_summary"] == replay, "publication replay report mismatch")
    require(summary["backend"] == native_run["backend"], "backend differs from native run metadata")
    require(summary["hash_domain"] == DOMAIN, "unexpected lineage domain")
    binary_file = matching_file([binary] if binary else
                               [replay["native_command"][0], ROOT / "bin" / "windows" / summary["backend"] / "coupled_kernel.exe"],
                               replay["native_binary_sha256"], "native executable")
    trajectory = model["trajectories"][0]
    require(len(model["trajectories"]) == 1 and len(trajectory["samples"]) == len(events), "handoff requires one complete trajectory")
    require(model["provenance"]["satnav_profile"] == profile, "original frame/profile content differs")
    initial, checks = trajectory["initial"], Counter()
    lat, lon, _ = profile["anchor_geodetic_rad_m"]
    origin = profile["anchor_ecef_m"]
    sin, cos = math.sin, math.cos
    rotation = [[-sin(lon), cos(lon), 0],
                [-sin(lat) * cos(lon), -sin(lat) * sin(lon), cos(lat)],
                [cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat)]]
    initialization = model["provenance"]["initialization"]
    if initialization["position_source"] == "first_valid_observation":
        first = next(row for row in solver if row["status"] == "CONVERGED")
        xyz = [float(first[key]) for key in ("x_m", "y_m", "z_m")]
        for k in range(3):
            close(initial["p"][k], sum(rotation[k][j] * (xyz[j] - origin[j]) for j in range(3)), "first observation initialization")
    else:
        require(initial["p"] == model["provenance"]["coupled_profile"]["trajectory"]["initial"]["p"], "custom initial position differs")
    if initialization["time_source"] == "first_sample_minus_dt":
        require(initial["time"] == float(epochs[0]["t_rx_gpst_s"]) -
                model["provenance"]["coupled_profile"]["initial_dt_s"], "explicit initial interval mismatch")
    previous_hash, failed, alerts = "0" * 64, [], []
    changes, different_positions, packed = 0, 0, 0
    for index, (event, native, row, epoch, sample) in enumerate(zip(events, trace, solver, epochs, trajectory["samples"])):
        label = f"epoch {epoch['epoch_id']}"
        eid, time = int(epoch["epoch_id"]), float(epoch["t_rx_gpst_s"])
        require(event["native_state"] == native, f"{label}: complete native state differs")
        checks["complete_native_trace_rows_equal"] += 1
        require(event["epoch_id"] == native["epoch_id"] == int(row["epoch_id"]) == sample["epoch_id"] == eid, f"{label}: ID/order mismatch")
        require(event["input_index"] == native["step"] == index, f"{label}: input index differs")
        require(event["t_gpst_s"] == native["time_after"] == float(row["t_rx_gpst_s"]) == sample["time"] == time, f"{label}: time mismatch")
        observation, modeled, chart = event["observation"], event["modeled"], event["chart"]
        require(observation["solver_record"] == row and observation["epoch_record"] == epoch, f"{label}: original records differ")
        require(observation["residual_records"] == residuals.get(eid, []), f"{label}: original residuals differ")
        checks["original_solver_epoch_residual_records_equal"] += 1
        xyz = [float(row[key]) for key in ("x_m", "y_m", "z_m")]
        enu = [sum(rotation[k][j] * (xyz[j] - origin[j]) for j in range(3)) for k in range(3)]
        require(observation["ecef_m"] == native["observed_ecef"] == sample["observed_ecef"] == xyz, f"{label}: original ECEF changed")
        for actual, expected in zip(observation["enu_m"], enu):
            close(actual, expected, f"{label}: observed ECEF-to-ENU")
        require(observation["enu_m"] == sample["target"] == native["target"], f"{label}: native target differs")
        clock = float(row["clock_bias_m"])
        require(observation["clock_bias_m"] == sample["clock_bias_m"] == native["clock_bias_m"] == clock, f"{label}: receiver clock changed")
        require(observation["formal_variance_m2"] == {key: float(row[f"var_{key}_m2"]) for key in ("x", "y", "z", "clock")}, f"{label}: formal variances differ")
        require(observation["solver_status"] == row["status"], f"{label}: solver status changed")
        checks["ecef_enu_clock_variance_status_retained"] += 1
        valid = row["status"] == "CONVERGED"
        require(observation["valid"] == sample["valid"] == bool(native["observation_valid"]) == valid, f"{label}: convergence validity changed")
        require(modeled["enu_m"] == native["p_after"] and modeled["velocity_enu_m_s"] == native["v_after"], f"{label}: modeled state differs")
        require(modeled["q"] == native["q_after"] and modeled["hoop_phi_rad"] == native["phi_after"], f"{label}: q/hoop differs")
        require(event["jk"] == {"before": native["q_before"], "j": native["j"], "k": native["k"], "after": native["q_after"]}, f"{label}: JK binding differs")
        require(native["q_after"] == ((native["j"] & ~native["q_before"]) | (~native["k"] & native["q_before"])) & trajectory["masks"]["present"], f"{label}: synchronous JK equation mismatch")
        checks["modeled_enu_ecef_velocity_jk_hoop_bound"] += 1
        if index:
            previous = trace[index - 1]
            state_time = previous["time_after"] if previous["status"] == "advanced" else previous["time_before"]
            require(native["p_before"] == previous["p_after"] and native["v_before"] == previous["v_after"] and
                    native["q_before"] == previous["q_after"] and native["phi_before"] == previous["phi_after"] and
                    native["time_before"] == state_time, f"{label}: persistent state discontinuity")
            checks["persistent_state_links"] += 1
        else:
            initial_phase = math.fmod(initial["phi"], 2 * math.pi)
            if initial_phase >= math.pi:
                initial_phase -= 2 * math.pi
            if initial_phase < -math.pi:
                initial_phase += 2 * math.pi
            require(native["p_before"] == initial["p"] and native["v_before"] == initial["v"] and native["q_before"] == initial["q"] and
                    native["phi_before"] == initial_phase and native["time_before"] == initial["time"], "initial state binding differs")
        require(native["dt"] == native["time_after"] - native["time_before"] > 0, f"{label}: nonpositive/incorrect timestep")
        if native["status"] == "advanced":
            require(modeled["valid"], f"{label}: advanced state marked unavailable")
            for k in range(3):
                close(modeled["ecef_m"][k], origin[k] + sum(rotation[j][k] * modeled["enu_m"][j] for j in range(3)),
                      f"{label}: modeled ENU-to-ECEF", 1e-14, 1e-9)
            stiffness = [trajectory["stiffness_base"][k // 3][k % 3] for k in range(9)]
            for channel in trajectory["channels"]:
                bit, direction = (native["q_after"] >> channel["index"]) & 1, channel["direction"]
                coefficient = channel["stiffness"]["on" if bit else "off"]
                for a in range(3):
                    for b in range(3):
                        stiffness[3 * a + b] += coefficient * direction[a] * direction[b]
            for actual, expected in zip(native["stiffness"], stiffness):
                close(actual, expected, f"{label}: q-dependent stiffness", 1e-12, 1e-12)
            checks["q_controls_full_stiffness_matrix"] += 1
            require(chart["time_gpst_s"] == time and chart["up_m"] == modeled["enu_m"][2] and
                    chart["hoop_phi_rad"] == modeled["hoop_phi_rad"], f"{label}: full time/Up/hoop lost")
            tick_coordinate = (time - profile["tick_origin_gpst_s"]) / profile["epoch_tick_period_s"]
            tick_defined = math.isfinite(tick_coordinate)
            tick = round(tick_coordinate) if tick_defined else None
            on_lattice = tick_defined and abs(tick_coordinate - tick) <= 1e-6
            radius = math.hypot(*modeled["enu_m"][:2])
            ratio = radius / trajectory["chart"]["r0"]
            expected_status = ("origin_core" if radius < trajectory["chart"]["core"] else
                               "numerical_range" if not math.isfinite(ratio) or ratio <= 0 else
                               "defined" if -20 <= math.log(ratio) <= 0 else "out_of_key_range")
            require(chart["status"] == expected_status, f"{label}: endpoint chart classification differs")
            if on_lattice:
                winding, remainder = divmod(tick, 16384)
                require(chart["linear_tick"] == tick and chart["winding"] == winding and chart["phase"] == remainder / 16384, f"{label}: winding/full tick differs")
            elif tick_defined:
                require(chart["winding"] == math.floor(tick_coordinate / 16384) and
                        chart["phase"] == (tick_coordinate % 16384) / 16384 and
                        chart["temporal_status"] == "tick_not_on_declared_lattice", f"{label}: continuous time winding differs")
            else:
                require(chart["tick_coordinate"] is None and chart["winding"] is None and chart["phase"] is None and
                        chart["temporal_status"] == "numerical_range", f"{label}: unavailable tick coordinate not identified")
            if expected_status == "defined" and on_lattice:
                rho, theta = math.log(ratio), math.atan2(modeled["enu_m"][1], modeled["enu_m"][0])
                close(chart["rho"], rho, f"{label}: chart rho")
                close(chart["theta"], theta, f"{label}: chart theta")
                def angle(value, width):
                    return int(math.floor((value % (2 * math.pi)) * (1 << width) / (2 * math.pi) + 0.5)) % (1 << width)
                fields = [int(math.floor((rho + 20) / 20 * ((1 << 20) - 1) + 0.5)), angle(theta, 18), tick % 16384, angle(modeled["hoop_phi_rad"], 12)]
                packing = event["packing"]
                require(packing["fields"] == fields, f"{label}: packed tuple differs")
                key = (fields[0] << 44) | (fields[1] << 26) | (fields[2] << 12) | fields[3]
                morton, widths = 0, [20, 18, 14, 12]
                for depth in range(20):
                    for field, width in enumerate(widths):
                        if depth < width:
                            morton = (morton << 1) | ((fields[field] >> (width - 1 - depth)) & 1)
                require(packing["contiguous_hex"] == f"{key:016x}" and packing["morton_hex"] == f"{morton:016x}", f"{label}: one or both key codecs differ")
                require(packing["linear_tick"] == tick and packing["winding"] == winding and packing["state_source"] == "modeled_endpoint", f"{label}: packed-state metadata differs")
                packed += 1
                checks["modeled_both_keys_full_time_winding_up_and_hoop"] += 1
            else:
                require(event["packing"] is None, f"{label}: undefined key domain incorrectly packed")
            if not valid:
                dt, mass, damping = native["dt"], trajectory["mass"], trajectory["damping"]
                expected_v = [(mass[k] * native["v_before"][k] + dt * native["force"][k]) /
                              (mass[k] + dt * damping[k]) for k in range(3)]
                for k in range(3):
                    close(native["v_after"][k], expected_v[k], f"{label}: unavailable observation prediction velocity")
                    close(native["p_after"][k], native["p_before"][k] + dt * expected_v[k], f"{label}: prediction position")
                    for j in range(3):
                        close(native["mechanical_matrix"][3 * k + j], mass[k] + dt * damping[k] if j == k else 0,
                              f"{label}: observation spring terms must vanish")
                require(event["event"] == "COUPLED_PREDICTION_ADVANCED", f"{label}: missing prediction publication")
                failed.append({"epoch_id": eid, "solver_status": row["status"],
                               "motion_m": math.dist(native["p_before"], native["p_after"]),
                               "q_before": native["q_before"], "q_after": native["q_after"], "target_spring_terms": 0})
                checks["failed_observation_prediction_dynamics_verified"] += 1
            if observation["residual_diagnostic"]["classification"] == "EXCEEDS":
                require(valid and native["observation_valid"] and event["event"] == "COUPLED_OBSERVATION_ADVANCED", f"{label}: residual alert suppressed mechanics")
                alerts.append(eid)
            if math.dist(observation["ecef_m"], modeled["ecef_m"]) > 1e-9:
                different_positions += 1
        else:
            require(native["status"] in ("numeric_failure", "previous_failure") and not modeled["valid"] and
                    modeled["ecef_m"] is None and event["packing"] is None and chart["status"] == "physical_state_unavailable",
                    f"{label}: physical failure published as available state")
            checks["explicit_physical_failure_records"] += 1
        if native["q_before"] != native["q_after"]:
            changes += 1
        require(event["lineage"]["model_sha256"] == summary["model_sha256"], f"{label}: model lineage mismatch")
        require(event["lineage"]["sources"] == model["provenance"]["sources"], f"{label}: original source lineage mismatch")
        native_lineage = event["lineage"]["native"]
        require(native_lineage["trace_sha256"] == replay["native_trace_sha256"] and
                native_lineage["binary_sha256"] == replay["native_binary_sha256"] and
                native_lineage["run_metadata"] == native_run and native_lineage["run_metadata_sha256"] == sha(native_run_path) and
                native_lineage["replay_summary_sha256"] == sha(base / "coupled" / "summary.json"), f"{label}: native execution lineage mismatch")
        require(event["previous_hash"] == previous_hash, f"{label}: hash-chain link differs")
        unhashed = {key: value for key, value in event.items() if key != "record_hash"}
        payload = json.dumps(unhashed, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        actual_hash = hashlib.sha256(DOMAIN.encode() + b"\0" + len(payload).to_bytes(8, "big") + payload).hexdigest()
        require(actual_hash == event["record_hash"], f"{label}: record digest differs")
        previous_hash = actual_hash
        checks["independent_hash_chain_records"] += 1
    require(previous_hash == summary["head_sha256"], "final chain head differs")
    source_files = {"satnav_profile": input_dir / "profile.json", "epochs": input_dir / "epochs.csv",
                    "solutions": run_dir / "solutions.csv", "residuals": run_dir / "residuals.csv",
                    "observations": input_dir / "observations.csv", "satnav_run": run_dir / "run.json"}
    for name, record in model["provenance"]["sources"].items():
        if name == "coupled_profile":
            source = matching_file([coupled_profile] if coupled_profile else
                                   [record["path"], ROOT / "profiles" / "COUPLED_R1.json"], record["sha256"], "coupled profile")
        else:
            source = source_files[name]
        require(sha(source) == record["sha256"], f"original source hash differs: {name}")
        checks["unchanged_source_file_hashes"] += 1
    return {"version": "3.6.1.7", "profile": "CGK-R1", "status": "passed", "backend": summary["backend"],
            "artifact": str(base), "audit_script_sha256": sha(Path(__file__)),
            "audit_method": "Independent standard-library publication audit: direct CSV/JSON equality, explicit ECEF/ENU equations, both key formulas, invalid-observation mechanics, q-dependent stiffness sums and standalone hashlib chain reconstruction. No publisher or coupled-reference functions imported; full native replay is separately bound by file hashes.",
            "checks": dict(checks), "rows": len(events), "packed_rows": packed,
            "native_replay_field_comparisons": replay["field_comparisons"], "q_transitions": changes,
            "distinct_q_states": sorted({row["q_after"] for row in trace}),
            "observed_and_modeled_positions_differ": different_positions,
            "invalid_predictions": failed, "residual_alerts_still_drive_model": alerts,
            "head_sha256": previous_hash, "verified_binary_path": str(binary_file),
            "hashes": {"events": sha(base / "ugts_events.jsonl"), "model": sha(base / "coupled_model.json"),
                       "native_trace": sha(trace_path), "native_binary": replay["native_binary_sha256"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--coupled-profile", type=Path)
    args = parser.parse_args()
    try:
        report = audit(args.input, args.run, args.handoff, binary=args.binary, coupled_profile=args.coupled_profile)
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError, StopIteration) as error:
        parser.exit(1, f"ERROR: publication audit failed: {error}\n")
    (args.handoff / "publication_audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
