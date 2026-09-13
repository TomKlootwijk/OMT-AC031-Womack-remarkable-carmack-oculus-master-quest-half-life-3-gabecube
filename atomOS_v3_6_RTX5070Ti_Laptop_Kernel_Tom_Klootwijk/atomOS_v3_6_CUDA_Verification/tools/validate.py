#!/usr/bin/env python3
"""Build and verify K1; optional GPU proof-of-conformance run with saved evidence."""
from __future__ import annotations
import argparse,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from reference import verify_run
from provenance import seal_run,verify_seal

def find_compute_sanitizer(requested:Path|None=None)->Path|None:
    found=str(requested) if requested else shutil.which('compute-sanitizer')
    if not found:return None
    path=Path(found).resolve()
    if path.suffix.lower() in ('.bat','.cmd'):
        # CUDA's bin/compute-sanitizer.bat forwards to the native executable.
        # Keep shell-free subprocess execution even when PATH finds the wrapper.
        native=path.parent.parent/'compute-sanitizer'/'compute-sanitizer.exe'
        return native if native.is_file() else None
    return path if path.is_file() else None

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpu',action='store_true');p.add_argument('--sanitizer',action='store_true',help='GPU memcheck after the normal GPU matrix')
    p.add_argument('--proofs',action='store_true',help='Require all Z3 symbolic obligations')
    p.add_argument('--build',type=Path);p.add_argument('--device',type=int,default=0)
    p.add_argument('--sanitizer-executable',type=Path,help='Explicit native Compute Sanitizer executable; CUDA Windows wrappers are resolved automatically')
    p.add_argument('--cmake-arg',action='append',default=[],help='Additional configure argument, e.g. --cmake-arg=-Tcuda=12.8 on Windows')
    args=p.parse_args()
    if args.sanitizer and not args.gpu:p.error('--sanitizer requires --gpu')
    if args.device<0 or args.device>1024:p.error('device ordinal out of range')
    build=(args.build or ROOT/('build_gpu' if args.gpu else 'build_cpu')).resolve()
    evidence=build/('evidence_'+str(time.time_ns()));evidence.mkdir(parents=True)
    status={'schema':'atomOS-v3.6-K1-validation','cpu':'not_run','proofs':'not_requested','cuda_build':'not_run','gpu':'not_run','gpu_memcheck':'not_requested','runs':[],'commands':[]}
    def save():
        (evidence/'validation.json').write_text(json.dumps(status,indent=2)+'\n')
    def run(command:list[str],label:str)->str:
        log=evidence/(label+'.log');print('+',subprocess.list2cmdline(command),flush=True)
        with log.open('w',encoding='utf-8') as f:
            r=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,text=True)
        status['commands'].append({'command':command,'exit_code':r.returncode,'log':log.name});save()
        if r.returncode:raise RuntimeError(f'{label} failed with exit {r.returncode}; see {log}')
        return log.read_text()
    try:
        if args.gpu and not shutil.which('nvcc'):
            status['reason']='nvcc unavailable; GPU work not run';status['status']='not_run';save();print(json.dumps(status,indent=2));print('Evidence:',evidence);return 3
        sanitizer=find_compute_sanitizer(args.sanitizer_executable) if args.sanitizer else None
        if args.sanitizer and sanitizer is None:
            status['reason']='Compute Sanitizer unavailable; requested GPU memory check not run';status['status']='not_run';save();print(json.dumps(status,indent=2));return 3
        run(['cmake','-S',str(ROOT),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DATOMOS_ENABLE_CUDA='+('ON' if args.gpu else 'OFF'),*args.cmake_arg],'configure')
        run(['cmake','--build',str(build),'--config','Release','--parallel','2'],'build')
        if args.gpu:status['cuda_build']='passed'
        run(['ctest','--test-dir',str(build),'-C','Release','--output-on-failure','-E','^cuda_'],'cpu_ctest')
        run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_reference.py','-v'],'python_tests');status['cpu']='passed'
        if args.proofs:
            status['proofs']='running';run([sys.executable,'proofs/check_proofs.py','--out',str(evidence/'proofs.json')],'symbolic_proofs');status['proofs']='passed'
        def executable(name):
            choices=[build/(name+'.exe'),build/'Release'/(name+'.exe')] if sys.platform=='win32' else [build/name]
            return next(x for x in choices if x.is_file())
        exe=executable('atomos_cuda' if args.gpu else 'atomos_cpu')
        if args.gpu:
            status['device']=json.loads(run([str(exe),'--probe','--device',str(args.device)],'device_probe'))
        digests={}
        for rows,angles in ((1,1),(17,257),(128,1024)):
            for mode in ('provided','recurrent','shift-xor','shift-or'):
                for fringe in ('off','on'):
                    for layout in ('linear','morton8'):
                        for read in (('texture','texture-packed','global') if args.gpu else ('texture',)):
                            label=f'{rows}_{angles}_{mode}_{fringe}_{layout}_{read}';out=evidence/label
                            cmd=[str(exe),'--rows',str(rows),'--angles',str(angles),'--epochs','3','--mode',mode,'--fringe',fringe,'--layout',layout,'--read',read,'--out',str(out),'--device',str(args.device)]
                            run(cmd,label);verified=verify_run(out,expected_backend='cuda' if args.gpu else 'cpu',expected_read=read if args.gpu else 'host',expected_device=status.get('device'))
                            if verified['invariant_counts'][1]!=0:raise ValueError('fixed proof fixture has a failed invariant comparison')
                            key=(rows,angles,mode,fringe);digest=verified['integer_semantic_sha256']
                            if key in digests and digests[key]!=digest:raise ValueError('cross-layout/read integer digest differs')
                            digests[key]=digest
                            seal_run(out,['atomOS:synthetic:K1'])
                            if not verify_seal(out):raise ValueError('new seal verification failed')
                            status['runs'].append({'path':label,**verified});save()
        if args.gpu:status['gpu']='passed'
        if args.sanitizer:
            status['gpu_memcheck']='running'
            for layout in ('linear','morton8'):
                for read in ('texture','texture-packed','global'):
                    label=f'memcheck_{layout}_{read}';out=evidence/label
                    run([str(sanitizer),'--tool','memcheck','--error-exitcode','2',str(exe),'--rows','17','--angles','257','--epochs','3','--mode','shift-or','--fringe','on','--layout',layout,'--read',read,'--device',str(args.device),'--out',str(out)],label)
                    verified=verify_run(out,expected_backend='cuda',expected_read=read,expected_device=status['device']);status['runs'].append({'path':label,**verified})
            status['gpu_memcheck']='passed'
        status['status']='passed';save();print(f"PASS: {len(status['runs'])} independently verified runs. Evidence: {evidence}");return 0
    except (OSError,RuntimeError,ValueError,KeyError,TypeError,StopIteration) as exc:
        status['status']='failed';status['reason']=str(exc);save();print('FAIL:',exc,file=sys.stderr);print('Evidence:',evidence);return 1
if __name__=='__main__':raise SystemExit(main())
