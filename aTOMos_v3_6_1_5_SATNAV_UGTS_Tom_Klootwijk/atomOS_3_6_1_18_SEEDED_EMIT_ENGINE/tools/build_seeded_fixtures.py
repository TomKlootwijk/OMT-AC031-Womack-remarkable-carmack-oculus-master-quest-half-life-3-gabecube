#!/usr/bin/env python3
"""Reproduce pinned original seeded programs with the unchanged vendor compiler.

Only --import-from reads an external source tree. All subsequent builds use the
copied, hash-checked inputs. This is CPU compilation/reference execution, not GPU
formal evaluation. No generated program is represented as new native reasoning.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples/seeded18"
SOURCES = FIXTURES / "source"
VENDOR = ROOT / "vendor/wqk_0_6"
SPECS = {
    "world03": {
        "source": "examples/world03/world03_release_artifact.literal.json",
        "materialized": "validation/world03/TOM_WORLD_QUERY_KERNEL_0_3_RELEASE.materialized.md",
    },
    "family_authority": {
        "source": "examples/learner06/learner06_family_authority.literal.json",
        "materialized": "validation/learner06/learner_authority.materialized.json",
        "direct": "validation/learner06/learner_authority.direct.json",
    },
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    def reject(value):
        raise ValueError("non-finite JSON token: " + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=reject)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def confined(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    return resolved


def import_sources(original: Path):
    original = original.resolve()
    selected = {"TOM_seed_genome_2026-09-01.txt", "spec/tom_seed_token_registry_1_0.json",
                "spec/tom_seeded_program.schema.json"}
    for spec in SPECS.values():
        source = original / spec["source"]
        document = strict_json(source.read_bytes())
        selected.add(spec["source"])
        for field in ("path", "token_registry"):
            selected.add(confined(original, source.parent / document["seed_genome"][field]).relative_to(original).as_posix())
        for definition in document["definitions"]:
            if definition["operation"]["op"] == "source.json":
                selected.add(confined(original, source.parent / definition["parameters"]["path"]).relative_to(original).as_posix())
        for field in ("materialized", "direct"):
            if field in spec:
                selected.add(spec[field])
        program = spec["source"].replace(".literal.json", ".tmg")
        selected.update((program, program + ".compile.json"))
    files = []
    for relative in sorted(selected):
        raw = confined(original, original / relative).read_bytes()
        destination = SOURCES / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        files.append({"path": relative, "bytes": len(raw), "sha256": sha(raw)})
    implementation = []
    for path in sorted((VENDOR / "src/python/tomagi").glob("*.py")):
        relative = path.relative_to(VENDOR).as_posix()
        raw = path.read_bytes()
        if raw != (original / relative).read_bytes():
            raise ValueError("vendor implementation differs from original: " + relative)
        implementation.append({"path": relative, "bytes": len(raw), "sha256": sha(raw)})
    write_json(FIXTURES / "source_manifest.json", {
        "profile": "ATOMOS-R18-ORIGINAL-SEEDED-INPUTS-R1",
        "original_root": str(original), "files": files,
        "unchanged_vendor_implementation": implementation,
        "note": "Exact copied source bytes; original tree read only. Existing vendor NOTICE/provenance applies; no new license asserted.",
    })


def verify_pins():
    manifest = strict_json((FIXTURES / "source_manifest.json").read_bytes())
    for key, base in (("files", SOURCES), ("unchanged_vendor_implementation", VENDOR)):
        for item in manifest[key]:
            raw = confined(base, base / item["path"]).read_bytes()
            if len(raw) != item["bytes"] or sha(raw) != item["sha256"]:
                raise ValueError("pinned input changed: " + item["path"])
    return manifest


def imports():
    sys.path.insert(0, str(VENDOR / "src/python"))
    from tomagi import compiler, core, format, materialize, formal, canonical
    return compiler, core, format, materialize, formal, canonical


def direct_bytes(document, source, formal, canonical):
    """Independent route through declared input bindings to direct formal output.

    This deliberately handles these pinned fixture shapes, not a replacement
    seeded compiler. The original formal evaluator remains the authority.
    """
    nodes = {d["id"]: d for d in document["definitions"]}
    values = {}
    def input_value(ident):
        if ident not in values:
            node = nodes[ident]
            op = node["operation"]["op"]
            if op == "source.json":
                values[ident] = strict_json((source.parent / node["parameters"]["path"]).read_bytes())
            elif op == "sequence.construct":
                values[ident] = [input_value(dep) for dep in node["dependencies"]]
            else:
                raise ValueError("unsupported direct input binding: " + op)
        return values[ident]
    evaluations = [d for d in nodes.values() if d["operation"]["op"] == "formal.evaluate"]
    if evaluations:
        if len(evaluations) != 1:
            raise ValueError("fixture direct route requires one formal evaluation")
        node = evaluations[0]
        budget = document["budgets"]
        limits = formal.Limits(max_steps=budget["max_expression_nodes"],
                               max_depth=budget["max_expression_depth"],
                               max_collection_items=budget["max_sequence_items"],
                               max_value_nodes=budget["max_expression_nodes"],
                               max_canonical_bytes=budget["max_output_bytes"])
        result = formal.run_program(input_value(node["dependencies"][0]),
                                    {node["parameters"]["input_name"]: input_value(node["dependencies"][1])}, limits=limits)
        encodings = [d for d in nodes.values() if d["operation"]["op"] == "canonical.encode"
                     and d["dependencies"] == [node["id"]]]
        if len(encodings) != 1:
            raise ValueError("fixture direct canonical encoding is ambiguous")
        raw = canonical.canonical_bytes(result)
        if encodings[0]["parameters"]["terminal_newline"]:
            raw += b"\n"
        return raw, result
    emit = next(d for d in nodes.values() if d["operation"]["op"] == "emit.graph")
    literal = nodes[emit["dependencies"][0]]
    if literal["operation"]["op"] != "literal" or literal["parameters"]["result_type"] != "bytes":
        raise ValueError("unsupported direct literal fixture")
    encoded = literal["parameters"]["value"]
    if encoded["encoding"] != "base64":
        raise ValueError("unsupported direct byte encoding")
    return base64.b64decode(encoded["data"], validate=True), None


def build_fixture(name: str, spec: dict):
    compiler, core, fmt, materialize, formal, canonical = imports()
    source = SOURCES / spec["source"]
    document = strict_json(source.read_bytes())
    destination_dir = FIXTURES / name
    destination_dir.mkdir(parents=True, exist_ok=True)
    binary_name = source.name.replace(".literal.json", ".tmg")
    destination = destination_dir / binary_name
    started = time.perf_counter()
    result = compiler.compile_file_result(source, destination)
    if result is None:
        raise ValueError("fixture silently used legacy compilation")
    first = destination.read_bytes()
    sidecar = destination.with_suffix(".tmg.compile.json").read_bytes()
    with tempfile.TemporaryDirectory(prefix="r18-repeat-") as temp:
        repeat = Path(temp) / binary_name
        compiler.compile_file_result(source, repeat)
        if repeat.read_bytes() != first or repeat.with_suffix(".tmg.compile.json").read_bytes() != sidecar:
            raise ValueError("seeded build is not byte-repeatable")
    original_program = source.with_name(binary_name)
    if first != original_program.read_bytes() or sidecar != original_program.with_suffix(".tmg.compile.json").read_bytes():
        raise ValueError("recompiled bytes/sidecar differ from preserved original: " + name)
    if fmt.dumps(fmt.loads(first)) != first:
        raise ValueError("ABI decode/re-encode differs")
    compile_seconds = time.perf_counter() - started
    direct, evaluated = direct_bytes(document, source, formal, canonical)
    stored = (SOURCES / spec["materialized"]).read_bytes()
    if direct != stored or ("direct" in spec and direct != (SOURCES / spec["direct"]).read_bytes()):
        raise ValueError("direct evaluation/encoding differs from original output")
    state, trace = core.run(result.program, trace=True)
    output, source_records = materialize.materialize_trace(result.program, trace)
    if not state.status & core.STATUS_HALT or output != direct:
        raise ValueError("original materializer did not produce complete direct bytes")
    records = []
    for item in source_records:
        row = trace[item.step]
        records.append({"sequence": item.sequence, "epoch": item.step,
                        "cell_before": item.cell_index, "flags": item.flags,
                        "payload": item.payload, "byte_count": item.byte_count,
                        "byte_order": item.byte_order, "lineage": item.lineage,
                        "cell_after": row["cell_after"], "branch_after": row["branch"],
                        "status_after": row["status"]})
    destination_dir.joinpath("expected.bin").write_bytes(output)
    write_json(destination_dir / "expected_journal.json", {
        "profile": "ATOMOS-R18-PYTHON-JOURNAL-REFERENCE-R1", "fixture": name,
        "program_bytes": len(first), "program_sha256": sha(first),
        "program_flags": result.program.flags, "executed_steps": len(trace),
        "recommended_ticks": len(trace) + 3, "event_count": len(records),
        "output_bytes": len(output), "output_sha256": sha(output),
        "final_state_words": state.words(), "events": records,
    })
    if evaluated is not None:
        destination_dir.joinpath("direct_formal.json").write_bytes(direct)
    return {"fixture": name, "program": destination.relative_to(ROOT).as_posix(),
            "expected_output": (destination_dir / "expected.bin").relative_to(ROOT).as_posix(),
            "expected_journal": (destination_dir / "expected_journal.json").relative_to(ROOT).as_posix(),
            "program_bytes": len(first), "program_sha256": sha(first),
            "cells": len(result.program.cells), "events": len(records), "output_bytes": len(output),
            "output_sha256": sha(output), "recommended_ticks": len(trace) + 3,
            "definitions": len(result.definition_order),
            "evaluated_definitions": len(result.report["evaluated_definition_order"]),
            "resolved_sources": len(result.report.get("resolved_sources", [])),
            "host_formal_steps": evaluated["steps"] if evaluated else None,
            "native_opcodes": {core.Opcode(op).name: sum(c.opcode == op for c in result.program.cells)
                               for op in sorted({c.opcode for c in result.program.cells})},
            "formal_expression_lowered_to_native": False,
            "two_compile_seconds": compile_seconds,
            "checks": {"seeded_profile": True, "two_full_programs_equal": True,
                       "two_full_sidecars_equal": True, "original_program_equal": True,
                       "original_sidecar_equal": True, "abi_roundtrip_equal": True,
                       "direct_bytes_equal_original": True, "materializer_bytes_equal_direct": True,
                       "reference_terminal_halt": True},
            "native_execution": "Not run by this CPU fixture builder; separate per-record/per-byte verifier required."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-from", type=Path)
    parser.add_argument("--fixture", choices=["all", *SPECS], default="all")
    args = parser.parse_args()
    if args.import_from:
        import_sources(args.import_from)
    manifest = verify_pins()
    rows = []
    for name in SPECS if args.fixture == "all" else [args.fixture]:
        print("Building original seeded fixture " + name, flush=True)
        row = build_fixture(name, SPECS[name])
        rows.append(row)
        print(json.dumps(row, indent=2), flush=True)
    report = {"profile": "ATOMOS-R18-SEEDED-REFERENCE-R1", "fixtures": rows,
              "source_files": len(manifest["files"]),
              "source_manifest_sha256": sha((FIXTURES / "source_manifest.json").read_bytes()),
              "execution_scope": "Host Python formal computation and original seeded compilation, followed by original CPU VM/materializer. Native execution is separate."}
    write_json(ROOT / "review/r18_seeded_reference.json", report)


if __name__ == "__main__":
    main()
