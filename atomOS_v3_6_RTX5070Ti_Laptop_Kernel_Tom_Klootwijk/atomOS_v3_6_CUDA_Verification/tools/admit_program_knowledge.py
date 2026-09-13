#!/usr/bin/env python3
"""Admit independently checked, semantically novel finite program LUT capsules."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from knowledge_admission import admit_candidates, demo_request, read_request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-bank", type=Path, required=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--candidates", type=Path, help="atomos-knowledge-candidates-v1 JSON")
    inputs.add_argument("--make-demo-candidates", type=Path, help="write the synthetic learned_v1 fixture to a new JSON file")
    parser.add_argument("--out", type=Path, help="new immutable result directory; no active pointer is changed")
    parser.add_argument("--candidate-limit", type=int, default=64)
    args = parser.parse_args()
    try:
        if args.make_demo_candidates:
            if args.out:
                parser.error("--out is for admission, not demo generation")
            fixture = demo_request(args.base_bank)
            args.make_demo_candidates.parent.mkdir(parents=True, exist_ok=True)
            with args.make_demo_candidates.open("x", encoding="utf-8") as stream:
                json.dump(fixture, stream, indent=2)
                stream.write("\n")
            print(json.dumps({"status": "written", "candidates": str(args.make_demo_candidates),
                              "source": "synthetic independent Boolean specifications; no model run"}, indent=2))
            return 0
        if args.out is None:
            parser.error("--out is required with --candidates")
        receipt = admit_candidates(args.base_bank, read_request(args.candidates), args.out,
                                   candidate_limit=args.candidate_limit)
        print(json.dumps({"status": receipt["status"], "accepted_capsules": receipt["accepted_capsules"],
                          "rejected_candidates": receipt["rejected_candidates"],
                          "receipt": str(args.out / "admission.json"),
                          "bank": str(args.out / "bank.bin") if receipt["accepted_capsules"] else None,
                          "gpu_execution": "not_run", "active_bank_changed": False}, indent=2))
        return 0
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"status": "rejected", "error": str(error)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
