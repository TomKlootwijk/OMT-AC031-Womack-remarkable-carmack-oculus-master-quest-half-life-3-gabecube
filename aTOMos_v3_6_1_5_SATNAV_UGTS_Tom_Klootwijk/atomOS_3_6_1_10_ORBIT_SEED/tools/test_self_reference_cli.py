#!/usr/bin/env python3
"""Reproduce the 25 SRK-R1 CPU CLI cases in results/selfref_cli_checks.json.

Usage: python tools/test_self_reference_cli.py --binary PATH_TO_CPU_EXECUTABLE
                                             --out NEW_REPORT.json

Use an executable built with SATNAV_ENABLE_CUDA=OFF: the last case deliberately
verifies that requesting its unbuilt CUDA backend reports not_run with exit 3.
The report path must be new. Fixture CSVs and native outputs use a temporary
directory; no package-relative input or hardcoded build path is required.
"""

import argparse
import csv
import json
from pathlib import Path
import subprocess
import tempfile


HEADER = (
    "trajectory_id,q0,drive,present,asa_mask,na_mask,boundary_mask,"
    "x_lut,j_lut,k_lut,steps"
)
BASE = ["0", "3", "1", "15", "15", "15", "0", "6", "204", "51", "4"]


def require(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def check_cli(binary, checks):
    with tempfile.TemporaryDirectory(prefix="srk3616_cli_") as temporary:
        root = Path(temporary)

        def invoke(path, out, backend="cpu", extra=()):
            return subprocess.run(
                [str(binary), "--input", str(path), "--out", str(out),
                 "--backend", backend, *extra],
                capture_output=True, text=True,
            )

        def reject_fixture(name, body):
            path = root / (name + ".csv")
            path.write_text(body, encoding="ascii")
            out = root / (name + "_out")
            result = invoke(path, out)
            require(result.returncode != 0 and not out.exists(),
                    f"{name}: expected rejected input without output; "
                    f"exit={result.returncode}, stdout={result.stdout!r}, "
                    f"stderr={result.stderr!r}")
            checks.append({"case": name, "status": "pass",
                           "message": result.stderr.strip()})

        invalid_fields = {
            "negative_id": (0, "-1"),
            "id_overflow": (0, "18446744073709551616"),
            "word_overflow": (1, "4294967296"),
            "non_decimal": (2, "0xff"),
            "fraction": (2, "1.0"),
            "spaces": (2, " 1"),
            "outside_present": (1, "16"),
            "x_lut_overflow": (7, "16"),
            "j_lut_overflow": (8, "256"),
            "k_lut_overflow": (9, "256"),
            "zero_steps": (10, "0"),
            "steps_overflow": (10, "18446744073709551616"),
            "allocation_overflow": (10, "18446744073709551615"),
        }
        for name, (column, value) in invalid_fields.items():
            row = BASE.copy()
            row[column] = value
            reject_fixture(name, HEADER + "\n" + ",".join(row) + "\n")

        malformed = [
            ("duplicate_id", HEADER + "\n" + ",".join(BASE) + "\n"
             + ",".join(BASE) + "\n"),
            ("empty_jobs", HEADER + "\n"),
            ("bad_header", "bad\n"),
            ("missing_field", HEADER + "\n" + ",".join(BASE[:-1]) + "\n"),
            ("blank_row", HEADER + "\n\n"),
        ]
        for name, body in malformed:
            reject_fixture(name, body)

        path = root / "valid.csv"
        out = root / "valid_out"
        path.write_text(
            HEADER + "\n" + ",".join(BASE) + "\n"
            "18446744073709551615,4294967295,4294967295,4294967295,"
            "4294967295,4294967295,0,15,255,255,2\n",
            encoding="ascii",
        )
        result = invoke(path, out)
        require(result.returncode == 0,
                f"valid input rejected: {result.stdout!r} {result.stderr!r}")
        with (out / "trace.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        metadata = json.loads((out / "run.json").read_text(encoding="utf-8"))
        require(len(rows) == 6
                and rows[4]["trajectory_id"] == "18446744073709551615"
                and rows[4]["after"] == "0"
                and rows[5]["after"] == "4294967295",
                "maximum-word/id fixture trace mismatch")
        require(metadata["trace_rows"] == 6
                and metadata["profile"] == "SRK-R1"
                and metadata["version"] == "3.6.1.6",
                "maximum-word/id fixture metadata mismatch")
        checks.append({"case": "valid_maximum_words_and_id", "status": "pass",
                       "trace_rows": len(rows)})

        original = (out / "trace.csv").read_bytes()
        result = invoke(path, out)
        require(result.returncode != 0 and (out / "trace.csv").read_bytes() == original,
                "existing output was accepted or changed")
        checks.append({"case": "existing_output_preserved", "status": "pass",
                       "message": result.stderr.strip()})

        invalid_options = [
            ("unknown_option", ["--wat"]),
            ("duplicate_option", ["--backend", "cpu"]),
            ("negative_device", ["--device", "-1"]),
            ("missing_option_value", ["--device"]),
        ]
        for name, extra in invalid_options:
            result = invoke(path, root / name, extra=extra)
            require(result.returncode != 0,
                    f"{name}: invalid CLI option was accepted")
            checks.append({"case": name, "status": "pass",
                           "message": result.stderr.strip()})

        unavailable_out = root / "unbuilt_cuda_out"
        result = invoke(path, unavailable_out, backend="cuda")
        require(result.returncode == 3 and "not_run" in result.stderr
                and not unavailable_out.exists(),
                "unbuilt_cuda_reports_not_run: expected exit 3, not_run and no "
                "output; use a CPU-only executable (SATNAV_ENABLE_CUDA=OFF). "
                f"Got exit={result.returncode}, stderr={result.stderr!r}")
        checks.append({"case": "unbuilt_cuda_reports_not_run", "status": "pass",
                       "exit_code": result.returncode,
                       "message": result.stderr.strip()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True,
                        help="CPU-only self_reference executable")
    parser.add_argument("--out", type=Path, required=True,
                        help="new JSON report file")
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    require(binary.is_file(), "--binary must name an executable file")
    require(not args.out.exists(), "report already exists; choose a new --out")
    report = {"version": "3.6.1.6", "profile": "SRK-R1", "status": "failed",
              "cases": 0, "executable": str(binary), "checks": []}
    # Compiler identity belongs to the build log; it cannot be inferred reliably
    # from an arbitrary supplied executable, so it is not invented in this report.
    code = 0
    try:
        check_cli(binary, report["checks"])
        report["status"] = "pass"
    except (OSError, RuntimeError, ValueError, KeyError, IndexError) as error:
        report["error"] = str(error)
        code = 1
    report["cases"] = len(report["checks"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(f"{report['cases']} CLI cases passed; status={report['status']}")
    if code:
        print(report["error"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
