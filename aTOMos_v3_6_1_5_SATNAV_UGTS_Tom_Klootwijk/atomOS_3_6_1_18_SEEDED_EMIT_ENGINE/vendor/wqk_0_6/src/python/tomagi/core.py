"""TOMAGI 1.0 deterministic operator machine.

The hot runtime is deliberately integer-only.  Real-valued geometry is compiled into
quantized log-polar coordinates before dispatch.  CPU and GPU backends therefore
share the same two's-complement and modulo semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import IntEnum
from typing import Iterable, Sequence

RHO_BITS = 20
THETA_BITS = 18
TIME_BITS = 14
PHI_BITS = 12
RHO_STATES = 1 << RHO_BITS
THETA_STATES = 1 << THETA_BITS
TIME_STATES = 1 << TIME_BITS
PHI_STATES = 1 << PHI_BITS
RHO_MASK = RHO_STATES - 1
THETA_MASK = THETA_STATES - 1
TIME_MASK = TIME_STATES - 1
PHI_MASK = PHI_STATES - 1

# State status bits.
STATUS_HALT = 1 << 0
STATUS_ZERO = 1 << 1
STATUS_WRAP = 1 << 2
STATUS_EMIT = 1 << 3
STATUS_CONE = 1 << 4
STATUS_SPHERE = 1 << 5
STATUS_REKEY_MISS = 1 << 6
STATUS_PHI_WRAP = 1 << 7

# Program profile flags. These occupy the existing TOMAGI 1.0 header flags
# word and do not alter the binary ABI or opcode transition equations.
PROGRAM_FLAG_SEEDED_PROFILE = 1 << 0
PROGRAM_FLAG_EMIT_BYTES = 1 << 1

# Generic/cell flags.  Meaning is opcode-specific.
FLAG_REKEY = 1 << 31
FLAG_EMIT_HALT = 1 << 0
# TOM-EMIT-BYTES-1.0: bits 8..10 carry a byte count in 1..4;
# bit 11 selects big-endian payload order.
FLAG_EMIT_COUNT_SHIFT = 8
FLAG_EMIT_COUNT_MASK = 0x7 << FLAG_EMIT_COUNT_SHIFT
FLAG_EMIT_BIG_ENDIAN = 1 << 11
FLAG_PHI_FLIP_ORIENTATION = 1 << 4
FLAG_PHI_BRANCH_HALF = 1 << 5
FLAG_KLEIN_SOURCE_HALF_TURN = 1 << 0
FLAG_KLEIN_FLIP_SHEET = 1 << 1
FLAG_HINGE_FLIP_ORIENTATION = 1 << 0
FLAG_HINGE_FLIP_SHEET = 1 << 1


class Opcode(IntEnum):
    NOP = 0
    SET = 1
    JIT1 = 2
    KIN2 = 3
    PHI = 4
    TIME = 5
    SDF0 = 6
    CONE = 7
    SPHERE = 8
    KLEIN = 9
    RADIX = 10
    HINGE = 11
    LSYS = 12
    PROJECT = 13
    EMIT = 14
    HALT = 15


OPCODE_BY_NAME = {op.name: op for op in Opcode}


def u32(x: int) -> int:
    return x & 0xFFFFFFFF


def i32(x: int) -> int:
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x & 0x80000000 else x


def rotl32(x: int, r: int) -> int:
    r &= 31
    x = u32(x)
    return u32((x << r) | (x >> ((32 - r) & 31)))


def mix32(x: int) -> int:
    x = u32(x)
    x ^= x >> 16
    x = u32(x * 0x7FEB352D)
    x ^= x >> 15
    x = u32(x * 0x846CA68B)
    x ^= x >> 16
    return u32(x)


def popcount32(x: int) -> int:
    return u32(x).bit_count()


def norm_mod(x: int, modulus: int) -> int:
    return x % modulus


def cyclic_delta(value: int, center: int, modulus: int) -> int:
    """Shortest signed modular delta in [-modulus/2, modulus/2)."""
    d = (value - center) % modulus
    if d >= modulus // 2:
        d -= modulus
    return d


def pack_key_contiguous(rho: int, theta: int, tick: int, phi: int) -> tuple[int, int]:
    qr = norm_mod(rho, RHO_STATES)
    qt = norm_mod(theta, THETA_STATES)
    qx = norm_mod(tick, TIME_STATES)
    qp = norm_mod(phi, PHI_STATES)
    hi = u32((qr << 12) | (qt >> 6))
    lo = u32(((qt & 0x3F) << 26) | (qx << 12) | qp)
    return hi, lo


def unpack_key_contiguous(hi: int, lo: int) -> tuple[int, int, int, int]:
    hi = u32(hi)
    lo = u32(lo)
    rho = (hi >> 12) & RHO_MASK
    theta = ((hi & 0xFFF) << 6) | ((lo >> 26) & 0x3F)
    tick = (lo >> 12) & TIME_MASK
    phi = lo & PHI_MASK
    return rho, theta, tick, phi


def pack_key_morton(rho: int, theta: int, tick: int, phi: int) -> tuple[int, int]:
    values = [rho & RHO_MASK, theta & THETA_MASK, tick & TIME_MASK, phi & PHI_MASK]
    positions = [RHO_BITS - 1, THETA_BITS - 1, TIME_BITS - 1, PHI_BITS - 1]
    out = 0
    while any(p >= 0 for p in positions):
        for idx in range(4):
            p = positions[idx]
            if p >= 0:
                out = ((out << 1) | ((values[idx] >> p) & 1)) & 0xFFFFFFFFFFFFFFFF
                positions[idx] -= 1
    return (out >> 32) & 0xFFFFFFFF, out & 0xFFFFFFFF


def unpack_key_morton(hi: int, lo: int) -> tuple[int, int, int, int]:
    word = ((u32(hi) << 32) | u32(lo)) & 0xFFFFFFFFFFFFFFFF
    positions = [RHO_BITS - 1, THETA_BITS - 1, TIME_BITS - 1, PHI_BITS - 1]
    values = [0, 0, 0, 0]
    bit_index = 63
    while any(p >= 0 for p in positions):
        for idx in range(4):
            p = positions[idx]
            if p >= 0:
                bit = (word >> bit_index) & 1
                values[idx] |= bit << p
                positions[idx] -= 1
                bit_index -= 1
    return tuple(values)  # type: ignore[return-value]


def key_as_u64(hi: int, lo: int) -> int:
    return (u32(hi) << 32) | u32(lo)


@dataclass(slots=True)
class State:
    rho: int = 0
    theta: int = 0
    tick: int = 0
    phi: int = 0
    vrho: int = 0
    vtheta: int = 0
    vtick: int = 0
    vphi: int = 0
    orientation: int = 0
    sheet: int = 0
    branch: int = 0
    cell: int = 0
    lineage: int = 0
    output: int = 0
    residual: int = 0
    status: int = 0

    def words(self) -> list[int]:
        signed = [self.rho, self.theta, self.tick, self.phi,
                  self.vrho, self.vtheta, self.vtick, self.vphi]
        return [u32(v) for v in signed] + [
            u32(self.orientation), u32(self.sheet), u32(self.branch), u32(self.cell),
            u32(self.lineage), u32(self.output), u32(self.residual), u32(self.status),
        ]

    @classmethod
    def from_words(cls, words: Sequence[int]) -> "State":
        if len(words) != 16:
            raise ValueError("TOMAGI state requires exactly 16 words")
        return cls(
            *[i32(words[i]) for i in range(8)],
            *[u32(words[i]) for i in range(8, 14)],
            i32(words[14]),
            u32(words[15]),
        )

    def normalized_key(self) -> tuple[int, int]:
        return pack_key_contiguous(self.rho, self.theta, self.tick, self.phi)

    def normalized_copy(self) -> "State":
        return replace(
            self,
            rho=norm_mod(self.rho, RHO_STATES),
            theta=norm_mod(self.theta, THETA_STATES),
            tick=norm_mod(self.tick, TIME_STATES),
            phi=norm_mod(self.phi, PHI_STATES),
            orientation=self.orientation & 1,
            branch=self.branch & 1,
        )


@dataclass(slots=True, frozen=True)
class Cell:
    key_hi: int
    key_lo: int
    opcode: int
    flags: int = 0
    arg0: int = 0
    arg1: int = 0
    arg2: int = 0
    arg3: int = 0
    next0: int = 0
    next1: int = 0
    payload: int = 0
    aux: int = 0

    def words(self) -> list[int]:
        return [
            u32(self.key_hi), u32(self.key_lo), u32(self.opcode), u32(self.flags),
            u32(self.arg0), u32(self.arg1), u32(self.arg2), u32(self.arg3),
            u32(self.next0), u32(self.next1), u32(self.payload), u32(self.aux),
        ]

    @classmethod
    def from_words(cls, words: Sequence[int]) -> "Cell":
        if len(words) != 12:
            raise ValueError("TOMAGI cell requires exactly 12 words")
        return cls(
            u32(words[0]), u32(words[1]), u32(words[2]), u32(words[3]),
            i32(words[4]), i32(words[5]), i32(words[6]), i32(words[7]),
            u32(words[8]), u32(words[9]), u32(words[10]), u32(words[11]),
        )

    @property
    def key_u64(self) -> int:
        return key_as_u64(self.key_hi, self.key_lo)


@dataclass(slots=True)
class Program:
    cells: list[Cell]
    entry: int
    seed: int
    default_ticks: int
    initial_state: State
    flags: int = 0

    def __post_init__(self) -> None:
        if not self.cells:
            raise ValueError("TOMAGI program requires at least one cell")
        if isinstance(self.entry, bool) or not isinstance(self.entry, int):
            raise ValueError("entry index must be an integer")
        if not (0 <= self.entry < len(self.cells)):
            raise ValueError("entry index is outside the cell table")
        if (
            isinstance(self.default_ticks, bool)
            or not isinstance(self.default_ticks, int)
            or not 0 <= self.default_ticks <= 0xFFFFFFFF
        ):
            raise ValueError("default_ticks must be in the u32 range")
        keys = [c.key_u64 for c in self.cells]
        if keys != sorted(keys):
            raise ValueError("cell table must be sorted by canonical key")
        if len(set(keys)) != len(keys):
            raise ValueError("canonical cell keys must be unique")
        for c in self.cells:
            if (
                isinstance(c.opcode, bool)
                or not isinstance(c.opcode, int)
                or not 0 <= c.opcode <= int(Opcode.HALT)
            ):
                raise ValueError("cell opcode is outside the TOMAGI 1.0 opcode table")
            if (
                isinstance(c.next0, bool)
                or isinstance(c.next1, bool)
                or not isinstance(c.next0, int)
                or not isinstance(c.next1, int)
                or not 0 <= c.next0 < len(self.cells)
                or not 0 <= c.next1 < len(self.cells)
            ):
                raise ValueError("cell successor is outside the cell table")

    def find_key(self, hi: int, lo: int) -> int | None:
        target = key_as_u64(hi, lo)
        left, right = 0, len(self.cells)
        while left < right:
            mid = (left + right) // 2
            value = self.cells[mid].key_u64
            if value < target:
                left = mid + 1
            else:
                right = mid
        if left < len(self.cells) and self.cells[left].key_u64 == target:
            return left
        return None


def _state_field_names() -> tuple[str, ...]:
    return (
        "rho", "theta", "tick", "phi", "vrho", "vtheta", "vtick", "vphi",
        "orientation", "sheet", "branch", "cell", "lineage", "output", "residual", "status",
    )


STATE_FIELD_NAMES = _state_field_names()


def _set_field(state: State, index: int, value: int, *, add: bool = False) -> None:
    if not 0 <= index < len(STATE_FIELD_NAMES):
        raise ValueError(f"invalid state field index {index}")
    name = STATE_FIELD_NAMES[index]
    old = getattr(state, name)
    new = old + value if add else value
    if index <= 7 or index == 14:
        new = i32(new)
    else:
        new = u32(new)
    setattr(state, name, new)


def _normalize_periodic(state: State) -> None:
    state.theta = norm_mod(state.theta, THETA_STATES)
    state.tick = norm_mod(state.tick, TIME_STATES)
    state.phi = norm_mod(state.phi, PHI_STATES)
    state.orientation &= 1
    state.branch &= 1


def _apply_klein(state: State, flags: int) -> None:
    wraps = state.rho // RHO_STATES
    state.rho = state.rho - wraps * RHO_STATES
    odd = wraps & 1
    if odd:
        if flags & FLAG_KLEIN_SOURCE_HALF_TURN:
            state.theta = state.theta + THETA_STATES // 2
        else:
            state.theta = THETA_STATES // 2 - state.theta
        state.phi = -state.phi
        state.orientation ^= 1
        if flags & FLAG_KLEIN_FLIP_SHEET:
            state.sheet ^= 1
        state.status |= STATUS_WRAP
    else:
        state.status &= ~STATUS_WRAP
    state.branch = odd
    _normalize_periodic(state)


def _cone_residual(state: State, cell: Cell) -> int:
    rho = norm_mod(state.rho, RHO_STATES)
    theta = norm_mod(state.theta, THETA_STATES)
    rlo, rhi = cell.arg0, cell.arg1
    center = norm_mod(cell.arg2, THETA_STATES)
    half = abs(cell.arg3)
    radial = max(rlo - rho, rho - rhi)
    angular = abs(cyclic_delta(theta, center, THETA_STATES)) - half
    return max(radial, angular)


def _sphere_residual(state: State, cell: Cell) -> int:
    rho = norm_mod(state.rho, RHO_STATES)
    phi = norm_mod(state.phi, PHI_STATES)
    radial = abs(rho - cell.arg0) - abs(cell.arg1)
    if cell.arg3 < 0:
        return radial
    angular = abs(cyclic_delta(phi, norm_mod(cell.arg2, PHI_STATES), PHI_STATES)) - abs(cell.arg3)
    return max(radial, angular)


def step(program: Program, state: State) -> State:
    """Execute one canonical TOMAGI transition in-place and return *state*."""
    if state.status & STATUS_HALT:
        return state
    if not (0 <= state.cell < len(program.cells)):
        raise IndexError("state.cell is outside the program cell table")

    cell_index = state.cell
    cell = program.cells[cell_index]
    key_hi, key_lo = state.normalized_key()
    op = Opcode(cell.opcode)

    if op is Opcode.NOP:
        pass
    elif op is Opcode.SET:
        _set_field(state, cell.flags & 0xF, cell.arg0, add=False)
    elif op is Opcode.JIT1:
        h = mix32(program.seed ^ key_hi ^ rotl32(key_lo, 13) ^ u32(state.tick) ^ cell.aux)
        bit = popcount32(h) & 1
        state.branch = bit
        sigma = 1 if bit else -1
        _set_field(state, cell.flags & 0xF, sigma * cell.arg0, add=True)
    elif op is Opcode.KIN2:
        state.vrho = i32(state.vrho + cell.arg0)
        state.vtheta = i32(state.vtheta + cell.arg1)
        state.vtick = i32(state.vtick + cell.arg2)
        state.vphi = i32(state.vphi + cell.arg3)
        state.rho = i32(state.rho + state.vrho)
        state.theta = i32(state.theta + state.vtheta)
        state.tick = i32(state.tick + state.vtick)
        state.phi = i32(state.phi + state.vphi)
    elif op is Opcode.PHI:
        raw = state.phi + cell.arg0
        wraps = raw // PHI_STATES
        state.phi = raw - wraps * PHI_STATES
        if (wraps & 1) and (cell.flags & FLAG_PHI_FLIP_ORIENTATION):
            state.orientation ^= 1
        state.status = (state.status | STATUS_PHI_WRAP) if wraps else (state.status & ~STATUS_PHI_WRAP)
        state.branch = ((state.phi >> (PHI_BITS - 1)) & 1) if (cell.flags & FLAG_PHI_BRANCH_HALF) else (wraps & 1)
    elif op is Opcode.TIME:
        raw = state.tick + cell.arg0
        wraps = raw // TIME_STATES
        state.tick = raw - wraps * TIME_STATES
        state.branch = wraps & 1
        if wraps:
            state.lineage = mix32(state.lineage ^ u32(wraps) ^ cell.aux)
    elif op is Opcode.SDF0:
        state.residual = 0
        state.status |= STATUS_ZERO
        state.branch = 1
    elif op is Opcode.CONE:
        state.residual = i32(_cone_residual(state, cell))
        inside = state.residual <= 0
        state.branch = int(inside)
        state.status = (state.status | STATUS_CONE) if inside else (state.status & ~STATUS_CONE)
    elif op is Opcode.SPHERE:
        state.residual = i32(_sphere_residual(state, cell))
        inside = state.residual <= 0
        state.branch = int(inside)
        state.status = (state.status | STATUS_SPHERE) if inside else (state.status & ~STATUS_SPHERE)
    elif op is Opcode.KLEIN:
        _apply_klein(state, cell.flags)
    elif op is Opcode.RADIX:
        bit_index = cell.arg0
        if not 0 <= bit_index < 64:
            raise ValueError("RADIX bit index must be in 0..63")
        if bit_index < 32:
            state.branch = (key_lo >> bit_index) & 1
        else:
            state.branch = (key_hi >> (bit_index - 32)) & 1
    elif op is Opcode.HINGE:
        if state.branch & 1:
            state.rho = i32(state.rho + cell.arg0)
            state.theta = i32(state.theta + cell.arg1)
            state.tick = i32(state.tick + cell.arg2)
            state.phi = i32(state.phi + cell.arg3)
            if cell.flags & FLAG_HINGE_FLIP_ORIENTATION:
                state.orientation ^= 1
            if cell.flags & FLAG_HINGE_FLIP_SHEET:
                state.sheet ^= 1
            _normalize_periodic(state)
    elif op is Opcode.LSYS:
        shift = max(0, min(30, cell.arg1))
        divisor = 1 << shift
        chirality = -1 if (state.orientation & 1) else 1
        turn_sign = 1 if (state.branch & 1) else -1
        state.phi = norm_mod(state.phi + chirality * turn_sign * cell.arg0, PHI_STATES)
        state.vrho = int(state.vrho / divisor)
        state.vtheta = int(state.vtheta / divisor)
        state.vtick = int(state.vtick / divisor)
        state.vphi = int(state.vphi / divisor)
    elif op is Opcode.PROJECT:
        state.output = u32(cell.payload)
    elif op is Opcode.EMIT:
        state.output = u32(cell.payload)
        state.status |= STATUS_EMIT
        if cell.flags & FLAG_EMIT_HALT:
            state.status |= STATUS_HALT
    elif op is Opcode.HALT:
        state.status |= STATUS_HALT
    else:  # pragma: no cover - IntEnum protects this path.
        raise ValueError(f"unsupported opcode {cell.opcode}")

    _normalize_periodic(state)

    # Every transition contributes to deterministic lineage.  It is a compact replay
    # checksum, not an ownership or cryptographic identity claim.
    state.lineage = mix32(
        state.lineage ^ cell.payload ^ cell.aux ^ key_hi ^ rotl32(key_lo, 7)
        ^ u32(state.branch) ^ u32(cell_index)
    )

    if not (state.status & STATUS_HALT):
        if cell.flags & FLAG_REKEY:
            new_hi, new_lo = state.normalized_key()
            found = program.find_key(new_hi, new_lo)
            if found is None:
                state.status |= STATUS_REKEY_MISS
                state.cell = cell.next1 if (state.branch & 1) else cell.next0
            else:
                state.status &= ~STATUS_REKEY_MISS
                state.cell = found
        else:
            state.cell = cell.next1 if (state.branch & 1) else cell.next0
    return state


def run(program: Program, ticks: int | None = None, state: State | None = None,
        *, trace: bool = False) -> tuple[State, list[dict[str, int]]]:
    if ticks is None:
        ticks = program.default_ticks
    if ticks < 0:
        raise ValueError("ticks must be non-negative")
    current = replace(state if state is not None else program.initial_state)
    current.cell = program.entry if state is None else current.cell
    records: list[dict[str, int]] = []
    for n in range(ticks):
        if current.status & STATUS_HALT:
            break
        before = current.cell
        cell = program.cells[before]
        step(program, current)
        if trace:
            hi, lo = current.normalized_key()
            records.append({
                "step": n,
                "cell_before": before,
                "opcode": cell.opcode,
                "branch": current.branch,
                "cell_after": current.cell,
                "key_hi": hi,
                "key_lo": lo,
                "rho": current.rho,
                "theta": current.theta,
                "tick": current.tick,
                "phi": current.phi,
                "orientation": current.orientation,
                "sheet": current.sheet,
                "residual": current.residual,
                "output": current.output,
                "lineage": current.lineage,
                "status": current.status,
            })
    return current, records


def zero_field(domain_keys: Iterable[tuple[int, int]], hi: int, lo: int) -> int | None:
    """Literal SDF0 semantics: zero for a definable key, undefined otherwise."""
    target = key_as_u64(hi, lo)
    return 0 if any(key_as_u64(a, b) == target for a, b in domain_keys) else None
