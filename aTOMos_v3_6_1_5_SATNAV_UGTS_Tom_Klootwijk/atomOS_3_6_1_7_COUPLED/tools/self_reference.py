#!/usr/bin/env python3
"""Compile SRK-R1 equations, run direct AST replay, optionally execute/verify native code.

--input equations.json --out NEWDIR: write input.csv, reference_trace.csv and summary.json.
Add --binary PATH [--backend cpu|cuda --device N] to run native code in NEWDIR/native
and independently compare every native trace field. Alternatively --verify RUN_DIR
compares an existing native trace. Equation language and JSON schema are documented
in python/self_reference.py. Each result directory must be new.
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from self_reference import (PROFILE, VERSION, file_digest, load_document, replay, write_compiled)


class NativeUnavailableError(RuntimeError):
    pass


def run(args):
    trajectories = load_document(args.input)
    args.out.mkdir(parents=True, exist_ok=False)
    compiled = args.out / "input.csv"
    write_compiled(trajectories, compiled)
    (args.out / "equations.json").write_bytes(args.input.read_bytes())
    report = {"version": VERSION, "profile": PROFILE, "status": "failed",
              "input_sha256": file_digest(args.input), "compiled_csv_sha256": file_digest(compiled),
              "native_execution": "not_run", "native_trace_verified": False}
    try:
        actual = None
        if args.binary is not None:
            binary = args.binary.resolve(strict=True)
            native = args.out / "native"
            command = [str(binary), "--input", str(compiled.resolve()), "--out", str(native.resolve()),
                       "--backend", args.backend, "--device", str(args.device)]
            report.update(native_command=command, native_binary_sha256=file_digest(binary))
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            (args.out / "native.stdout.txt").write_text(completed.stdout, encoding="utf-8")
            (args.out / "native.stderr.txt").write_text(completed.stderr, encoding="utf-8")
            report.update(native_returncode=completed.returncode,
                          native_execution="passed" if completed.returncode == 0 else
                          "not_run" if completed.returncode == 3 else "failed")
            if completed.returncode == 3:
                report["status"] = "not_run"
                raise NativeUnavailableError("Requested native backend unavailable; see captured logs")
            if completed.returncode != 0:
                raise RuntimeError(f"Native executable returned {completed.returncode}; see captured logs")
            actual = native / "trace.csv"
        elif args.verify is not None:
            actual = args.verify / "trace.csv"
        result = replay(trajectories, trace_path=args.out / "reference_trace.csv", actual_path=actual)
        report.update(result)
        report["reference_trace_sha256"] = file_digest(args.out / "reference_trace.csv")
        if actual is not None:
            report["native_trace_sha256"] = file_digest(actual)
        return report
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        (args.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True, help="SRK-R1 JSON equation input")
    parser.add_argument("--out", type=Path, required=True, help="new compilation/replay/report directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--binary", type=Path, help="native self_reference executable to execute and verify")
    mode.add_argument("--verify", type=Path, help="existing native run directory to verify")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()
    if args.device < 0:
        parser.error("--device must be nonnegative")
    try:
        report = run(args)
    except NativeUnavailableError as exc:
        print(f"NOT_RUN: {exc}", file=sys.stderr)
        return 3
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({key: report[key] for key in ("status", "transitions", "field_comparisons",
                                                  "native_execution", "native_trace_verified")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
