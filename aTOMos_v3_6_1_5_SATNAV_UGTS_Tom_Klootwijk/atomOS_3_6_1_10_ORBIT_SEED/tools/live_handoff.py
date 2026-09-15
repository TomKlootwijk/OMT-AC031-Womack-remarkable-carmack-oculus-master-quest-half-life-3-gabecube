#!/usr/bin/env python3
"""Replay completed live fixes through the retained CGK-R1 component after capture."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from geodesy import ecef_to_geodetic
from coupled_handoff import process as coupled_process
from audit_coupled_handoff import audit as audit_publication
from verify_run import verify as verify_satnav

DOMAIN = "atomOS:LIVE-CGK-BRIDGE:3.6.1.8"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def write_csv(path, fields, rows):
    with Path(path).open("x", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def checked_run(command, logbase):
    result = subprocess.run([str(arg) for arg in command], text=True, capture_output=True)
    Path(str(logbase) + ".stdout.log").write_text(result.stdout, encoding="utf-8")
    Path(str(logbase) + ".stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"command failed with exit {result.returncode}; see {logbase}")


def process(live_run, out, satnav_binary, coupled_binary, backend="cpu", device=0,
            chart_r0_m=100000., chart_core_m=.1, tick_period_s=1.):
    live_run, out = Path(live_run).resolve(strict=True), Path(out).resolve()
    satnav_binary = Path(satnav_binary).resolve(strict=True)
    coupled_binary = Path(coupled_binary).resolve(strict=True)
    if not all(math.isfinite(value) for value in (chart_r0_m, chart_core_m, tick_period_s)) or not chart_r0_m > chart_core_m > 0 or tick_period_s <= 0:
        raise ValueError("require finite r0 > core > 0 and positive tick period")
    if backend not in ("cpu", "cuda") or type(device) is not int or device < 0:
        raise ValueError("invalid backend/device")
    original_summary = json.loads((live_run / "summary.json").read_text(encoding="utf-8"))
    traces = [json.loads(line) for line in (live_run / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    selected = [row for row in traces if row["result"]["position_available"] is True]
    if not selected or len(selected) != original_summary["positions"]:
        raise ValueError("completed live summary and trace must agree on a nonempty set of positions")
    selected_ids = [row["result"]["epoch_id"] for row in selected]
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("duplicate live epoch IDs")
    for row in selected:
        result = row["result"]
        if result["status"] != "CONVERGED" or result["native_status"] != "CONVERGED":
            raise ValueError("available live position lacks completed outer/native convergence")
        if row["passes"][-1]["solution"]["state"] != result["state_ecef_clock_m"]:
            raise ValueError("live result differs from its final native solution")
    epoch_fields, epoch_rows = read_csv(live_run / "prepared" / "epochs.csv")
    obs_fields, obs_rows = read_csv(live_run / "prepared" / "observations.csv")
    wanted = set(selected_ids)
    epochs = [row for row in epoch_rows if int(row["epoch_id"]) in wanted]
    observations = [row for row in obs_rows if int(row["epoch_id"]) in wanted]
    if [int(row["epoch_id"]) for row in epochs] != selected_ids:
        raise ValueError("prepared source rows must retain live trace order and IDs")
    by_epoch = {}
    for ob in observations:
        by_epoch.setdefault(int(ob["epoch_id"]), []).append(ob)
    previous_time = None
    for row, epoch in zip(selected, epochs):
        result, prepared = row["result"], row["passes"][-1]["prepared"]
        time = result["time_gpst_s"]
        if float(epoch["t_rx_gpst_s"]) != time or row["raw_epoch"]["time_gpst_s"] != time:
            raise ValueError("original live/prepared full times differ")
        if previous_time is not None and time <= previous_time:
            raise ValueError("selected times must increase; bridge never sorts or renumbers")
        previous_time = time
        seed = [float(epoch[key]) for key in ("x0_m", "y0_m", "z0_m", "b0_m")]
        if seed != prepared["receiver_seed_ecef_m"] + [prepared["receiver_seed_clock_m"]]:
            raise ValueError("prepared CSV seed differs from original live final-pass seed")
        source_obs = by_epoch.get(result["epoch_id"], [])
        if len(source_obs) != len(prepared["observations"]):
            raise ValueError("prepared observation count differs from original live final pass")
        for old, native in zip(source_obs, prepared["observations"]):
            if old["satellite_id"] != native["satellite_id"]:
                raise ValueError("prepared satellite identifiers differ")
            for key in obs_fields:
                if key not in ("epoch_id", "satellite_id") and float(old[key]) != native[key]:
                    raise ValueError(f"prepared observation field differs: {key}")

    out.mkdir(parents=True, exist_ok=False)
    archived = out / "original_live"
    archived.mkdir()
    sources = {}
    names = ["trace.jsonl", "events.jsonl", "summary.json", "run_metadata.json",
             "capture.rtcm3", "capture.rtcm3.json", "capture.rtcm3.timing.jsonl",
             "prepared/epochs.csv", "prepared/observations.csv", "prepared/profile.json"]
    for name in names:
        source = live_run / name
        if not source.is_file():
            continue
        destination = archived / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        before = sha(source)
        shutil.copyfile(source, destination)
        if sha(destination) != before or sha(source) != before:
            raise ValueError("live source changed while archiving")
        sources[name] = dict(original_path=str(source), preserved_copy=str(destination), sha256=before)

    first = selected[0]["result"]
    origin = first["state_ecef_clock_m"][:3]
    lat, lon, height = ecef_to_geodetic(*origin)
    omitted = [dict(epoch_id=row["result"]["epoch_id"], time_gpst_s=row["result"]["time_gpst_s"],
                    status=row["result"]["status"]) for row in traces if not row["result"]["position_available"]]
    # No copied demo profile: every local chart and diagnostic choice is explicit.
    profile = dict(version="3.6.1.8", profile="LIVE-GPS-L1-TO-CGK-R1",
        data_origin="completed remote live receiver positions, replayed after capture",
        frame="ECEF_reception_axes_satellite_at_emission", time_scale="GPST",
        anchor_ecef_m=origin, anchor_geodetic_rad_m=[lat, lon, height],
        anchor_source=dict(kind="first_computed_live_position", epoch_id=first["epoch_id"],
                           time_gpst_s=first["time_gpst_s"], reference_station_arp_used=False),
        chart_r0_m=chart_r0_m, chart_core_m=chart_core_m, rho_interval=[-20., 0.],
        chart_meaning="arbitrary local analysis origin at first computed fix; chart slope is not geodetic heading",
        hoop_phi_rad=0., epoch_tick_period_s=tick_period_s, tick_origin_gpst_s=first["time_gpst_s"],
        support_spheres_enu_m=[dict(center=[0.,0.,0.], radius=10000.)],
        support_position_bound_m=0., code_residual_bound_m=0., code_residual_budget_m=20.,
        bounds_origin="explicit uncalibrated computational diagnostic settings; no measurement-error bounds claimed",
        corrections="unchanged final outer-loop code and additive correction from live preparation",
        provenance=dict(original_live_sources=sources, included_live_epoch_ids=selected_ids,
                        omitted_unavailable_epochs=omitted,
                        omission_policy="only completed position_available=true rows; full original trace preserved",
                        application_phase="postcapture", coupled_component_version="3.6.1.7"))
    prepared_dir = out / "prepared_completed"
    prepared_dir.mkdir()
    write_csv(prepared_dir / "epochs.csv", epoch_fields, epochs)
    write_csv(prepared_dir / "observations.csv", obs_fields, observations)
    dump(prepared_dir / "profile.json", profile)
    batch_dir = out / "native_satnav_replay"
    command = [satnav_binary, "--input", prepared_dir, "--out", batch_dir, "--backend", backend, "--verify"]
    if backend == "cuda":
        command += ["--device", str(device)]
    checked_run(command, out / "native_satnav_replay")
    batch_verification = verify_satnav(prepared_dir, batch_dir)
    _, solutions = read_csv(batch_dir / "solutions.csv")
    differences = []
    for original, solution in zip(selected, solutions):
        result = original["result"]
        if int(solution["epoch_id"]) != result["epoch_id"] or float(solution["t_rx_gpst_s"]) != result["time_gpst_s"] or solution["status"] != "CONVERGED":
            raise ValueError("batch replay no longer matches completed live epoch")
        values = [float(solution[key]) for key in ("x_m", "y_m", "z_m", "clock_bias_m")]
        difference = max(abs(a-b) for a,b in zip(values, result["state_ecef_clock_m"]))
        if difference > 1e-4:
            raise ValueError("batch replay differs from original live position/clock beyond1e-4m")
        differences.append(difference)
    coupled_dir = out / "coupled_handoff"
    component_profile = ROOT / "profiles" / "COUPLED_R1.json"
    handoff_summary = coupled_process(prepared_dir, batch_dir, out=coupled_dir,
        coupled_profile=component_profile, binary=coupled_binary, backend=backend, device=device)
    publication = audit_publication(prepared_dir, batch_dir, coupled_dir,
                                    binary=coupled_binary, coupled_profile=component_profile)
    dump(coupled_dir / "publication_audit.json", publication)
    handoff_events = [json.loads(line) for line in (coupled_dir / "ugts_events.jsonl").read_text(encoding="utf-8").splitlines()]
    if handoff_summary["initialization"]["uses_future_observation"]:
        raise ValueError("bridge initialization cannot use a future unavailable-epoch fix")
    head = "0" * 64
    with (out / "live_bindings.jsonl").open("x", encoding="utf-8") as stream:
        for original, event, difference in zip(selected, handoff_events, differences):
            if event["epoch_id"] != original["result"]["epoch_id"]:
                raise ValueError("CGK epoch ID differs from preserved original live result")
            binding = dict(version="3.6.1.8", hash_domain=DOMAIN, previous_hash=head,
                original_live_result=original["result"], original_live_trace_sha256=sources["trace.jsonl"]["sha256"],
                coupled_event_record_hash=event["record_hash"],
                max_original_to_batch_state_difference_m=difference,
                computed_receiver_state=event["observation"], modeled_cgk_state=event["modeled"],
                full_time_gpst_s=event["t_gpst_s"], jk=event["jk"], chart=event["chart"], packing=event["packing"])
            payload = json.dumps(binding, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            head = hashlib.sha256((DOMAIN + "\0").encode() + payload).hexdigest()
            stream.write(json.dumps(dict(binding, record_hash=head), separators=(",", ":"), allow_nan=False) + "\n")
    for source in sources.values():
        if sha(source["original_path"]) != source["sha256"] or sha(source["preserved_copy"]) != source["sha256"]:
            raise ValueError("original live source or preserved copy changed during execution")
    summary = dict(status="passed", version="3.6.1.8", phase="postcapture",
        coupled_component_version="3.6.1.7", source_live_run=str(live_run), backend=backend,
        selected_completed_positions=len(selected), original_trace_epochs=len(traces),
        omitted_status_counts=dict(Counter(row["status"] for row in omitted)), omitted_epochs=omitted,
        included_epoch_ids=selected_ids, original_live_sources=sources,
        fixed_local_anchor=profile["anchor_source"], anchor_ecef_m=origin,
        first_state_at_chart_origin=True, caster_coordinates_used=False,
        initial_future_observation_used=False,
        maximum_batch_vs_original_position_clock_difference_m=max(differences),
        satnav_independent_verification=batch_verification,
        coupled_native_replay=handoff_summary["replay_summary"], publication_audit=publication,
        binding_head_sha256=head, bindings_sha256=sha(out / "live_bindings.jsonl"),
        limitations="CGK is an uncalibrated postcapture mechanical observer; modeled state is distinct from receiver position and does not feed back into the GNSS solve")
    dump(out / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--satnav-binary", type=Path, required=True)
    parser.add_argument("--coupled-binary", type=Path, required=True)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--chart-r0-m", type=float, default=100000.)
    parser.add_argument("--chart-core-m", type=float, default=.1)
    parser.add_argument("--tick-period-s", type=float, default=1.)
    args = parser.parse_args()
    result = process(args.live_run, args.out, args.satnav_binary, args.coupled_binary,
        args.backend, args.device, args.chart_r0_m, args.chart_core_m, args.tick_period_s)
    print(json.dumps({key:result[key] for key in ("status","phase","backend","selected_completed_positions",
        "omitted_status_counts","maximum_batch_vs_original_position_clock_difference_m","binding_head_sha256")}, indent=2))


if __name__ == "__main__":
    main()
