#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from python.reference import verify_directory
from python.provenance import verify
p=argparse.ArgumentParser(description='Run independent scalar checks and optional record-seal verification')
p.add_argument('directory',type=Path)
p.add_argument('--head')
a=p.parse_args()
try:
    result=verify_directory(a.directory)
    if (a.directory/'seal.json').exists():
        if not verify(a.directory,a.head):raise ValueError('seal mismatch')
        result['seal']='pass'
    elif a.head is not None:raise ValueError('expected head supplied but no seal exists')
    print(json.dumps(result,indent=2))
except (OSError,ValueError,AssertionError,KeyError) as e:
    print(str(e),file=sys.stderr);raise SystemExit(1)
