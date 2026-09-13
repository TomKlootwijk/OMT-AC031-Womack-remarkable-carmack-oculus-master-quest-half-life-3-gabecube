#!/usr/bin/env python3
"""Recompute all 48 bundled CPU matrix outputs and verify their retained run seals."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from reference import verify_run
from provenance import verify_seal

def main():
    base=(ROOT/'results/cpu_matrix_evidence').resolve()
    report=json.loads((base/'validation.json').read_text())
    verified=0;total=0
    for entry in report['runs']:
        p=(base/entry['path']).resolve()
        if not p.is_relative_to(base) or not p.is_dir():raise ValueError('invalid evidence path')
        actual=verify_run(p)
        if actual['integer_semantic_sha256']!=entry['integer_semantic_sha256'] or not verify_seal(p):raise ValueError('evidence hash/semantics differ')
        verified+=1;total+=actual['lane_epochs']
    if verified!=48:raise ValueError('unexpected matrix size')
    print(json.dumps({'status':'passed','bundled_cpu_runs_recomputed':verified,'lane_epochs':total,'gpu_execution':'not_performed_by_this_check'},indent=2))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError) as e:print('FAIL:',e,file=sys.stderr);raise SystemExit(1)
