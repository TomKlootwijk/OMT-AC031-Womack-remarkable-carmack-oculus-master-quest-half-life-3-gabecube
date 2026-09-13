#!/usr/bin/env python3
"""Verify journal continuity and the supplied expected endpoint.

Verification detects changes relative to an independently retained endpoint.
It does not make a wholly rewritten journal authentic or detect truncation when
the attacker can also replace the expected endpoint and count.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

def verify(folder: Path, expected_head: str | None = None) -> dict:
    p = json.loads((folder / "provenance.json").read_text())
    root = bytes.fromhex(p["root_sha256"])
    head = hashlib.sha256(b"atomOS:genesis:v2\0" + root + p["manifest_json"].encode()).hexdigest()
    if head != p["genesis"]:
        raise ValueError("genesis mismatch")
    count = 0
    with (folder / "journal.jsonl").open() as f:
        for line in f:
            record = json.loads(line)
            if record["previous"] != head:
                raise ValueError(f"continuity failure at event {count}")
            h = hashlib.sha256(b"atomOS:event:v2\0" + bytes.fromhex(head) + record["event_json"].encode()).hexdigest()
            if record["hash"] != h:
                raise ValueError(f"event digest failure at event {count}")
            json.loads(record["event_json"])
            head = h
            count += 1
    if count != p["events"] or head != p["head"]:
        raise ValueError("count or local endpoint mismatch")
    if expected_head is not None and head != expected_head:
        raise ValueError("independently supplied endpoint mismatch")
    return {"verified_events": count, "head": head, "external_anchor_supplied": expected_head is not None}

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    p.add_argument("--expected-head")
    args = p.parse_args()
    print(json.dumps(verify(args.folder, args.expected_head), indent=2))

if __name__ == "__main__":
    main()
