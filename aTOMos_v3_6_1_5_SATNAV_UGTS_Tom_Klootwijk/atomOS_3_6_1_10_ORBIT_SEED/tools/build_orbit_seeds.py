#!/usr/bin/env python3
"""Construct four editable seed inputs and compact packs from frozen fitted models."""
from pathlib import Path
import argparse
import json
from orbital_seed import ROOT, wrap_model
from orbit_seed import pack_bytes, inspect_bytes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=ROOT / "examples/orbit/seeds")
    p.add_argument("--models", type=Path, default=ROOT / "examples/orbit/models")
    p.add_argument("--replace-generated", action="store_true")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    classes = {"G05": "MEO", "C03": "GEO", "C06": "IGSO", "CHANDRA": "HEO"}
    reports = []
    for name, kind in classes.items():
        seed = wrap_model(args.models / (name + ".json"), name, kind)
        data = pack_bytes(seed)
        paths = [args.out / (name + suffix) for suffix in (".json", ".orbseed")]
        if not args.replace_generated and any(path.exists() for path in paths):
            p.error("Output exists; choose a new directory or explicitly replace generated seeds")
        paths[0].write_text(json.dumps(seed, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        paths[1].write_bytes(data)
        report = inspect_bytes(data)
        report["canonical_codec_comparison_bytes"] = len(pack_bytes(seed, codec="canonical-zlib"))
        report["packing_error_bits"] = 0
        reports.append(report)
    (args.out / "seed_sizes.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{ "object": r["object"]["id"], "bytes": r["file_bytes"] } for r in reports]))


if __name__ == "__main__": main()
