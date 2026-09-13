#!/usr/bin/env python3
"""Distill example-driven finite skills into seeded Klein/log-polar program LUTs."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from program_bank import builtin_examples, distill, seed_digest, write_bank


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, help="external atomos-teacher-examples-v1 JSON; omit for synthetic independent teachers")
    parser.add_argument("--seed", default="atomOS finite skill distillation v1")
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--angles", type=int, default=256)
    parser.add_argument("--max-operators", type=int, default=3)
    parser.add_argument("--candidate-budget", type=int, default=12000)
    parser.add_argument("--train-count", type=int, default=40, help="built-in teachers only")
    parser.add_argument("--parent-sha256", help="optional retained predecessor digest")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("--out must not exist; retained learning evidence is never overwritten")
    data = json.loads(args.examples.read_text(encoding="utf-8")) if args.examples else builtin_examples(args.seed, args.train_count)
    packages, receipt = distill(data, args.seed, max_operators=args.max_operators,
                               candidate_budget=args.candidate_budget, parent_digest256=args.parent_sha256)
    args.out.mkdir(parents=True)
    (args.out / "teacher_examples.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (args.out / "learning.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    manifest = None
    if packages:
        manifest = write_bank(args.out / "bank.bin", packages, master_seed_hex=seed_digest(args.seed),
                              rows=args.rows, angles=args.angles)
    print(json.dumps({"status": receipt["status"], "accepted_skills": len(packages),
                      "requested_skills": receipt["requested_skills"],
                      "bank": str(args.out / "bank.bin") if manifest else None,
                      "claim_scope": receipt["claim_scope"],
                      "learning_receipt": str(args.out / "learning.json")}, indent=2))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
