"""WANTWOMBAN v1.0: auditable reference kernel, standard library only.

The 64-bit word is geometry/control state. Temperatures, material memory,
LUTs, the tree stack, and measured physical parameters are separate.
Run this file to execute the deterministic conformance tests.
"""
from math import exp, isfinite
from random import Random

FIELDS = {
    "chi": (63, 1), "rho": (52, 11), "theta": (41, 11),
    "z": (30, 11), "phi": (20, 10), "depth": (15, 5),
    "phase": (10, 5), "lut": (3, 7), "kappa": (2, 1),
    "cycle": (0, 2),
}
WORD_MASK = (1 << 64) - 1
LUT = (128,) * 128  # Example log-radius boundary, not measured paint data.

def get(w: int, name: str) -> int:
    if not isinstance(w, int) or not 0 <= w <= WORD_MASK:
        raise ValueError("word must be an unsigned 64-bit integer")
    shift, width = FIELDS[name]
    return (w >> shift) & ((1 << width) - 1)

def put(w: int, name: str, value: int) -> int:
    get(w, name)  # Validate the incoming word.
    shift, width = FIELDS[name]
    mask = (1 << width) - 1
    if not isinstance(value, int) or not 0 <= value <= mask:
        raise ValueError("field value is outside its unsigned range")
    clear = WORD_MASK ^ (mask << shift)
    return (w & clear) | (value << shift)

def signed(raw: int, width: int) -> int:
    if not 0 <= raw < (1 << width):
        raise ValueError("invalid signed-field encoding")
    return raw - (1 << width) if raw & (1 << (width - 1)) else raw

def clip(x: int, lo: int, hi: int) -> int:
    return min(hi, max(lo, x))

def nearest(n: int, d: int) -> int:
    """Nearest rounding with power-of-two divisor; ties away from zero."""
    if d <= 0 or (d & (d - 1)):
        raise ValueError("denominator must be a positive power of two")
    q = (abs(n) + (d >> 1)) >> (d.bit_length() - 1)
    return -q if n < 0 else q

def constmul(x: int, coefficient: int) -> int:
    """Exact multiplication by a nonnegative integer using shift/add."""
    if coefficient < 0:
        raise ValueError("coefficient must be nonnegative")
    out = 0
    while coefficient:
        if coefficient & 1:
            out += x
        x <<= 1
        coefficient >>= 1
    return out

def pinion(v: tuple[int, int, int, int]) -> tuple[int, ...]:
    x, y, z, f = v
    a, b = x + y + z + f, x - y + z - f
    c, d = x + y - z - f, x - y - z + f
    return (nearest(constmul(a, 106039), 131072),
            nearest(constmul(b, 40503), 131072),
            nearest(c, 2), nearest(-d, 2))

def otan2(rho_raw: int, occupancy: int) -> int:
    if occupancy not in (0, 1):
        raise ValueError("occupancy must be one bit")
    a = rho_raw & 2047
    b = occupancy << 10
    a = a ^ b
    return a & 2047

def otan2_literal(rho_raw: int, occupancy: int) -> int:
    if occupancy not in (0, 1):
        raise ValueError("occupancy must be one bit")
    return (((rho_raw & 2047) ^ occupancy) << 10) & 2047

def parity3(w: int) -> int:
    return (w & 1) ^ ((w >> 1) & 1) ^ ((w >> 2) & 1)

def occupancy(w: int, lut: tuple[int, ...] = LUT) -> tuple[int, int]:
    if len(lut) != 128 or any(not isinstance(x, int) for x in lut):
        raise ValueError("LUT must contain 128 integer boundaries")
    c = get(w, "cycle")
    c13 = (c << 3) + (c << 2) + c
    j = ((get(w, "theta") >> 4) + get(w, "phase") + c13) & 127
    jitter = ((get(w, "phi") & 1) ^ get(w, "kappa"))
    threshold = lut[j] + (jitter << 1) - 1
    return int(signed(get(w, "rho"), 11) <= threshold), j

def seam(w: int) -> int:
    """Shifted Klein reflection plus an independent log-radius inversion."""
    r = signed(get(w, "rho"), 11)
    if r == -1024:
        raise ValueError("seam profile uses symmetric radius range")
    w = put(w, "rho", (-r) & 2047)
    w = put(w, "theta", (1024 - get(w, "theta")) & 2047)
    return put(w, "kappa", get(w, "kappa") ^ 1)

