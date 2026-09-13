"""Check the NOR output identity and clean output-token specification."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from check_proofs import engine

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
source = Path(__file__).with_name('sdf_nor.smt2')
version, solve = engine()
started = time.perf_counter()
observed = solve(source)
result = dict(status='passed' if observed.split() == ['unsat', 'unsat'] else 'failed',
              solver=version, observed=observed, seconds=time.perf_counter()-started,
              sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              scope='Source whole-word absorption implements NOR under explicit carrier encoding; mathematical bit-vector specification, not SDF numeric or CUDA binary proof')
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result))
raise SystemExit(0 if result['status']=='passed' else 1)
