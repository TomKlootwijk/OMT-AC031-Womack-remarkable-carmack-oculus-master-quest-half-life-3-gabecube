#!/usr/bin/env python3
"""Compile and independently verify scalar SDF operator planes on M1 Klein."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from sdf_atlas import default_config, write_atlas, verify_atlas

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("geometry", "nor_sites"), default="geometry")
    parser.add_argument("--rows", type=int)
    parser.add_argument("--angles", type=int)
    parser.add_argument("--config", type=Path, help="editable JSON geometry profile")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path, help="verify an existing binary and sibling .json manifest")
    args = parser.parse_args()
    if args.verify:
        result = verify_atlas(args.verify)
        print(json.dumps({k: result[k] for k in ("rows", "angles", "verified_bits", "independent_all_bits_verified", "seam_tests")}, indent=2))
        return
    if args.out is None:
        parser.error("--out is required when compiling")
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else default_config(args.profile)
    if args.rows is not None:
        config["rows"] = args.rows
    if args.angles is not None:
        config["angles"] = args.angles
    print(json.dumps(write_atlas(config, args.out), indent=2))

if __name__ == "__main__":
    main()
