"""Binary .tmg format for TOMAGI 1.0."""
from __future__ import annotations

import struct
from pathlib import Path

from .core import Cell, Program, State

MAGIC = b"TOMAGI1\0"
VERSION_WORD = 0x00010000
HEADER_SIZE = 128
CELL_SIZE = 48
STATE_SIZE = 64
_HEADER = struct.Struct("<8s14I")  # 64 bytes: magic + eight fields + six reserved
_STATE = struct.Struct("<16I")
_CELL = struct.Struct("<12I")


def dumps(program: Program) -> bytes:
    header = _HEADER.pack(
        MAGIC,
        VERSION_WORD,
        program.flags & 0xFFFFFFFF,
        len(program.cells),
        program.entry,
        program.seed & 0xFFFFFFFF,
        program.default_ticks,
        CELL_SIZE,
        STATE_SIZE,
        0, 0, 0, 0, 0, 0,
    )
    assert len(header) == 64
    state_blob = _STATE.pack(*program.initial_state.words())
    cells_blob = b"".join(_CELL.pack(*cell.words()) for cell in program.cells)
    return header + state_blob + cells_blob


def loads(data: bytes) -> Program:
    if len(data) < HEADER_SIZE:
        raise ValueError("file is shorter than the TOMAGI header")
    values = _HEADER.unpack_from(data, 0)
    magic = values[0]
    if magic != MAGIC:
        raise ValueError("not a TOMAGI 1.0 program")
    version, flags, count, entry, seed, ticks, cell_size, state_size = values[1:9]
    reserved = values[9:15]
    if any(reserved):
        raise ValueError("reserved TOMAGI header words must be zero")
    if version != VERSION_WORD:
        raise ValueError(f"unsupported TOMAGI version word 0x{version:08x}")
    if cell_size != CELL_SIZE or state_size != STATE_SIZE:
        raise ValueError("record size does not match TOMAGI 1.0")
    expected = HEADER_SIZE + count * CELL_SIZE
    if len(data) != expected:
        raise ValueError(f"file length {len(data)} does not match expected {expected}")
    state = State.from_words(_STATE.unpack_from(data, 64))
    cells = []
    offset = HEADER_SIZE
    for _ in range(count):
        cells.append(Cell.from_words(_CELL.unpack_from(data, offset)))
        offset += CELL_SIZE
    return Program(cells=cells, entry=entry, seed=seed, default_ticks=ticks,
                   initial_state=state, flags=flags)


def dump(program: Program, path: str | Path) -> None:
    Path(path).write_bytes(dumps(program))


def load(path: str | Path) -> Program:
    return loads(Path(path).read_bytes())
