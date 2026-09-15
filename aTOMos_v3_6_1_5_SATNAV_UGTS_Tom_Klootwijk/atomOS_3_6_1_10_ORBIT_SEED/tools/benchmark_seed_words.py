#!/usr/bin/env python3
"""Compare exact word transposition and complete seed I/O with the preserved release."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import random
import statistics
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import orbit_seed as current


def load_module(path):
    spec = importlib.util.spec_from_file_location("preserved_orbit_seed", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def median_seconds(function, repeats=9, loops=5):
    function()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        for _ in range(loops):
            function()
        samples.append((time.perf_counter() - start) / loops)
    return {"median_s": statistics.median(samples), "min_s": min(samples),
            "max_s": max(samples), "repeats": repeats, "loops": loops}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT.parent / "atomOS_3_6_1_9_ORBIT_SEED")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    baseline = load_module(args.baseline / "python/orbit_seed.py")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        parser.error("Choose a new output path")

    # Exhaust all basis vectors: each of 4096 input bits must reach its specified
    # output lane. The six stages use only XOR/masks, so this also proves the
    # mapping for every block by GF(2) linearity, including arbitrary float bits.
    for row in range(64):
        for bit in range(64):
            words = [0] * 64
            words[row] = 1 << bit
            expected = [0] * 64
            expected[bit] = 1 << row
            encoded = current.words_to_bitplanes(words)
            assert encoded == struct.pack("<64Q", *expected)
            assert current.bitplanes_to_words(encoded, 64) == words

    rng = random.Random(36110)
    lengths = list(range(130)) + [191, 192, 193, 1023, 1024, 1025, 4096]
    for count in lengths:
        words = [rng.getrandbits(64) for _ in range(count)]
        encoded = current.words_to_bitplanes(words)
        assert encoded == baseline.words_to_bitplanes(words)
        assert current.bitplanes_to_words(encoded, count) == words

    seeds = []
    for directory in ("seeds", "confirmation_seeds"):
        for path in sorted((args.baseline / "examples/orbit" / directory).glob("*.orbseed")):
            data = path.read_bytes()
            old, new = baseline.unpack_bytes(data), current.unpack_bytes(data)
            assert current.pack_bytes(new) == baseline.pack_bytes(old) == data
            assert current.digest(new) == baseline.digest(old)
            seeds.append({"path": path.relative_to(args.baseline).as_posix(),
                          "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                          "seed_sha256": current.digest(new), "model_sha256": current.digest(new["model"])})

    path = args.baseline / "examples/orbit/seeds/C03.orbseed"
    data = path.read_bytes()
    seed = current.unpack_bytes(data)
    numbers = []
    current._encode(seed, numbers=numbers)
    planes = current.words_to_bitplanes(numbers)
    jobs = {
        "words_to_planes": (lambda: baseline.words_to_bitplanes(numbers), lambda: current.words_to_bitplanes(numbers)),
        "planes_to_words": (lambda: baseline.bitplanes_to_words(planes, len(numbers)), lambda: current.bitplanes_to_words(planes, len(numbers))),
        "complete_pack": (lambda: baseline.pack_bytes(seed), lambda: current.pack_bytes(seed)),
        "complete_unpack": (lambda: baseline.unpack_bytes(data), lambda: current.unpack_bytes(data)),
    }
    timings = {}
    for name, (before, after) in jobs.items():
        a, b = median_seconds(before), median_seconds(after)
        timings[name] = {"baseline": a, "optimized": b, "median_speedup": a["median_s"] / b["median_s"]}
    report = {"status": "passed", "scope": "Exact representation and local host timing; no change to orbital arithmetic or physical accuracy",
              "python": sys.version, "platform": platform.platform(),
              "basis_vectors": 4096, "random_lengths": lengths, "numeric_words_in_timing_seed": len(numbers),
              "seeds": seeds, "timings": timings,
              "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                [ROOT / "python/orbit_seed.py", args.baseline / "python/orbit_seed.py"]}}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "seeds": len(seeds), "timings": timings}, indent=2))


if __name__ == "__main__":
    main()
