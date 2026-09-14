#!/usr/bin/env python3
"""Generate deterministic SRK-R1 equations for GPU block and variable-offset coverage.

Default: seed 3616, 257 independent trajectories, step lengths spanning 1..32,
32-bit masks/drive/state, and boundary zero on every even-indexed trajectory.
The output path must not exist. Regeneration with the same seed/count is byte exact.
"""
from pathlib import Path
import argparse
import json
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from self_reference import PROFILE, VERSION, parse_document


X_EXPRESSIONS = (
    "q | d", "q ^ d", "q & d", "q", "d", "~q", "~d", "0", "1",
    "(~q & d) | (q & ~d)", "(q & d) | (~q & ~d)", "q & ~d",
    "~(q | d)", "~(q & d)", "(q ^ d) | ~q", "(q | d) & ~q",
)
JK_EXPRESSIONS = (
    "0", "1", "q", "y", "d", "~q", "~y", "~d", "q ^ y", "q ^ d",
    "y ^ d", "q | y | d", "q & y & d", "(q & y) | (~q & d)",
    "(~q & y) | (q & d)", "(q & ~y) | (~q & d)", "q ^ y ^ d",
    "~(q ^ (y | d))", "(q | y) & (~q | d)", "(y & d) | (q & ~d)",
    "~(q | (y & d))", "(q & y) ^ (d | ~y)", "q | ~q", "y & ~y",
)


def generate(seed=3616, count=257):
    if type(seed) is not int or type(count) is not int or count <= 0:
        raise ValueError("seed must be an integer and count must be a positive integer")
    rng = random.Random(seed)
    trajectories = []
    for index in range(count):
        present = rng.getrandbits(32)
        trajectories.append({
            "id": index,
            "q0": rng.getrandbits(32) & present,
            "drive": rng.getrandbits(32),
            "present": present,
            "asa_mask": rng.getrandbits(32),
            "na_mask": rng.getrandbits(32),
            "boundary_mask": 0 if index % 2 == 0 else rng.getrandbits(32),
            # 13 is coprime to 32: each group of 32 covers all step lengths.
            "steps": 1 + (index * 13) % 32,
            "equations": {
                "x": rng.choice(X_EXPRESSIONS),
                "j": rng.choice(JK_EXPRESSIONS),
                "k": rng.choice(JK_EXPRESSIONS),
            },
        })
    document = {
        "version": VERSION,
        "profile": PROFILE,
        "description": f"Deterministic block/index stress: seed {seed}; {count} independent trajectories; "
                       "steps span 1..32; even-indexed boundary masks are zero.",
        "trajectories": trajectories,
    }
    parse_document(document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="new JSON equation input file")
    parser.add_argument("--seed", type=int, default=3616)
    parser.add_argument("--trajectories", type=int, default=257)
    args = parser.parse_args()
    try:
        document = generate(args.seed, args.trajectories)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="ascii", newline="\n") as stream:
            stream.write(json.dumps(document, indent=2, ensure_ascii=True) + "\n")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps({"output": str(args.out), "seed": args.seed,
                      "trajectories": len(document["trajectories"]),
                      "transitions": sum(row["steps"] for row in document["trajectories"])}, indent=2))


if __name__ == "__main__":
    main()
