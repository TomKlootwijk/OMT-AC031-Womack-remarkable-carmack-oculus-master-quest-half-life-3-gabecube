#!/usr/bin/env python3
"""Study atomos.radio.v1 JSONL, or losslessly pack/unpack its original bytes."""
from pathlib import Path
import argparse
from decimal import Decimal
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from atomos_radio import pack_bytes, unpack_bytes, study_file


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    study = commands.add_parser("study", help="Preserve source and produce CSV, summary and plots")
    study.add_argument("input", type=Path)
    study.add_argument("output", type=Path)
    study.add_argument("--no-plots", action="store_true")
    study.add_argument("--label", help="Visible study/plot label; preserves the supplied source bytes")
    study.add_argument("--stale-after-seconds", type=Decimal, default=Decimal(30))
    study.add_argument("--wall-jump-seconds", type=Decimal, default=Decimal(2))
    for name in ("pack", "unpack"):
        command = commands.add_parser(name)
        command.add_argument("input", type=Path)
        command.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "study":
            result = study_file(args.input, args.output, plots=not args.no_plots, label=args.label,
                stale_after_seconds=args.stale_after_seconds, wall_jump_seconds=args.wall_jump_seconds)
            print(json.dumps({"output": str(args.output), "input_sha256": result["input_sha256"],
                "radio_records": result["radio_records"], "invalid_rows": len(result["invalid_rows"]),
                "issues": len(result["issues"]), "plots": len(result["plots"])}, indent=2))
            return 0
        if args.input.resolve() == args.output.resolve():
            raise ValueError("input and output must differ")
        if args.output.exists():
            raise ValueError("output already exists; choose a new output path")
        raw = args.input.read_bytes()
        converted = pack_bytes(raw) if args.command == "pack" else unpack_bytes(raw)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as output:
            output.write(converted)
        print(json.dumps({"output": str(args.output), "bytes": len(converted),
                          "sha256": hashlib.sha256(converted).hexdigest()}))
        return 0
    except (OSError, ValueError, TypeError, ImportError) as error:
        print(f"radio study failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
