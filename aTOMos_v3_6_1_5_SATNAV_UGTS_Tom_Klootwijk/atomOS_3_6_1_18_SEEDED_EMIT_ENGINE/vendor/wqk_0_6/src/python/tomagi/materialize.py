"""Generic byte materialization from ordered TOMAGI EMIT execution records."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .core import (
    FLAG_EMIT_BIG_ENDIAN,
    FLAG_EMIT_COUNT_MASK,
    FLAG_EMIT_COUNT_SHIFT,
    Opcode,
    Program,
    State,
    PROGRAM_FLAG_EMIT_BYTES,
    PROGRAM_FLAG_SEEDED_PROFILE,
    run,
    u32,
)
from .format import load


TRACE_FIELDS = (
    "step", "cell_before", "opcode", "branch", "cell_after", "key_hi", "key_lo",
    "rho", "theta", "tick", "phi", "orientation", "sheet", "residual", "output",
    "lineage", "status",
)


@dataclass(frozen=True, slots=True)
class EmitRecord:
    sequence: int
    step: int
    cell_index: int
    flags: int
    payload: int
    byte_count: int
    byte_order: str
    data: bytes
    lineage: int

    def as_record(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "step": self.step,
            "cell_index": self.cell_index,
            "flags": self.flags,
            "payload": self.payload,
            "byte_count": self.byte_count,
            "byte_order": self.byte_order,
            "hex": self.data.hex(),
            "lineage": self.lineage,
        }


def decode_emit_payload(flags: int, payload: int) -> tuple[bytes, int, str]:
    flags = u32(flags)
    payload = u32(payload)
    count = (flags & FLAG_EMIT_COUNT_MASK) >> FLAG_EMIT_COUNT_SHIFT
    if not 1 <= count <= 4:
        raise ValueError(f"EMIT byte count must be in 1..4, found {count}")
    if flags & FLAG_EMIT_BIG_ENDIAN:
        return payload.to_bytes(4, "big")[-count:], count, "big"
    return payload.to_bytes(4, "little")[:count], count, "little"


def _validate_trace(
    program: Program,
    trace: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Authenticate a canonical-initial-state trace prefix by deterministic replay."""
    rows = list(trace)
    _, expected = run(program, ticks=len(rows), trace=True)
    if len(expected) != len(rows):
        raise ValueError("trace continues after the program halted")
    for index, (row, reference) in enumerate(zip(rows, expected)):
        if not isinstance(row, Mapping):
            raise ValueError(f"trace row {index} must be an object")
        unknown = sorted(
            (key for key in row if key not in TRACE_FIELDS), key=repr
        )
        if unknown:
            raise ValueError(
                f"trace row {index} has unknown fields: "
                + ", ".join(repr(key) for key in unknown)
            )
        for field in TRACE_FIELDS:
            if field not in row:
                raise ValueError(f"trace row {index} is missing field {field}")
            value = row[field]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"trace row {index} field {field} must be an integer")
            if value != reference[field]:
                raise ValueError(
                    f"trace row {index} field {field} does not match deterministic replay"
                )
    return rows


def materialize_trace(
    program: Program,
    trace: Sequence[Mapping[str, Any]],
) -> tuple[bytes, list[EmitRecord]]:
    if not (program.flags & PROGRAM_FLAG_SEEDED_PROFILE):
        raise ValueError("byte materialization requires a seeded-profile program")
    if not (program.flags & PROGRAM_FLAG_EMIT_BYTES):
        raise ValueError("program does not declare emitted-byte materialization")
    validated_trace = _validate_trace(program, trace)
    output = bytearray()
    records: list[EmitRecord] = []
    for row in validated_trace:
        index = int(row["cell_before"])
        if not 0 <= index < len(program.cells):
            raise ValueError(f"trace cell index outside program: {index}")
        cell = program.cells[index]
        if cell.opcode != int(Opcode.EMIT):
            continue
        data, count, byte_order = decode_emit_payload(cell.flags, cell.payload)
        records.append(EmitRecord(
            sequence=len(records),
            step=int(row["step"]),
            cell_index=index,
            flags=cell.flags,
            payload=cell.payload,
            byte_count=count,
            byte_order=byte_order,
            data=data,
            lineage=int(row.get("lineage", 0)),
        ))
        output.extend(data)
    if not records:
        raise ValueError("execution trace contains no EMIT records")
    return bytes(output), records


def materialize_file(
    program_path: str | Path,
    destination: str | Path,
    *,
    ticks: int | None = None,
) -> tuple[bytes, State, list[dict[str, int]], list[EmitRecord]]:
    program = load(program_path)
    state, trace = run(program, ticks=ticks, trace=True)
    data, records = materialize_trace(program, trace)
    out = Path(destination)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return data, state, trace, records
