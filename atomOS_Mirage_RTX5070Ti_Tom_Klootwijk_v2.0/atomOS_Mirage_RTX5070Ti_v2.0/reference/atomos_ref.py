"""Independent Python mathematics and bit-tape reference for atomOS 2.0.

Standard library only. Finite executable tapes stop before an out-of-range
transition; unbounded-memory semantics are a separate mathematical model.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Callable

MASK32 = (1 << 32) - 1
TAU = 2 * math.pi

def word_step(psi: int, jitter: int, mask: int, merge_or: bool = False) -> int:
    if any(type(x) is not int or not 0 <= x <= MASK32 for x in (psi, jitter, mask)):
        raise ValueError("expected 32-bit unsigned words")
    if psi == 0:
        return 0
    left, right = (psi << 1) & MASK32, psi >> 1
    blend = ((left | right) if merge_or else (left ^ right)) ^ jitter
    return 0 if blend & mask else blend

def children(parent: int) -> tuple[int, int]:
    if type(parent) is not int or not 1 <= parent <= (1 << 63) - 1:
        raise ValueError("64-bit lineage exhausted or invalid")
    return parent << 1, (parent << 1) | 1

def jitter_bit(root: bytes, tick: int, child: int, threshold: int = 32) -> int:
    if len(root) != 32 or not 0 <= threshold <= 256:
        raise ValueError("invalid root digest or threshold")
    if not 0 <= tick < 1 << 64 or not 0 <= child < 1 << 64:
        raise ValueError("counter outside uint64")
    h = hashlib.sha256(b"atomOS:jitter:v2\0" + root + struct.pack("<QQ", tick, child))
    return int(h.digest()[0] < threshold)

def pack_bits(bits: list[int]) -> list[int]:
    if any(x not in (0, 1) for x in bits):
        raise ValueError("nonbinary predicate")
    words = [0] * ((len(bits) + 31) // 32)
    for i, bit in enumerate(bits):
        words[i // 32] |= bit << (i % 32)
    return words

def get_bit(words: list[int], index: int, size: int) -> int:
    if not 0 <= index < size or len(words) < (size + 31) // 32:
        raise IndexError("predicate index out of bounds")
    return (words[index // 32] >> (index % 32)) & 1

def klein(rho: float, phi: float, low: float, high: float, orientation: int = 0):
    if not all(map(math.isfinite, (rho, phi, low, high))) or high <= low:
        raise ValueError("invalid quotient chart")
    q = math.floor((rho - low) / (high - low))
    return rho - q * (high - low), ((-phi if q % 2 else phi) % TAU), orientation ^ (q & 1)

def rk4(rhs: Callable[[float, float], float], t: float, y: float, h: float) -> float:
    k1 = rhs(t, y)
    k2 = rhs(t + h / 2, y + h * k1 / 2)
    k3 = rhs(t + h / 2, y + h * k2 / 2)
    k4 = rhs(t + h, y + h * k3)
    return y + h * (k1 + 2 * k2 + 2 * k3 + k4) / 6

def jk(q: int, j: int, k: int) -> int:
    if any(x not in (0, 1) for x in (q, j, k)):
        raise ValueError("JK values must be binary")
    return (j & (1 ^ q)) | ((1 ^ k) & q)

def instruction(next_state: int, write: int, move: int) -> int:
    if not 0 <= next_state < 1 << 24 or write not in (0, 1) or move not in (-1, 0, 1):
        raise ValueError("invalid transition")
    return (next_state << 8) | ((move + 1) << 1) | write | 8

@dataclass
class Machine:
    states: int
    halt: int
    program: list[int]
    tape: dict[int, int]
    tape_bits: int = 32
    state: int = 0
    head: int = 0
    status: int = 0
    steps: int = 0

    def step(self) -> None:
        if self.status:
            return
        if self.state == self.halt:
            self.status = 1
            return
        if not 0 <= self.state < self.states or self.steps == MASK32:
            self.status = 3
            return
        if not 0 <= self.head < self.tape_bits:
            self.status = 2
            return
        symbol = self.tape.get(self.head, 0)
        code = self.program[2 * self.state + symbol]
        next_state, move_code = code >> 8, (code >> 1) & 3
        if not (code & 8) or (code & 0xF0) or move_code == 3 or next_state >= self.states:
            self.status = 3
            return
        h = self.head + move_code - 1
        if not 0 <= h < self.tape_bits:
            self.status = 2
            return
        if code & 1:
            self.tape[self.head] = 1
        else:
            self.tape.pop(self.head, None)
        self.state, self.head = next_state, h
        self.steps += 1
        if self.state == self.halt:
            self.status = 1

    def run(self, budget: int) -> None:
        if type(budget) is not int or budget < 0:
            raise ValueError("nonnegative step budget required")
        for _ in range(budget):
            if self.status:
                break
            self.step()
