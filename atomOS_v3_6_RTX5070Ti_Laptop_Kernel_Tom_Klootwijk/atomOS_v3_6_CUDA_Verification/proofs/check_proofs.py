#!/usr/bin/env python3
"""Run independent SMT-LIB obligations with Z3 binary or the Z3 C library.

UNSAT proves the negated SPECIFICATION property has no counterexample within its
stated bit-vector domain. It is not compiler or machine-code verification.
"""
from __future__ import annotations
import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent

def engine():
    executable=shutil.which('z3')
    if executable:
        version=subprocess.check_output([executable,'-version'],text=True).strip()
        def run(path):
            p=subprocess.run([executable,str(path)],capture_output=True,text=True,timeout=40,check=True)
            return p.stdout.strip()
        return version,run
    name=ctypes.util.find_library('z3')
    if not name:
        try:
            import z3
            base=Path(z3.__file__).parent
            candidates=list(base.rglob('libz3.so*'))+list(base.rglob('libz3.dylib'))+list(base.rglob('libz3.dll'))
            name=str(candidates[0]) if candidates else None
        except ImportError:
            pass
    if not name:raise RuntimeError('No Z3 executable/library: install the optional z3-solver package or Z3 locally.')
    lib=ctypes.CDLL(name)
    lib.Z3_get_full_version.restype=ctypes.c_char_p
    lib.Z3_mk_config.restype=ctypes.c_void_p
    lib.Z3_del_config.argtypes=[ctypes.c_void_p]
    lib.Z3_mk_context.argtypes=[ctypes.c_void_p];lib.Z3_mk_context.restype=ctypes.c_void_p
    lib.Z3_del_context.argtypes=[ctypes.c_void_p]
    lib.Z3_eval_smtlib2_string.argtypes=[ctypes.c_void_p,ctypes.c_char_p];lib.Z3_eval_smtlib2_string.restype=ctypes.c_char_p
    def run(path):
        cfg=lib.Z3_mk_config();ctx=lib.Z3_mk_context(cfg);lib.Z3_del_config(cfg)
        try:return lib.Z3_eval_smtlib2_string(ctx,path.read_bytes()).decode().strip()
        finally:lib.Z3_del_context(ctx)
    return lib.Z3_get_full_version().decode(),run

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT.parent/'results/proofs.json');a=p.parse_args()
    try:version,run=engine()
    except RuntimeError as exc:
        print(json.dumps({'status':'not_run','reason':str(exc)}));return 3
    records=[]
    for claim in json.loads((ROOT/'obligations.json').read_text()):
        path=ROOT/claim['file'];start=time.monotonic();observed=run(path)
        records.append({**claim,'observed':observed,'passed':observed==claim['expected'],'seconds':time.monotonic()-start,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        print(claim['id']+': '+observed,flush=True)
    result={'scope':'Symbolic specification properties, not source-code or GPU equivalence proof','solver':'Z3 '+version,'status':'passed' if all(r['passed'] for r in records) else 'failed','obligations':records}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    return 0 if result['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
