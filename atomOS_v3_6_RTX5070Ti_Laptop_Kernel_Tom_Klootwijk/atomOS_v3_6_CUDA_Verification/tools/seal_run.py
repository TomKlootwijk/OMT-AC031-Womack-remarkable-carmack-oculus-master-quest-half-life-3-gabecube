#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from provenance import seal_run,verify_seal
p=argparse.ArgumentParser(description='Seal a local run or verify it against the retained unsigned seal')
p.add_argument('directory',type=Path);p.add_argument('--verify',action='store_true');p.add_argument('--label',action='append');a=p.parse_args()
try:
    if a.verify:
        passed=verify_seal(a.directory);print('PASS: integrity matches retained seal' if passed else 'FAIL: data differs');raise SystemExit(0 if passed else 1)
    print(json.dumps(seal_run(a.directory,a.label or ['atomOS:synthetic:K1']),indent=2))
except (OSError,ValueError,KeyError,TypeError) as exc:
    print(f'FAIL: {exc}',file=sys.stderr);raise SystemExit(1)
