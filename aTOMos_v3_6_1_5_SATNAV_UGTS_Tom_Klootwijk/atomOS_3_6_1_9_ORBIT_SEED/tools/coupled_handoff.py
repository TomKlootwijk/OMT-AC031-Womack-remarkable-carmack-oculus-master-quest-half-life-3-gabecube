#!/usr/bin/env python3
"""Bind actual SATNAV results to the CGK-R1 native geometry/state feedback loop."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from geodesy import ecef_to_enu, enu_to_ecef
from ugts import contiguous, digest, morton, phase_winding, quantize

VERSION = "3.6.1.7"
DOMAIN = "atomOS:CGK-R1:3.6.1.7:handoff"
DEFAULT_PROFILE = ROOT / "profiles" / "COUPLED_R1.json"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_number(value, name):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def vector(value, name):
    if len(value) != 3:
        raise ValueError(f"{name} requires three coordinates")
    return [finite_number(x, name) for x in value]


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_sources(input_dir, run_dir, profile_path=DEFAULT_PROFILE):
    """Retain source rows verbatim, bind by ID and validate temporal/frame meaning."""
    input_dir, run_dir, profile_path = Path(input_dir), Path(run_dir), Path(profile_path)
    files = {"satnav_profile": input_dir / "profile.json", "epochs": input_dir / "epochs.csv",
             "solutions": run_dir / "solutions.csv", "residuals": run_dir / "residuals.csv",
             "coupled_profile": profile_path}
    for name, path in (("observations", input_dir / "observations.csv"),
                       ("satnav_run", run_dir / "run.json")):
        if path.is_file():
            files[name] = path
    hashes = {name: {"path": str(path.resolve()), "sha256": file_hash(path)}
              for name, path in files.items()}
    cfg = json.loads(files["satnav_profile"].read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if cfg["frame"] != "ECEF_reception_axes_satellite_at_emission":
        raise ValueError("unsupported ECEF frame: an explicit frame conversion is required")
    if cfg["time_scale"] != "GPST":
        raise ValueError("unsupported time scale: an explicit GPST conversion is required")
    lat, lon, _ = vector(cfg["anchor_geodetic_rad_m"], "anchor_geodetic_rad_m")
    if not -math.pi / 2 <= lat <= math.pi / 2:
        raise ValueError("anchor latitude domain")
    origin = vector(cfg["anchor_ecef_m"], "anchor_ecef_m")
    period = finite_number(cfg["epoch_tick_period_s"], "epoch_tick_period_s")
    if period <= 0:
        raise ValueError("epoch_tick_period_s must be positive")
    finite_number(cfg["tick_origin_gpst_s"], "tick_origin_gpst_s")
    rows, epochs = read_csv(files["solutions"]), read_csv(files["epochs"])
    if not rows or len(rows) != len(epochs):
        raise ValueError("exactly one solver result is required for each input epoch")
    residuals = {}
    seen_channels = set()
    for row in read_csv(files["residuals"]):
        eid, channel = int(row["epoch_id"]), int(row["channel"])
        if not 0 <= channel < 32 or not 0 <= eid < 1 << 64:
            raise ValueError("residual epoch/channel outside unsigned domain")
        if (eid, channel) in seen_channels:
            raise ValueError("duplicate residual channel in epoch")
        seen_channels.add((eid, channel))
        finite_number(row["residual_m"], "residual_m")
        residuals.setdefault(eid, []).append(row)
    observations, seen, previous_time = [], set(), None
    for index, (row, epoch) in enumerate(zip(rows, epochs)):
        eid, expected_id = int(row["epoch_id"]), int(epoch["epoch_id"])
        if eid != expected_id:
            raise ValueError("solutions must retain input epoch order and IDs")
        if eid in seen or not 0 <= eid < 1 << 64:
            raise ValueError("duplicate or invalid epoch ID")
        seen.add(eid)
        time = finite_number(row["t_rx_gpst_s"], "solution time")
        if time != finite_number(epoch["t_rx_gpst_s"], "input epoch time"):
            raise ValueError("solution time differs from its input epoch")
        if previous_time is not None and time <= previous_time:
            raise ValueError("coupled dynamics require strictly increasing input times; input is never sorted")
        previous_time = time
        xyz = [finite_number(row[key], key) for key in ("x_m", "y_m", "z_m")]
        clock = finite_number(row["clock_bias_m"], "clock_bias_m")
        variance = [finite_number(row[key], key)
                    for key in ("var_x_m2", "var_y_m2", "var_z_m2", "var_clock_m2")]
        valid = row["status"] == "CONVERGED"
        channel_rows = residuals.get(eid, [])
        if valid and not channel_rows:
            raise ValueError(f"missing residuals for converged epoch {eid}")
        observations.append({"epoch_id": eid, "time": time, "valid": valid,
                             "ecef_m": xyz, "enu_m": list(ecef_to_enu(xyz, origin, lat, lon)),
                             "clock_bias_m": clock, "formal_variance_m2": variance,
                             "input_index": index, "solver_record": row, "epoch_record": epoch,
                             "residual_records": channel_rows})
    if set(residuals) - seen:
        raise ValueError("residuals refer to an unknown epoch")
    return {"config": cfg, "profile": profile, "observations": observations,
            "sources": hashes, "anchor": {"ecef_m": origin, "lat_rad": lat, "lon_rad": lon}}


def assert_sources_unchanged(bundle):
    for name, source in bundle["sources"].items():
        if file_hash(source["path"]) != source["sha256"]:
            raise ValueError(f"source changed while coupling was running: {name}")


def build_model(bundle):
    profile, cfg, observations = bundle["profile"], bundle["config"], bundle["observations"]
    if profile.get("profile") != "CGK-R1-SATNAV" or profile.get("version") != VERSION:
        raise ValueError(f"coupled profile requires CGK-R1-SATNAV version {VERSION}")
    trajectory = copy.deepcopy(profile["trajectory"])
    position_source = profile["initial_position_source"]
    if position_source == "first_valid_observation":
        first_valid = next((row for row in observations if row["valid"]), None)
        if first_valid is None:
            raise ValueError("no converged observation for initialization; supply initial_position_source='profile' and an explicit position")
        trajectory["initial"]["p"] = list(first_valid["enu_m"])
        initialization = {"position_source": position_source, "epoch_id": first_valid["epoch_id"],
                          "epoch_time": first_valid["time"], "uses_future_observation": first_valid["input_index"] > 0}
    elif position_source == "profile":
        trajectory["initial"]["p"] = vector(trajectory["initial"]["p"], "initial p")
        initialization = {"position_source": "profile", "uses_future_observation": False}
    else:
        raise ValueError("initial_position_source must be first_valid_observation or profile")
    time_source = profile.get("initial_time_source", "first_sample_minus_dt")
    if time_source == "first_sample_minus_dt":
        dt = finite_number(profile["initial_dt_s"], "initial_dt_s")
        if dt <= 0:
            raise ValueError("initial_dt_s must be positive")
        trajectory["initial"]["time"] = observations[0]["time"] - dt
        initialization.update(time_source=time_source, requested_initial_dt_s=dt)
    elif time_source != "profile":
        raise ValueError("initial_time_source must be first_sample_minus_dt or profile")
    else:
        initialization["time_source"] = "profile"
    if profile.get("chart_source", "profile") == "satnav_profile":
        trajectory["chart"].update(r0=finite_number(cfg["chart_r0_m"], "chart_r0_m"),
                                   core=finite_number(cfg["chart_core_m"], "chart_core_m"))
    elif profile.get("chart_source", "profile") != "profile":
        raise ValueError("chart_source must be satnav_profile or profile")
    if profile.get("hoop_initial_source", "profile") == "satnav_profile":
        trajectory["initial"]["phi"] = finite_number(cfg["hoop_phi_rad"], "hoop_phi_rad")
    elif profile.get("hoop_initial_source", "profile") != "profile":
        raise ValueError("hoop_initial_source must be satnav_profile or profile")
    external_force = vector(profile["external_force"], "external_force")
    trajectory["samples"] = [
        {"epoch_id": row["epoch_id"], "time": row["time"], "valid": row["valid"],
         "target": row["enu_m"], "observed_ecef": row["ecef_m"],
         "clock_bias_m": row["clock_bias_m"], "force": list(external_force)}
        for row in observations]
    document = {"version": VERSION, "profile": "CGK-R1", "equations": copy.deepcopy(profile["equations"]),
                "trajectories": [trajectory],
                "description": "Actual SATNAV results drive an explicitly defined CGK-R1 mechanical observer.",
                "provenance": {"sources": copy.deepcopy(bundle["sources"]), "satnav_profile": copy.deepcopy(cfg),
                               "coupled_profile": copy.deepcopy(profile), "anchor": copy.deepcopy(bundle["anchor"]),
                               "initialization": initialization,
                               "input_records": copy.deepcopy(observations),
                               "model_origin": profile["model_origin"],
                               "validity_rule": "solver status CONVERGED; residual classification does not disable mechanics",
                               "unavailable_observation_rule": "valid=false removes target spring terms; state evolution continues"}}
    # This uses the same strict input validator as compilation; replay remains independent.
    from coupled import parse_document
    parse_document(document)
    return document


def residual_diagnostic(observation, cfg):
    """Residual fit is metadata; convergence alone selects observation terms."""
    rows = observation["residual_records"]
    if not observation["valid"]:
        return {"classification": "NOT_APPLICABLE", "reason": "solver_not_converged"}
    maximum = max(abs(float(row["residual_m"])) for row in rows)
    bound = finite_number(cfg["code_residual_bound_m"], "code_residual_bound_m")
    budget = finite_number(cfg["code_residual_budget_m"], "code_residual_budget_m")
    if bound < 0 or budget < 0:
        raise ValueError("residual model bound and budget must be nonnegative")
    lower, upper = max(0.0, maximum - bound), maximum + bound
    return {"classification": "WITHIN" if upper <= budget else "EXCEEDS" if lower > budget else "UNRESOLVED",
            "max_abs_residual_m": maximum, "model_interval_m": [lower, upper],
            "budget_m": budget, "conditional_on_declared_bound": True,
            "changes_observation_validity": False}


def chart_and_keys(position, time, hoop, cfg, geometry, physical_status="advanced"):
    """Index the modeled endpoint; full state/time/Up/hoop remain independent fields."""
    period, origin = float(cfg["epoch_tick_period_s"]), float(cfg["tick_origin_gpst_s"])
    tick_float = (time - origin) / period
    tick_defined = math.isfinite(tick_float)
    tick = round(tick_float) if tick_defined else None
    chart = {"up_m": position[2], "hoop_phi_rad": hoop, "time_gpst_s": time,
             "tick_coordinate": tick_float if tick_defined else None, "tick_origin_gpst_s": origin,
             "tick_period_s": period, "winding": math.floor(tick_float / 16384) if tick_defined else None,
             "phase": (tick_float % 16384) / 16384 if tick_defined else None,
             "quantity": "modeled_endpoint_local_ENU_chart"}
    on_lattice = tick_defined and abs(tick_float - tick) <= 1e-6
    if on_lattice:
        winding, phase = phase_winding(tick, 0, 16384)
        chart.update(linear_tick=tick, winding=winding, phase=phase)
    chart["temporal_status"] = ("on_declared_lattice" if on_lattice else "tick_not_on_declared_lattice") if tick_defined else "numerical_range"
    if physical_status != "advanced":
        chart["status"] = "physical_state_unavailable"
        return chart, None
    radius = math.hypot(position[0], position[1])
    if radius < geometry["core"]:
        chart["status"] = "origin_core"
        return chart, None
    ratio = radius / geometry["r0"]
    if not math.isfinite(ratio) or ratio <= 0:
        chart["status"] = "numerical_range"
        return chart, None
    rho, theta = math.log(ratio), math.atan2(position[1], position[0])
    chart.update(rho=rho, theta=theta, status="defined" if -20 <= rho <= 0 else "out_of_key_range")
    if chart["status"] != "defined" or not on_lattice:
        return chart, None
    fields = quantize(rho, theta, tick, hoop)
    return chart, {"fields": fields, "contiguous_hex": f"{contiguous(fields):016x}",
                   "morton_hex": f"{morton(fields):016x}", "linear_tick": tick,
                   "winding": winding, "phase": phase, "state_source": "modeled_endpoint",
                   "not_a_complete_navigation_state": True}


def _dump_new(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def execute_native(model_path, out, binary, backend="cpu", device=0):
    binary = Path(binary).resolve(strict=True)
    command = [sys.executable, str(ROOT / "tools" / "coupled.py"), "--input", str(Path(model_path).resolve()),
               "--out", str(Path(out).resolve()), "--binary", str(binary), "--backend", backend,
               "--device", str(device)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "handoff.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (Path(out) / "handoff.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(f"coupled native execution/replay failed ({completed.returncode}); see {out}")
    report = json.loads((Path(out) / "summary.json").read_text(encoding="utf-8"))
    if report.get("native_execution") != "passed" or report.get("native_trace_verified") is not True:
        raise RuntimeError("native execution and independent trace replay are required for the handoff")
    trace_path = Path(out) / "native" / "trace.jsonl"
    trace_hash, binary_hash = file_hash(trace_path), file_hash(binary)
    if report.get("input_sha256") != file_hash(model_path) or report.get("native_trace_sha256") != trace_hash:
        raise ValueError("model/trace hashes do not match the independently verified native run")
    if report.get("native_binary_sha256") != binary_hash:
        raise ValueError("native executable changed after execution")
    run_path = Path(out) / "native" / "run.json"
    run_metadata = json.loads(run_path.read_text(encoding="utf-8"))
    if run_metadata.get("backend") != backend:
        raise ValueError("native run metadata does not identify the requested backend")
    trace = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return trace, report, {"binary_path": str(binary), "binary_sha256": binary_hash,
                           "trace_sha256": trace_hash, "backend": backend, "device": device,
                           "run_metadata": run_metadata, "run_metadata_sha256": file_hash(run_path),
                           "replay_summary_sha256": file_hash(Path(out) / "summary.json")}


def publish_records(bundle, model, trace, native_info, model_hash):
    """Bind every native row to its original measurement, including failed solver epochs."""
    trajectory, rows = model["trajectories"][0], bundle["observations"]
    if len(trace) != len(rows):
        raise ValueError("native trace sample count does not match actual SATNAV results")
    cfg, anchor = bundle["config"], bundle["anchor"]
    head, records = "0" * 64, []
    frame_id = digest(anchor, domain=DOMAIN + ":frame")
    for index, (row, sample, native) in enumerate(zip(rows, trajectory["samples"], trace)):
        expected = {"trajectory_id": trajectory["id"], "epoch_id": row["epoch_id"], "step": index,
                    "time_after": row["time"], "observation_valid": row["valid"],
                    "target": row["enu_m"], "observed_ecef": row["ecef_m"], "clock_bias_m": row["clock_bias_m"]}
        if any(native.get(key) != value for key, value in expected.items()):
            raise ValueError(f"native trace does not bind to original SATNAV sample {row['epoch_id']}")
        if native["status"] not in ("advanced", "numeric_failure", "previous_failure"):
            raise ValueError("unknown native physical status")
        p, v, phi = native["p_after"], native["v_after"], native["phi_after"]
        physical_valid = native["status"] == "advanced"
        if physical_valid:
            p, v, phi = vector(p, "native p_after"), vector(v, "native v_after"), finite_number(phi, "native phi_after")
            modeled_ecef = list(enu_to_ecef(p, anchor["ecef_m"], anchor["lat_rad"], anchor["lon_rad"]))
            chart, packing = chart_and_keys(p, row["time"], phi, cfg, trajectory["chart"])
        else:
            modeled_ecef, packing = None, None
            chart, _ = chart_and_keys(p if isinstance(p, list) and len(p) == 3 else [None] * 3,
                                     row["time"], phi, cfg, trajectory["chart"], native["status"])
        event = ("COUPLED_OBSERVATION_ADVANCED" if row["valid"] else "COUPLED_PREDICTION_ADVANCED") if physical_valid else native["status"].upper()
        record = {"version": VERSION, "profile": "CGK-R1", "trajectory_id": trajectory["id"],
                  "epoch_id": row["epoch_id"], "input_index": index, "t_gpst_s": row["time"],
                  "time_scale": "GPST", "frame_id": frame_id,
                  "event": event, "transition": "coupled_geometry_ASA_NA_JK_backward_Euler",
                  "observation": {"solver_status": row["solver_record"]["status"], "valid": row["valid"],
                                  "ecef_m": row["ecef_m"], "enu_m": row["enu_m"],
                                  "position_meaning": "converged_receiver_fix" if row["valid"] else "solver_seed_or_partial_iterate",
                                  "clock_bias_m": row["clock_bias_m"],
                                  "formal_variance_m2": {"x": row["formal_variance_m2"][0], "y": row["formal_variance_m2"][1],
                                                         "z": row["formal_variance_m2"][2], "clock": row["formal_variance_m2"][3]},
                                  "solver_record": row["solver_record"], "epoch_record": row["epoch_record"],
                                  "residual_records": row["residual_records"],
                                  "residual_diagnostic": residual_diagnostic(row, cfg)},
                  "modeled": {"valid": physical_valid, "status": native["status"], "enu_m": p, "ecef_m": modeled_ecef,
                              "velocity_enu_m_s": v, "q": native["q_after"], "hoop_phi_rad": phi,
                              "clock_model": "observed receiver clock retained separately; no dynamic clock estimator",
                              "quantity": "CGK-R1 mechanical observer position"},
                  "jk": {"before": native["q_before"], "j": native["j"], "k": native["k"], "after": native["q_after"]},
                  "native_state": native, "chart": chart, "packing": packing,
                  "lineage": {"sources": bundle["sources"], "model_sha256": model_hash,
                              "native": native_info, "hash_domain": DOMAIN}, "previous_hash": head}
        head = digest(record, domain=DOMAIN)
        record["record_hash"] = head
        records.append(record)
    return records, head


def process(input_dir, run_dir, *, out=None, coupled_profile=None, backend="cpu", binary=None, device=0):
    if backend not in ("cpu", "cuda") or type(device) is not int or device < 0:
        raise ValueError("backend must be cpu/cuda and device must be nonnegative")
    input_dir, run_dir = Path(input_dir), Path(run_dir)
    destination = Path(out) if out is not None else run_dir
    profile_path = Path(coupled_profile) if coupled_profile is not None else DEFAULT_PROFILE
    binary = Path(binary) if binary is not None else ROOT / "bin" / "windows" / backend / "coupled_kernel.exe"
    binary.resolve(strict=True)  # Never publish a Python-only run as a native handoff.
    bundle = read_sources(input_dir, run_dir, profile_path)
    model = build_model(bundle)
    if out is not None:
        destination.mkdir(parents=True, exist_ok=False)
    for name in ("coupled_model.json", "coupled", "ugts_events.jsonl", "ugts_summary.json"):
        if (destination / name).exists():
            raise FileExistsError(f"new output files required; already exists: {destination / name}")
    model_path = destination / "coupled_model.json"
    _dump_new(model_path, model)
    model_hash = file_hash(model_path)
    trace, replay, native_info = execute_native(model_path, destination / "coupled", binary, backend, device)
    assert_sources_unchanged(bundle)
    if file_hash(model_path) != model_hash:
        raise ValueError("generated coupled model changed during execution")
    records, head = publish_records(bundle, model, trace, native_info, model_hash)
    counts = {}
    for record in records:
        counts[record["event"]] = counts.get(record["event"], 0) + 1
    with (destination / "ugts_events.jsonl").open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
    summary = {"version": VERSION, "profile": "CGK-R1", "samples": len(records), "events": counts,
               "head_sha256": head, "hash_domain": DOMAIN, "backend": backend,
               "native_execution": "passed", "native_trace_verified": True,
               "replay_summary": replay, "model_sha256": model_hash,
               "source_records_retained": True, "sample_order": "input_epoch_order",
               "model_origin": bundle["profile"]["model_origin"],
               "equations": model["equations"], "initialization": model["provenance"]["initialization"],
               "scope": "Coupled mechanical observer driven by decoded SATNAV solutions; original solver state and modeled state remain distinct."}
    _dump_new(destination / "ugts_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--coupled-profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()
    try:
        result = process(args.input, args.run, out=args.out, coupled_profile=args.coupled_profile,
                         backend=args.backend, binary=args.binary, device=args.device)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
