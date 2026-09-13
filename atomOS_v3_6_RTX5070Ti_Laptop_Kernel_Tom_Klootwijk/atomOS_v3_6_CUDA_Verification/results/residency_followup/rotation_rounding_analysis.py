"""Exact rational enclosure for the fixed K1 rotation, plus 100-digit mpmath.

The Taylor proof applies to the exact value of the binary64 literal 0.4, not to
the different rational 2/5. All enclosure and rounding-bin comparisons below use
fractions of integers; decimal strings are only presentation.
"""
from datetime import datetime, timezone
from decimal import Decimal, localcontext, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import math
import struct
import sys
import mpmath as mp


def rational_record(value, direction=ROUND_FLOOR):
    with localcontext() as context:
        context.prec = 170
        context.rounding = direction
        decimal = str(Decimal(value.numerator) / Decimal(value.denominator))
    return {"numerator": str(value.numerator), "denominator": str(value.denominator),
            "decimal_outward_rounded": decimal}


def taylor_enclosure(x, name, count=40):
    assert 0 < x < 1
    term = Fraction(1) if name == "cos" else x
    partial = Fraction(0)
    for k in range(count):
        partial += term
        first = 2 * k + (1 if name == "cos" else 2)
        following = -term * x * x / (first * (first + 1))
        assert abs(following) < abs(term)
        term = following
    # The terms alternate and decrease to zero because 0<x<1. The true value
    # lies strictly between the partial sum and the sum including its next term.
    return min(partial, partial + term), max(partial, partial + term), term


def main():
    mp.mp.dps = 100
    x = Fraction.from_float(0.4)
    assert x == Fraction(3602879701896397, 9007199254740992)
    exact_mpf = mp.mpf(x.numerator) / x.denominator
    report = {
        "schema": "atomOS-K1-fixed-rotation-rounding-v1",
        "status": "passed",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "mpmath_version": mp.__version__,
        "mpmath_decimal_precision": mp.mp.dps,
        "input": {"literal": ".4", "binary64_hex": (0.4).hex(), **rational_record(x)},
        "proof_method": "40-term exact rational alternating Taylor sums with next-term enclosures, strictly inside one binary64 nearest-rounding bin",
        "proof_assumptions": [
            "The analytic alternating Taylor expansions for sine and cosine at 0<x<1.",
            "The next-term alternating-series remainder bound, justified by strictly decreasing term magnitudes tending to zero.",
            "IEEE-754 binary64 rounding to nearest; neither result is a midpoint tie."
        ],
        "evidence_categories": {"exact_rational_rounding_enclosure": "passed",
                                "gpu_literal_runtime_comparison": "not_run",
                                "gpu_cache_effect": "not_run"},
        "results": {}
    }
    for name in ("cos", "sin"):
        high_precision = getattr(mp, name)(exact_mpf)
        candidate = float(high_precision)
        previous = math.nextafter(candidate, -math.inf)
        following = math.nextafter(candidate, math.inf)
        lower_midpoint = (Fraction.from_float(previous) + Fraction.from_float(candidate)) / 2
        upper_midpoint = (Fraction.from_float(candidate) + Fraction.from_float(following)) / 2
        low, high, next_term = taylor_enclosure(x, name)
        assert lower_midpoint < low < high < upper_midpoint
        assert high - low < Fraction(1, 10**100)
        bits = struct.unpack(">Q", struct.pack(">d", candidate))[0]
        report["results"][name] = {
            "mpmath_value_100_digits": mp.nstr(high_precision, 100),
            "nearest_binary64_hex": candidate.hex(),
            "nearest_binary64_bits": f"0x{bits:016x}",
            "nearest_binary64_decimal_17_digits": format(candidate, ".17g"),
            "previous_binary64_hex": previous.hex(),
            "following_binary64_hex": following.hex(),
            "taylor_terms": 40,
            "enclosure_lower": rational_record(low, ROUND_FLOOR),
            "enclosure_upper": rational_record(high, ROUND_CEILING),
            "enclosure_width": rational_record(abs(next_term), ROUND_CEILING),
            "rounding_bin_lower_midpoint": rational_record(lower_midpoint, ROUND_FLOOR),
            "rounding_bin_upper_midpoint": rational_record(upper_midpoint, ROUND_CEILING),
            "lower_strict_margin": rational_record(low - lower_midpoint, ROUND_FLOOR),
            "upper_strict_margin": rational_record(upper_midpoint - high, ROUND_FLOOR),
            "strictly_inside_unique_rounding_bin": True,
            "host_python_math_hex": getattr(math, name)(0.4).hex()
        }
    script = Path(__file__).resolve()
    report["analysis_source_sha256"] = hashlib.sha256(script.read_bytes()).hexdigest()
    output = script.with_name("rotation_rounding.json")
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output),
                      "cos": report["results"]["cos"]["nearest_binary64_hex"],
                      "sin": report["results"]["sin"]["nearest_binary64_hex"],
                      "gpu_comparison": "not_run"}, indent=2))


if __name__ == "__main__":
    main()
