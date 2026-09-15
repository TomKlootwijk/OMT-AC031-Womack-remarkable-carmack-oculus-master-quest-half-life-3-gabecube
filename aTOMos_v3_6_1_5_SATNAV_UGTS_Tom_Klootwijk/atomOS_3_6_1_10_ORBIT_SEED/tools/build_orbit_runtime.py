#!/usr/bin/env python3
"""Create a small replay bundle; source/reference audit datasets stay in the full release."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    modules = ["orbit_seed", "orbit_native", "orbit_dynamics", "orbit_precision", "orbit_query", "self_reference", "ugts", "geodesy"]
    paths = [ROOT / "python" / (name + ".py") for name in modules]
    paths += [ROOT / "tools" / (name + ".py") for name in ("orbital_seed", "orbit_scrub", "verify_orbit_run", "verify_package")]
    paths += [ROOT / "requirements.txt", ROOT / "web/orbit_scrubber.html"]
    paths += [ROOT / "bin" / backend / "orbit_worker.exe" for backend in ("cpu", "cuda")]
    for directory in ("seeds", "confirmation_seeds"):
        paths += sorted((ROOT / "examples/orbit" / directory).glob("*.json"))
        paths += sorted((ROOT / "examples/orbit" / directory).glob("*.orbseed"))
    paths += [ROOT / "results" / directory / "accuracy_summary.json" for directory in
              ("orbit_accuracy_r2_cpu_verified", "orbit_accuracy_confirmation_cpu_verified")]
    paths += [ROOT / "results" / name for name in ("orbit_r2_24h_tolerance_verified.json", "orbit_confirmation_24h_tolerance_verified.json")]
    payload = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in paths}
    payload["README.md"] = b"""# aTOMos 3.6.1.10 orbital replay runtime

From this extracted folder on Windows:

    python -m pip install -r requirements.txt
    python tools/verify_package.py
    python tools/orbit_scrub.py

Open http://127.0.0.1:3619 in your browser. The default January seeds are under
examples/orbit/seeds. February confirmation seeds are in confirmation_seeds;
to use them, pass --seeds examples/orbit/confirmation_seeds and
--accuracy results/orbit_accuracy_confirmation_cpu_verified/accuracy_summary.json.

Version3.6.1.10 uses a six-stage exact bit transpose and deduplicates identical
native batch timestamps. Each session freezes its seed/model identity. Edit an
exported copy and create a new session; start a new worker for a changed physical
model. Native transport3 enforces the declared time domain and reference Earth
surface. Compatible seed schema version remains3.6.1.9.

Exact timestamp query:

    python tools/orbital_seed.py query --seed examples/orbit/seeds/C03.orbseed --worker bin/cpu/orbit_worker.exe --time-s 12345.678 --out NEW_QUERY.json

Edit a JSON seed companion and repack:

    python tools/orbital_seed.py pack --input MY_SEED.json --out MY_SEED.orbseed

The default codec packs all original numeric bits into 64 one-bit planes held
in uint64 words. It does not reduce a numeric value to one bit or replace
binary64 propagation. Both explicit ASA/NA mask sets and synchronous JK remain.
The prior canonical codec is selectable with --codec canonical-zlib.

The seeds reconstruct from embedded initial state, gravity, Sun/Moon forcing,
Earth frame, station configuration and provenance. No original observations,
future target table or Internet lookup are required during replay. Python,
NumPy/SciPy and the native operating-system runtime are shared dependencies.
Numba/ERFA/JPL libraries are not required for native packed replay.

The CPU worker is the default. The CUDA worker was tested on SM120 hardware;
use --worker bin/cuda/orbit_worker.exe --backend cuda for that backend.

These examples describe archived January/February 2025 orbits. Both date sets
remain below the explicit 10 m engineering budget at every tested first-day
reference epoch for all four satellites. This is sampled evidence, not a
continuous-time or universal physical bound. Some longer intervals fail; the
February GEO reference also has a later 48-hour gap. Chandra reference products
have documented later position/velocity discontinuities. Seed-domain membership
does not establish accuracy. Local demo stations are not surveyed user hardware.

This compact bundle omits raw reference datasets, full source/build history,
long audit traces and the equation PDF. Those are delivered separately in the
complete 3.6.1.10 archive and PDF. The accuracy summaries retain model identities;
the complete reference CSV curves and provenance are in that full release.
"""
    manifest = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, data in sorted(payload.items()))
    payload["SHA256SUMS.txt"] = manifest.encode()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    prefix = "aTOMos_3_6_1_10_Orbit_Runtime/"
    with zipfile.ZipFile(args.out, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payload.items()): archive.writestr(prefix + name, data)
    with zipfile.ZipFile(args.out) as archive:
        if archive.testzip() is not None: raise ValueError("Runtime archive CRC error")
        for name, data in payload.items():
            if archive.read(prefix + name) != data: raise ValueError("Runtime archive byte mismatch")
    print(f"Verified {len(payload)} runtime members; {args.out.stat().st_size:,} bytes")


if __name__ == "__main__": main()
