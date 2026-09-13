#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from reference import verify_run
p=argparse.ArgumentParser(description='Independent Python conformance checker for every recorded word epoch')
p.add_argument('directory',type=Path);a=p.parse_args()
try:print(json.dumps(verify_run(a.directory),indent=2))
except (OSError,ValueError,KeyError,TypeError) as exc:
    print(f'FAIL: {exc}',file=sys.stderr);raise SystemExit(1)
