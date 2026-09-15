"""WANTWOMBAN | Operator I, sub-version 1.1.

Numerical/serialization reference, not a device driver or a calibrated multiphysics
simulator. Place this file beside the unchanged wantwomban_reference.py extracted
from the parent PDF. Run: python operator_i_reference.py
Only Python's standard library is needed. Results are written beside this file.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import product
from math import exp, expm1, isfinite, log
from pathlib import Path
from random import Random
import json
import struct
import zlib
import wantwomban_reference as parent

BODY = struct.Struct("<2sBBIQQiiIIiHBBIII")
assert BODY.size == 60
MAGIC = b"WI"
VERSION = (1, 1)
# X, Y, time, valid, accepted, saturated, fault, dark, T-valid, strain-valid,
# two-band-valid; bits 11 through 15 are reserved.
KNOWN_FLAGS = 0x07FF

def finite(*values: float) -> None:
    if not all(isfinite(v) for v in values):
        raise ValueError("non-finite numerical input")

def quarter_ratio(x: float) -> float:
    """v = VL/Vex - VR/Vex, with R4 = R*(1+x); other arms equal R."""
    finite(x)
    if x <= -1:
        raise ValueError("R4 must remain positive")
    # The reciprocal form avoids overflow at very large positive x.
    return -0.5/(1 + 2/x) if x > 1 else -x/(4 + 2*x)

def quarter_inverse(v: float) -> float:
    finite(v)
    if not -0.5 < v < 0.5:
        raise ValueError("ratio outside positive-resistance quarter-bridge range")
    return -4*v / (1 + 2*v)

def verified_event(x: int, y: int, timing: int, valid: int,
                   saturated: int = 0, fault: int = 0) -> int:
    args = (x, y, timing, valid, saturated, fault)
    if any(type(a) is not int or a not in (0, 1) for a in args):
        raise ValueError("event inputs must be integer bits")
    return x & y & timing & valid & (1-saturated) & (1-fault)

def event_from_flags(flags: int) -> int:
    return verified_event((flags >> 0) & 1, (flags >> 1) & 1,
                          (flags >> 2) & 1, (flags >> 3) & 1,
                          (flags >> 5) & 1, (flags >> 6) & 1)

def validate_flags(flags: int) -> None:
    if type(flags) is not int or not 0 <= flags <= 65535:
        raise ValueError("flags are not uint16")
    if flags & ~KNOWN_FLAGS:
        raise ValueError("reserved flag bits must be zero")
    if ((flags >> 4) & 1) != event_from_flags(flags):
        raise ValueError("accepted-event flag is inconsistent")

@dataclass(frozen=True)
class Record:
    sequence: int
    tick_ns: int
    word: int
    temperature_mK: int
    strain_nano: int
    band1_counts: int
    band2_counts: int
    secondary_counts: int
    flags: int
    mode: int
    calibration_id: int
    window_ns: int
    site_id: int

    def validate(self) -> None:
        ranges = {
            "sequence": (0, 2**32-1), "tick_ns": (0, 2**64-1),
            "word": (0, 2**64-1), "temperature_mK": (0, 2**31-1),
            "strain_nano": (-2**31, 2**31-1),
            "band1_counts": (0, 2**32-1), "band2_counts": (0, 2**32-1),
            "secondary_counts": (-2**31, 2**31-1),
            "mode": (0, 3), "calibration_id": (0, 2**32-1),
            "window_ns": (1, 2**32-1), "site_id": (0, 2**32-1)}
        for name, (lo, hi) in ranges.items():
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f"{name} outside declared range")
        validate_flags(self.flags)
        if self.flags & (1 << 8) and self.temperature_mK == 0:
            raise ValueError("zero temperature code cannot be marked valid")
        if self.flags & (1 << 3) and self.calibration_id == 0:
            raise ValueError("valid record needs nonzero calibration identifier")

    def encode(self) -> bytes:
        self.validate()
        body = BODY.pack(MAGIC, *VERSION, self.sequence, self.tick_ns, self.word,
                         self.temperature_mK, self.strain_nano, self.band1_counts,
                         self.band2_counts, self.secondary_counts, self.flags,
                         self.mode, 0, self.calibration_id, self.window_ns, self.site_id)
        return body + struct.pack("<I", zlib.crc32(body))

    @classmethod
    def decode(cls, packet: bytes) -> "Record":
        if len(packet) != 64:
            raise ValueError("record must be exactly 64 bytes")
        body, checksum = packet[:60], struct.unpack("<I", packet[60:])[0]
        if zlib.crc32(body) != checksum:
            raise ValueError("CRC mismatch")
        vals = BODY.unpack(body)
        if vals[:3] != (MAGIC, *VERSION) or vals[13] != 0:
            raise ValueError("wrong magic, version, or reserved byte")
        # Fields 3..12, skip reserved index 13, then fields 14..16.
        record = cls(*vals[3:13], *vals[14:17])
        record.validate()
        return record

def chemical_step(zeta: float, activation: float, recovery: float, dt: float) -> float:
    """Exact proposed two-state kinetics with constant nonnegative rates (1/s)."""
    finite(zeta, activation, recovery, dt)
    if not 0 <= zeta <= 1 or min(activation, recovery, dt) < 0:
        raise ValueError("invalid state, rate, or time")
    if dt == 0:
        return zeta
    total = activation + recovery
    finite(total)
    if total == 0:
        return zeta
    equilibrium = activation / total
    return equilibrium + (zeta-equilibrium)*exp(-total*dt)

def deformation_prune(center_projection: float, slit_center: float, half_width: float,
                      radius: float, deformation_bound: float,
                      encoding_bound: float = 0.0) -> bool:
    finite(center_projection, slit_center, half_width, radius,
           deformation_bound, encoding_bound)
    if min(half_width, radius, deformation_bound, encoding_bound) < 0:
        raise ValueError("enclosure terms must be nonnegative lengths")
    return abs(center_projection-slit_center) > (
        half_width + radius + deformation_bound + encoding_bound)

def zero_failure_upper(n: int, confidence: float = 0.95) -> float:
    if type(n) is not int or n <= 0 or not 0 < confidence < 1:
        raise ValueError("positive trial count and probability required")
    return -expm1(log(1-confidence)/n)

def reference_kernel_tick(word: int, scheduled_branch: int, optical_dark: int,
                          prior_event: int, feedback_enabled: bool = False):
    """Only the optional branch-input policy is new; parent W64 semantics persist."""
    if any(type(x) is not int or x not in (0, 1)
           for x in (prior_event, scheduled_branch, optical_dark)):
        raise ValueError("branch, event, and darkness must be integer bits")
    if type(feedback_enabled) is not bool:
        raise ValueError("feedback_enabled must be Boolean")
    branch = scheduled_branch ^ (prior_event if feedback_enabled else 0)
    return parent.step(word, branch, optical_dark)

def calculations() -> dict:
    h, c, elementary_charge = 6.62607015e-34, 299792458.0, 1.602176634e-19
    wavelength, optical_power, pulse = 550e-9, 1e-3, 0.005
    energy = h*c/wavelength
    absorbed_power, C, G = 0.8*optical_power, 1e-6, 1e-4
    rise = absorbed_power/G * (-expm1(-G*pulse/C))
    absorbed = absorbed_power*pulse
    return {
      "classification": "specified calculation inputs; not experimental observations",
      "rim_section_I_ratio_h_over_t_10": 100.0,
      "foil_x_GF2_e100micro": 0.0002,
      "foil_Vout_Vex1_V": quarter_ratio(2*100e-6),
      "silicon_Vout_Vex1_V_GF100": quarter_ratio(100*100e-6),
      "bridge_gauge_power_Vex1_R350_W": 1.0/(4*350),
      "bridge_gauge_power_Vex3p3_R350_W": 3.3**2/(4*350),
      "slit_first_zero_rad_w100um": wavelength/100e-6,
      "slit_first_zero_rad_h2mm": wavelength/0.002,
      "photon_550nm_J": energy,
      "photon_550nm_eV": energy/elementary_charge,
      "one_photon_deltaT_C1micro_JperK_K": energy/C,
      "one_photon_deltaT_parent_C0p02_K": energy/0.02,
      "pulse_absorbed_J": absorbed,
      "pulse_absorbed_photons_mean": absorbed/energy,
      "pulse_time_constant_s": C/G,
      "pulse_peak_deltaT_K": rise,
      "pulse_stored_heat_J": C*rise,
      "pulse_heat_lost_J": absorbed-C*rise,
      "pFA_independent_1e_minus3_times_1e_minus3": 1e-6,
      "pD_independent_0p95_times_0p90": 0.95*0.90,
      "zero_false_events_N10000_upper95": zero_failure_upper(10000),
      "N_for_zero_failures_to_bound_pFA_1e_minus6_at95": 2995731,
      "accidental_rate_rX10_rY20_window5ms_per_s": 10*20*0.005,
    }

def self_test() -> dict:
    rng = Random(19900710)
    result = {"parent": parent.self_test()}
    worst = 0.0
    for i in range(10001):
        x = -0.5 + i/10000
        worst = max(worst, abs(quarter_inverse(quarter_ratio(x))-x))
    assert worst < 1e-14
    result["bridge_inverse_cases"] = 10001
    result["bridge_inverse_max_abs_error"] = worst
    accepted = 0
    for inputs in product((0, 1), repeat=6):
        got = verified_event(*inputs)
        assert got == int(all(inputs[:4]) and not any(inputs[4:]))
        accepted += got
    assert accepted == 1
    result["gate_truth_table_cases"] = 64
    result["gate_accepting_rows"] = accepted
    packets = []
    for i in range(1000):
        low = rng.randrange(2048) & ~(1 << 4)
        low |= event_from_flags(low) << 4
        record = Record(i, i*1000000, rng.getrandbits(64), 293150,
                        rng.randrange(-1000000, 1000000), rng.randrange(65536),
                        rng.randrange(65536), rng.randrange(-65536, 65536), low,
                        i % 4, 1, 5000000, i % 32)
        packet = record.encode()
        assert Record.decode(packet) == record
        assert len(packet) == 64
        packets.append(packet)
    result["packet_roundtrips"] = 1000
    packet = packets[0]
    for bit in range(512):
        mutated = bytearray(packet)
        mutated[bit//8] ^= 1 << (bit % 8)
        try:
            Record.decode(bytes(mutated))
        except ValueError:
            pass
        else:
            raise AssertionError("corrupted packet was accepted")
    result["single_bit_corruptions_rejected"] = 512
    for _ in range(1000):
        z = chemical_step(rng.random(), 10*rng.random(), 10*rng.random(), rng.random())
        assert 0 <= z <= 1
    result["bounded_kinetic_updates"] = 1000
    pruned = 0
    points = 0
    for _ in range(2000):
        center, slit = rng.uniform(-10,10), rng.uniform(-3,3)
        radius, half, deformation, error = (rng.random() for i in range(4))
        if deformation_prune(center, slit, half, radius, deformation, error):
            pruned += 1
            for j in range(25):
                point = center + rng.uniform(-radius,radius)
                point += rng.uniform(-deformation,deformation)
                point += rng.uniform(-error,error)
                assert abs(point-slit) > half
                points += 1
    result["random_enclosure_cases"] = 2000
    result["pruned_enclosures_checked"] = pruned
    result["enclosed_points_checked"] = points
    for _ in range(1000):
        w, b, dark, e = rng.getrandbits(64), rng.randrange(2), rng.randrange(2), rng.randrange(2)
        assert reference_kernel_tick(w,b,dark,e,False) == parent.step(w,b,dark)
        assert reference_kernel_tick(w,b,dark,e,True) == parent.step(w,b^e,dark)
    result["parent_compatibility_cases"] = 1000
    result["event_branch_policy_cases"] = 1000
    assert zlib.crc32(b"123456789") == 0xCBF43926
    assert 0 < zero_failure_upper(10000) < 0.0003
    result["crc_check_vector"] = "CBF43926"
    result["status"] = "PASS - arithmetic, logical and transport checks only"
    return result

if __name__ == "__main__":
    output = {"version": "1.1", "tests": self_test(), "calculations": calculations()}
    path = Path(__file__).with_name("operator_i_results.json")
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
