"""Reproduce the two local U packed-symbol specification obligations."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from check_proofs import engine

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=Path('results/optimization_20260913/universal_packing_proofs.json'))
args = parser.parse_args()
source = Path(__file__).with_name('universal_packing.smt2')
version, solve = engine()
start = time.perf_counter()
observed = solve(source)
result = dict(status='passed' if observed.split() == ['unsat', 'unsat'] else 'failed',
              solver=version, observed=observed, seconds=time.perf_counter()-start,
              sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              scope='Packed-symbol read-after-write and outside-bit preservation specification; not binary proof')
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result))
raise SystemExit(0 if result['status']=='passed' else 1)
