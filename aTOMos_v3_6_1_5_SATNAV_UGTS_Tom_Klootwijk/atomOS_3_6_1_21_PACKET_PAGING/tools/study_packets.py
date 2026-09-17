#!/usr/bin/env python3
"""Decode an existing local PCAP/PCAPNG with TShark; no live capture or lookups."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from atomos_packets import DEFAULT_TSHARK, study_capture


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tshark", type=Path, default=DEFAULT_TSHARK)
    parser.add_argument("--label")
    parser.add_argument("--packet-limit", type=int, default=100000)
    parser.add_argument("--timeout-seconds", type=float, default=45)
    parser.add_argument("--udp-offset", type=int, default=0, help="Zero-based offset among decoded UDP matches")
    parser.add_argument("--udp-limit", type=int, default=200, help="UDP records on this page, 1..200 (default 200)")
    args = parser.parse_args(argv)
    try:
        summary = study_capture(args.input, args.output, tshark=args.tshark,
            label=args.label, packet_limit=args.packet_limit, timeout_seconds=args.timeout_seconds,
            udp_offset=args.udp_offset, udp_limit=args.udp_limit)
        print(json.dumps({"output": str(args.output), "status": summary["status"],
            "input_sha256": summary["input_sha256"], "decoded_packets": summary["decoded_packet_rows"],
            "udp_page": summary["udp_readable"],
            "errors": len(summary["decoder_errors"])}, indent=2))
        return 0 if summary["status"] == "decoded" else 2
    except (OSError, ValueError, TypeError) as error:
        print(f"packet study failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