def step(w: int, branch: int, optical_dark: int,
         lut: tuple[int, ...] = LUT) -> tuple[int, int]:
    """One node event. Returns next word and binary heater command.

    optical_dark is a previously acquired measurement, never an algebraic
    unknown. The returned command applies over the following time slot.
    """
    if branch not in (0, 1) or optical_dark not in (0, 1):
        raise ValueError("branch and optical measurement must be bits")
    g, j = occupancy(w, lut)
    command = 1 - (g ^ get(w, "chi") ^ get(w, "kappa"))
    p = parity3(w) ^ branch
    f = get(w, "phi")
    f = ((f << 1) & 1023) if p == 0 else (f >> 1)
    r, a, z, f = pinion((signed(get(w, "rho"), 11),
                        signed(get(w, "theta"), 11),
                        signed(get(w, "z"), 11), signed(f, 10)))
    r = clip(r + ((branch << 1) - 1), -1023, 1023)
    golden = 1266 if p == 0 else -1266
    a = (a + otan2(r & 2047, g) + golden) & 2047
    out = put(w, "rho", r & 2047)
    out = put(out, "theta", a)
    out = put(out, "z", clip(z, -1024, 1023) & 2047)
    out = put(out, "phi", f & 1023)
    out = put(out, "lut", j)
    out = put(out, "phase", (get(w, "phase") + 1 + optical_dark) & 31)
    if get(w, "depth") == 31:
        out = seam(out)
        out = put(out, "depth", 0)
    else:
        out = put(out, "depth", get(w, "depth") + 1)
    return out, command

def thermal_step(T: float, command: int, dt: float, C: float = 0.02,
                 G: float = 0.005, Ta: float = 293.15,
                 Pmax: float = 0.10) -> float:
    """Exact constant-input lumped model; all temperatures are kelvin."""
    if command not in (0, 1) or not all(map(isfinite,
                                           (T, dt, C, G, Ta, Pmax))):
        raise ValueError("invalid thermal arguments")
    if min(T, C, G, Ta) <= 0 or dt < 0 or Pmax < 0:
        raise ValueError("nonphysical lumped-model parameters")
    target = Ta + Pmax * command / G
    return target + (T - target) * exp(-G * dt / C)

def dark_bit(T: float, previous: int, low: float = 301.15,
             high: float = 304.15) -> int:
    if previous not in (0, 1) or not low < high or not isfinite(T):
        raise ValueError("invalid hysteresis arguments")
    return 0 if T >= high else (1 if T <= low else previous)

def self_test() -> dict[str, int]:
    rng = Random(19900710)
    masks = [((1 << width) - 1) << shift for shift, width in FIELDS.values()]
    assert sum(masks) == WORD_MASK
    assert all(not (a & b) for i, a in enumerate(masks) for b in masks[i+1:])
    for _ in range(10000):
        w = rng.getrandbits(64)
        out = 0
        for name in FIELDS:
            out = put(out, name, get(w, name))
        assert out == w
        name = rng.choice(tuple(FIELDS))
        s, n = FIELDS[name]
        out = put(w, name, rng.randrange(1 << n))
        mask = ((1 << n) - 1) << s
        assert ((out ^ w) & (WORD_MASK ^ mask)) == 0
    for o in (0, 1):
        assert len({otan2(r, o) for r in range(2048)}) == 2048
        assert {otan2_literal(r, o) for r in range(2048)} == {0, 1024}
    for a in range(2048):
        w = put(put(put(0, "theta", a), "rho", 77), "kappa", a & 1)
        assert seam(seam(w)) == w
    B = ((1,1,1,1), (1,-1,1,-1), (1,1,-1,-1), (1,-1,-1,1))
    for i in range(4):
        for j in range(4):
            assert sum(B[i][k]*B[k][j] for k in range(4)) == (4 if i==j else 0)
    for _ in range(1000):
        w = rng.getrandbits(64)
        for b in (0, 1):
            out, u = step(w, b, rng.randrange(2))
            assert 0 <= out <= WORD_MASK and u in (0, 1)
            assert get(out, "chi") == get(w, "chi")
            assert get(out, "cycle") == get(w, "cycle")
            assert get(out, "depth") == (get(w, "depth") + 1) % 32
    assert abs(thermal_step(313.15, 1, 1) - 313.15) < 1e-10
    assert abs(thermal_step(293.15, 0, 1) - 293.15) < 1e-10
    assert dark_bit(302, 0) == 0 and dark_bit(302, 1) == 1
    return {"word_roundtrips": 10000, "field_isolations": 10000,
            "seam_involutions": 2048, "transition_cases": 2000,
            "OTAN2_inputs_per_profile": 4096, "matrix_entries": 16}

if __name__ == "__main__":
    print("PASS", self_test())
