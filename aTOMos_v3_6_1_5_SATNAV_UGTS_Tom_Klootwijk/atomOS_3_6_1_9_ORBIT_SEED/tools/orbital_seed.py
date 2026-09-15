#!/usr/bin/env python3
"""Pack, inspect, query and replay complete ORBIT-SEED-R1 orbital seeds."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from orbit_native import NativeOrbit
from orbit_query import OrbitSession, station_events
from orbit_seed import (PROFILE, VERSION, default_feedback, default_query, default_stations,
                        inspect_bytes, load, load_json, pack_bytes, unpack_bytes)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def wrap_model(path, object_id, orbit_class):
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    model = record["model"]
    return {"profile": PROFILE, "version": VERSION,
            "object": {"id": object_id, "orbit_class": orbit_class}, "model": model,
            "description": "Physical initial-state seed fitted from earlier target data; future target positions excluded",
            "stations": default_stations(), "query": default_query(0., model["domain_s"][1]),
            "feedback": default_feedback(),
            "provenance": {"fit": record.get("fit", {}), "construction": record.get("construction", {}),
                           "source_file": Path(path).name,
                           "source_role": "Construction provenance only; replay dependencies embedded in model"},
            "encoding": {"orbital_state": "IEEE754 binary64, lossless", "future_target_table": False,
                         "shared_runtime": model["profile"] + " plus original ASA/NA/JK/UGTS implementations"}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    wrap = sub.add_parser("wrap", help="Add editable station/query/equation inputs to a fitted model")
    wrap.add_argument("--model", type=Path, required=True)
    wrap.add_argument("--object-id", required=True)
    wrap.add_argument("--orbit-class", required=True)
    wrap.add_argument("--out", type=Path, required=True)
    pack = sub.add_parser("pack")
    pack.add_argument("--input", type=Path, required=True)
    pack.add_argument("--out", type=Path, required=True)
    pack.add_argument("--codec", choices=("bitplanes64-zlib", "canonical-zlib"), default="bitplanes64-zlib")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--seed", type=Path, required=True)
    decode = sub.add_parser("unpack")
    decode.add_argument("--seed", type=Path, required=True)
    decode.add_argument("--out", type=Path, required=True)
    for command in ("query", "predict", "events"):
        run = sub.add_parser(command)
        run.add_argument("--seed", type=Path, required=True)
        run.add_argument("--worker", type=Path, required=True)
        run.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
        run.add_argument("--station")
        if command == "query": run.add_argument("--time-s", type=float, required=True)
        else:
            run.add_argument("--start-s", type=float)
            run.add_argument("--end-s", type=float)
        run.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if args.command == "wrap":
        write_json(args.out, wrap_model(args.model, args.object_id, args.orbit_class))
    elif args.command == "pack":
        seed = load_json(args.input)
        data = pack_bytes(seed, codec=args.codec)
        if unpack_bytes(data) != seed: raise RuntimeError("Seed round trip failed")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("xb") as stream: stream.write(data)
        print(json.dumps(inspect_bytes(data), indent=2))
    elif args.command == "inspect":
        print(json.dumps(inspect_bytes(args.seed.read_bytes()), indent=2))
    elif args.command == "unpack":
        write_json(args.out, load(args.seed))
    else:
        seed = load(args.seed)
        with NativeOrbit(args.worker, seed["model"], args.backend) as worker:
            session = OrbitSession(seed, worker, args.station)
            if args.command == "query": write_json(args.out, session.query(args.time_s))
            elif args.command == "events": write_json(args.out, station_events(session, args.start_s, args.end_s))
            else:
                args.out.mkdir(parents=True, exist_ok=False)
                count = 0
                with (args.out / "trace.jsonl").open("x", encoding="utf-8") as stream:
                    for record in session.schedule(args.start_s, args.end_s):
                        stream.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
                        count += 1
                write_json(args.out / "summary.json", {"seed": inspect_bytes(args.seed.read_bytes()),
                    "station": session.station, "queries": count, "worker": worker.ready,
                    "start_s": seed["query"]["start_s"] if args.start_s is None else args.start_s,
                    "end_s": seed["query"]["end_s"] if args.end_s is None else args.end_s,
                    "final_record_sha256": record["record_sha256"],
                    "stats": worker.stats(), "trace_bytes": (args.out / "trace.jsonl").stat().st_size})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
