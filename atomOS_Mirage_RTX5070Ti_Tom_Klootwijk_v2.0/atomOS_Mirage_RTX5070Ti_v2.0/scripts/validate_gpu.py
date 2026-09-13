#!/usr/bin/env python3
"""Build and validate on the owner's CUDA machine. No elevation or driver changes."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--build",type=Path,default=ROOT/"build_gpu")
    ap.add_argument("--out",type=Path,default=ROOT/"gpu_validation")
    ap.add_argument("--sanitizer",action="store_true")
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    report={"cuda_compiled":False,"gpu_executed":False,"cpu_gpu_tests_passed":False,
            "gpu_execution_attempted":False,"compute_sanitizer_passed":None,"commands":[],"reason":None}
    def save():
        (args.out/"validation.json").write_text(json.dumps(report,indent=2)+"\n")
    missing=[name for name in ("nvcc","cmake") if not shutil.which(name)]
    if missing:
        report["reason"]=", ".join(missing)+" missing from PATH; CUDA not compiled or run"
        save();print(report["reason"],file=sys.stderr);return 2
    def run(command,name):
        p=subprocess.run(list(map(str,command)),capture_output=True,text=True)
        (args.out/(name+".txt")).write_text(p.stdout+p.stderr)
        report["commands"].append({"argv":list(map(str,command)),"returncode":p.returncode})
        if p.returncode:raise RuntimeError(f"{name} failed; see {args.out/(name+'.txt')}")
    try:
        run(["nvcc","--version"],"nvcc")
        if shutil.which("nvidia-smi"):run(["nvidia-smi"],"device")
        run(["cmake","-S",ROOT,"-B",args.build,"-DATOMOS_ENABLE_CUDA=ON","-DCMAKE_CUDA_ARCHITECTURES=120","-DCMAKE_BUILD_TYPE=Release"],"configure")
        run(["cmake","--build",args.build,"--config","Release","--parallel","2"],"build")
        report["cuda_compiled"]=True
        report["gpu_execution_attempted"]=True;report["gpu_executed"]=None
        run(["ctest","--test-dir",args.build,"-C","Release","--output-on-failure"],"ctest")
        report["gpu_executed"]=True;report["cpu_gpu_tests_passed"]=True
        exe=args.build/("Release/atomos_gpu.exe" if os.name=="nt" else "atomos_gpu")
        if not exe.exists() and os.name=="nt":exe=args.build/"atomos_gpu.exe"
        if args.sanitizer:
            if not shutil.which("compute-sanitizer"):raise RuntimeError("compute-sanitizer not on PATH")
            run(["compute-sanitizer","--tool","memcheck","--error-exitcode","1",exe,"--generations","8","--verify","--out",args.out/"memcheck_run"],"memcheck")
            run(["compute-sanitizer","--tool","memcheck","--error-exitcode","1",exe,"--mode","universal","--verify","--out",args.out/"memcheck_vm_run"],"memcheck_vm")
            run(["compute-sanitizer","--tool","racecheck","--error-exitcode","1",exe,"--mode","universal","--verify","--out",args.out/"racecheck_run"],"racecheck")
            report["compute_sanitizer_passed"]=True
    except (OSError,RuntimeError) as e:
        report["reason"]=str(e);save();print(e,file=sys.stderr);return 1
    save();print(json.dumps(report,indent=2));return 0

if __name__=="__main__":raise SystemExit(main())
