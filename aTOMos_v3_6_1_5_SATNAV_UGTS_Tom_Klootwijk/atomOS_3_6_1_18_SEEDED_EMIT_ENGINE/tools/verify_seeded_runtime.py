#!/usr/bin/env python3
"""Verify a completed native seeded artifact against full original CPU replay.

This tool does not launch the native executable. It compares every ordered event
field, every final State64 word, and every output byte; hashes are additional
identifiers, not substitutes for equality or source authenticity guarantees.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from build_seeded_fixtures import (
    ROOT, FIXTURES, SOURCES, SPECS, imports, sha, strict_json, verify_pins, write_json,
)

EVENT_FIELDS = ("sequence", "epoch", "lane", "cell_before", "flags", "payload", "byte_count",
                "byte_order", "lineage", "cell_after", "branch_after", "status_after")


def integer(value, name, maximum=(1 << 64) - 1):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError(name + " must be a bounded nonnegative integer")
    return value


def replay_reference(fixture):
    if fixture not in SPECS:
        raise ValueError("unknown fixture")
    verify_pins()
    _, core, fmt, materialize, _, _ = imports()
    spec = SPECS[fixture]
    filename = Path(spec["source"]).name.replace(".literal.json", ".tmg")
    path = FIXTURES / fixture / filename
    binary = path.read_bytes()
    original = (SOURCES / spec["source"]).with_name(filename).read_bytes()
    if binary != original:
        raise ValueError("native input program differs from pinned original bytes")
    program = fmt.loads(binary)
    if fmt.dumps(program) != binary:
        raise ValueError("noncanonical program roundtrip")
    state, trace = core.run(program, trace=True)
    output, records = materialize.materialize_trace(program, trace)
    if not state.status & core.STATUS_HALT:
        raise ValueError("reference does not complete within its declared horizon")
    if output != (SOURCES / spec["materialized"]).read_bytes():
        raise ValueError("replayed materializer differs from pinned original artifact")
    events = []
    for record in records:
        row = trace[record.step]
        events.append({"sequence": record.sequence, "epoch": record.step, "lane": 0,
                       "cell_before": record.cell_index, "flags": record.flags,
                       "payload": record.payload, "byte_count": record.byte_count,
                       "byte_order": record.byte_order, "lineage": record.lineage,
                       "cell_after": row["cell_after"], "branch_after": row["branch"],
                       "status_after": row["status"]})
    return {"fixture": fixture, "program_bytes": len(binary), "program_sha256": sha(binary),
            "program_flags": program.flags, "executed_steps": len(trace),
            "events": events, "final_state_words": state.words(), "output": output}


def compare_native(reference, native, output: bytes, ticks: int):
    integer(ticks, "ticks", (1 << 32) - 1)
    if ticks < reference["executed_steps"]:
        raise ValueError("requested horizon does not include the complete reference artifact")
    if not isinstance(native, dict) or native.get("profile") != "ATOMOS-EMIT-JOURNAL-R1":
        raise ValueError("unknown native journal profile")
    if native.get("status") != "complete":
        raise ValueError("native journal is not a completed artifact")
    for field in ("artifact_written", "expanded_source_bytes_equal_input"):
        if native.get(field) is not True:
            raise ValueError("native completion evidence must be true: " + field)
    for field in ("owner_id", "generation"):
        integer(native.get(field), field)
    expected_header = {"start_epoch": 0, "end_epoch": ticks, "error": 0,
                       "program_flags": reference["program_flags"],
                       "program_bytes": reference["program_bytes"],
                       "event_count": len(reference["events"]),
                       "output_bytes": len(reference["output"])}
    for field, expected in expected_header.items():
        actual = integer(native.get(field), field)
        if actual != expected:
            raise ValueError("native header mismatch: " + field)
    states = native.get("final_state_words")
    if not isinstance(states, list) or len(states) != 16:
        raise ValueError("native final State64 must contain sixteen words")
    for index, (actual, expected) in enumerate(zip(states, reference["final_state_words"])):
        if integer(actual, "State64 word", (1 << 32) - 1) != expected:
            raise ValueError("native final State64 mismatch at word " + str(index))
    rows = native.get("events")
    if not isinstance(rows, list) or len(rows) != len(reference["events"]):
        raise ValueError("native journal event count differs from full replay")
    for index, (actual, expected) in enumerate(zip(rows, reference["events"])):
        if not isinstance(actual, dict):
            raise ValueError("native event must be an object")
        for field in EVENT_FIELDS:
            value = actual.get(field)
            if field != "byte_order":
                integer(value, "event " + field)
            if value != expected[field]:
                raise ValueError("native event mismatch at sequence %d field %s" % (index, field))
    if output != reference["output"]:
        mismatch = next((i for i, pair in enumerate(zip(output, reference["output"])) if pair[0] != pair[1]),
                        min(len(output), len(reference["output"])))
        raise ValueError("native artifact byte mismatch at offset " + str(mismatch))
    return {"fixture": reference["fixture"], "status": "verified_complete",
            "program_sha256": reference["program_sha256"], "requested_ticks": ticks,
            "compared_events": len(rows), "compared_event_fields": len(rows) * len(EVENT_FIELDS),
            "compared_final_state_words": 16, "compared_output_bytes": len(output),
            "output_sha256": sha(output), "native_status": native["status"],
            "checks": "Every ordered event field, every final state word, and every artifact byte equal fresh original Python replay/materialization.",
            "scope": "Native execution emits the host-compiled bytes. The source formal expression tree was evaluated on the host."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=list(SPECS), required=True)
    parser.add_argument("--report", type=Path, required=True, help="Actual native journal JSON")
    parser.add_argument("--artifact", type=Path, required=True, help="Actual native materialized bytes")
    parser.add_argument("--ticks", type=int, required=True)
    parser.add_argument("--output", type=Path, help="Write verification evidence JSON")
    args = parser.parse_args()
    reference = replay_reference(args.fixture)
    native_raw = args.report.read_bytes()
    result = compare_native(reference, strict_json(native_raw), args.artifact.read_bytes(), args.ticks)
    result.update({"native_report": str(args.report), "native_report_sha256": sha(native_raw),
                   "native_artifact": str(args.artifact),
                   "source_manifest_sha256": sha((FIXTURES / "source_manifest.json").read_bytes())})
    if args.output:
        write_json(args.output, result)
    import json
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
