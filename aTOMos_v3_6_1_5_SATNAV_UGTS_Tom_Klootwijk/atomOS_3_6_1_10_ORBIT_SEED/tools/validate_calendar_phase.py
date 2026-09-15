#!/usr/bin/env python3
"""Exhaustive Gregorian-cycle/address audit, separate from orbital prediction."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from orbit_query import chart_record, timestamp_gpst
from ugts import (contiguous, decode_contiguous, decode_morton, morton,
                  phase_winding, quantize)

PERIOD = 1 << 14
DAY = 86400


def leap_year(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def dates(start_year, end_year):
    """Manual month enumeration; end year is exclusive. No datetime oracle."""
    for year in range(start_year, end_year):
        lengths = (31, 29 if leap_year(year) else 28, 31, 30, 31, 30,
                   31, 31, 30, 31, 30, 31)
        for month, length in enumerate(lengths, 1):
            for day in range(1, length + 1):
                yield year, month, day


def jdn(year, month, day):
    """Integer proleptic Gregorian Julian day number, Gregorian noon convention."""
    a = (14 - month) // 12
    y, m = year + 4800 - a, month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def ordinal(year, month, day):
    """Independent January-based days-before-year/month sum, 0001-01-01 = 1."""
    y = year - 1
    before = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    return 365 * y + y // 4 - y // 100 + y // 400 + before[month - 1] + day + int(month > 2 and leap_year(year))


GPS_JDN = jdn(1980, 1, 6)


def midnight_tick(date):
    return (jdn(*date) - GPS_JDN) * DAY


def label(date, clock="00:00:00.000"):
    return f"{date[0]:04d}-{date[1]:02d}-{date[2]:02d}T{clock} GPST"


class Checks:
    def __init__(self):
        self.count = 0
        self.failure_count = 0
        self.failures = []

    def equal(self, actual, expected, context):
        self.count += 1
        if actual != expected:
            self.failure_count += 1
            if len(self.failures) < 20:
                self.failures.append({"context": context, "actual": actual, "expected": expected})


def audit_calendar(checks, start_year=2000, end_year=2400):
    start = jdn(start_year, 1, 1)
    previous, previous_tick = None, None
    n, leaps, months, years = 0, 0, 0, 0
    # The last boundary is included, although its date is outside the full cycle.
    for date in (*dates(start_year, end_year), (end_year, 1, 1)):
        day_number = jdn(*date)
        tick = midnight_tick(date)
        context = f"{date[0]:04d}-{date[1]:02d}-{date[2]:02d}"
        checks.equal(day_number, start + n, context + " sequential JDN")
        checks.equal(day_number - ordinal(*date), 1721425, context + " independent ordinal")
        checks.equal(timestamp_gpst(tick), label(date), context + " midnight")
        checks.equal(timestamp_gpst(tick + .125), label(date, "00:00:00.125"), context + " exact fractional second")
        checks.equal(jdn(date[0] + 400, date[1], date[2]) - day_number, 146097, context + " 400-year repeat")
        checks.equal((jdn(date[0] + 400, date[1], date[2]) - day_number) % 7, 0, context + " weekday repeat")
        if previous is not None:
            checks.equal(tick - previous_tick, DAY, context + " no calendar reset")
            checks.equal(timestamp_gpst(tick - 1), label(previous, "23:59:59.000"), context + " previous second")
        if date != (end_year, 1, 1):
            leaps += int(date[1:] == (2, 29))
            months += int(date[2] == 1)
            years += int(date[1:] == (1, 1))
        previous, previous_tick = date, tick
        n += 1
    return {"years": [start_year, end_year - 1], "dates_in_cycle": n - 1,
            "included_next_boundary": label((end_year, 1, 1)),
            "midnights_checked": n, "formatter_checks": 3 * n - 1,
            "month_starts_in_cycle": months, "year_starts_in_cycle": years,
            "leap_days_in_cycle": leaps, "cycle_days": jdn(end_year, 1, 1) - start,
            "cycle_weekday_remainder": (jdn(end_year, 1, 1) - start) % 7,
            "first_tick_gpst_s": midnight_tick((start_year, 1, 1)),
            "next_boundary_tick_gpst_s": midnight_tick((end_year, 1, 1)),
            "oracle": "Manual Gregorian month enumeration, March-based integer JDN, and independent January-based ordinal; no datetime used as expected-value oracle"}


def audit_extra_boundaries(checks):
    # Dates beyond the enumerated interval are individual tests, not another cycle.
    transitions = (((1900, 2, 28), (1900, 3, 1)),
                   ((1999, 12, 31), (2000, 1, 1)),
                   ((2000, 2, 28), (2000, 2, 29)),
                   ((2000, 2, 29), (2000, 3, 1)),
                   ((2100, 2, 28), (2100, 3, 1)),
                   ((2200, 2, 28), (2200, 3, 1)),
                   ((2300, 2, 28), (2300, 3, 1)),
                   ((2399, 12, 31), (2400, 1, 1)),
                   ((2400, 2, 28), (2400, 2, 29)),
                   ((2400, 2, 29), (2400, 3, 1)))
    for before, after in transitions:
        tick = midnight_tick(after)
        checks.equal(tick - midnight_tick(before), DAY, "explicit century transition")
        checks.equal(timestamp_gpst(tick - 1), label(before, "23:59:59.000"), "explicit century previous second")
        checks.equal(timestamp_gpst(tick), label(after), "explicit century midnight")
    checks.equal(timestamp_gpst(-1), "1980-01-05T23:59:59.000 GPST", "negative GPS-epoch second")
    checks.equal(timestamp_gpst(0), "1980-01-06T00:00:00.000 GPST", "GPS epoch")
    return {"century_transitions": [[label(a), label(b)] for a, b in transitions],
            "formatter_checks": 2 * len(transitions) + 2,
            "scope": "Individual century/epoch boundary cases, including next-cycle 2400 leap day"}


def check_phase(checks, tick, reference=0):
    delta = tick - reference
    # Power-of-two arithmetic oracle, independent of the runtime's divmod.
    expected_w, expected_r = delta >> 14, delta & (PERIOD - 1)
    w, fraction = phase_winding(tick, reference, PERIOD)
    checks.equal(w, expected_w, "phase winding")
    checks.equal(fraction, expected_r / PERIOD, "phase fraction")
    checks.equal(w * PERIOD + int(fraction * PERIOD) + reference, tick, "full integer tick reconstruction")


def key_oracles(indices):
    widths = (20, 18, 14, 12)
    fields = tuple(f"{x:0{width}b}" for x, width in zip(indices, widths))
    straight = int("".join(fields), 2)
    interleaved = int("".join(field[depth] for depth in range(20)
                              for field in fields if depth < len(field)), 2)
    return straight, interleaved


def check_codecs(checks, tick):
    q = quantize(-10., .25, tick, .5)
    checks.equal(q[2], tick & (PERIOD - 1), "quantized exact 14-bit time index")
    expected_contiguous, expected_morton = key_oracles(q)
    c, m = contiguous(q), morton(q)
    checks.equal(c, expected_contiguous, "independent contiguous bit string")
    checks.equal(m, expected_morton, "independent Morton bit string")
    checks.equal(decode_contiguous(c), q, "contiguous full tuple round trip")
    checks.equal(decode_morton(m), q, "Morton full tuple round trip")
    return c, m


def audit_phase(checks, first_tick, last_tick, include_daily=True):
    # Every quotient carry in the calendar interval, with both adjacent ticks.
    first_wrap, last_wrap = (first_tick >> 14) + 1, last_tick >> 14
    wraps = max(0, last_wrap - first_wrap + 1)
    for winding in range(first_wrap, last_wrap + 1):
        boundary = winding << 14
        for tick in (boundary - 1, boundary, boundary + 1):
            check_phase(checks, tick)
    # Exhaust every possible phase value, with positive and negative windings.
    phase_cases = 0
    for base in (-(1 << 70), 0, 1 << 70):
        for remainder in range(PERIOD):
            tick = base + remainder
            check_phase(checks, tick)
            check_codecs(checks, tick)
            phase_cases += 1
    signed_cases = 0
    for base in (-(10 ** 100), -(1 << 63), -PERIOD, 0, PERIOD, (1 << 63), 10 ** 100):
        for offset in (-1, 0, 1, PERIOD - 1, PERIOD, PERIOD + 1):
            for reference in (-10 ** 80, -1, 0, 1, 10 ** 80):
                check_phase(checks, base + offset, reference)
                signed_cases += 1
    # A repeated key is only a wrapped address; winding and absolute time survive.
    collision_checks = 0
    for tick in (-PERIOD - 1, -1, 0, 1, PERIOD - 1, 10 ** 100):
        checks.equal(check_codecs(checks, tick), check_codecs(checks, tick + PERIOD), "periodic key identity")
        checks.equal(phase_winding(tick + PERIOD, 0, PERIOD)[0], phase_winding(tick, 0, PERIOD)[0] + 1, "key repeat carries winding")
        collision_checks += 1
    daily_records = 0
    if include_daily:
        seed = {"model": {"epoch_gpst_s": 0},
                "query": {"tick_s": 1., "phi_rad": .5, "chart_r0_m": 1.e9}}
        for tick in range(first_tick, last_tick + 1, DAY):
            row = chart_record(seed, tick, {"enu_m": [1.e6, 2.e6, 3.]})
            checks.equal(row["absolute_tick"], tick, "daily chart absolute time")
            checks.equal(row["winding"], tick >> 14, "daily chart winding")
            checks.equal(row["tick_phase_index"], tick & (PERIOD - 1), "daily chart phase")
            checks.equal(row["tick_phase_fraction"], (tick & (PERIOD - 1)) / PERIOD, "daily chart fraction")
            checks.equal(row["indices"][2], row["tick_phase_index"], "daily chart key time")
            checks.equal(decode_contiguous(int(row["contiguous_key_hex"], 16)), tuple(row["indices"]), "daily contiguous decode")
            checks.equal(decode_morton(int(row["morton_key_hex"], 16)), tuple(row["indices"]), "daily Morton decode")
            daily_records += 1
    return {"period_ticks": PERIOD, "calendar_interval_wraps": wraps,
            "adjacent_wrap_ticks_checked": 3 * wraps, "exhaustive_phase_cases": phase_cases,
            "signed_large_integer_reference_cases": signed_cases,
            "largest_test_tick_magnitude": "10**100 + 16385", "periodic_key_carry_cases": collision_checks,
            "daily_chart_records": daily_records,
            "integer_scope": "Arbitrary-size Python integer phase helper; not a claim that binary64 timestamps preserve arbitrary-size integer ticks"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    checks, start = Checks(), time.perf_counter()
    calendar = audit_calendar(checks)
    extra_boundaries = audit_extra_boundaries(checks)
    phase = audit_phase(checks, calendar["first_tick_gpst_s"], calendar["next_boundary_tick_gpst_s"])
    return {"profile": "GREGORIAN-PHASE-AUDIT-R1", "status": "passed" if not checks.failure_count else "failed",
            "scope": "Uniform 86400-second GPST-labelled calendar formatting and exact integer time addresses. No UTC leap-second-table validation, orbital propagation outside seed domain, or 400-year physical forecast.",
            "calendar": calendar, "extra_boundaries": extra_boundaries, "phase": phase, "checks": checks.count,
            "failure_count": checks.failure_count, "failures": checks.failures,
            "elapsed_s": time.perf_counter() - start,
            "source_sha256": {path: sha(ROOT / path) for path in
                              ("python/orbit_query.py", "python/ugts.py", "tools/validate_calendar_phase.py", "tests/test_calendar_phase.py")},
            "seed_sha256": {path.relative_to(ROOT).as_posix(): sha(path) for folder in ("seeds", "confirmation_seeds")
                            for path in sorted((ROOT / "examples/orbit" / folder).glob("*.orbseed"))},
            "runtime_changes": "none; verification tool and tests only"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/calendar_phase_36110")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = run()
    (args.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
