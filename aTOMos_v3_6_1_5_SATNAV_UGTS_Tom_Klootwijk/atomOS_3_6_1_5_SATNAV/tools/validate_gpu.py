#!/usr/bin/env python3
"""Build on the requested laptop, compare both device fetch paths and run memcheck."""
from pathlib import Path
import argparse,datetime,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--sanitizer',action='store_true');p.add_argument('--device',type=int,default=0);a=p.parse_args()
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f');report=ROOT/'results'/('gpu_'+stamp);report.mkdir()
    if not shutil.which('nvcc'):
        status={'cuda_compile':'not_run','cuda_execution':'not_run','reason':'nvcc not found on PATH'}
        (report/'status.json').write_text(json.dumps(status,indent=2)+'\n');print(status);return 3
    build=ROOT/'build_gpu'
    def call(args,name):
        with (report/(name+'.log')).open('w')as f:subprocess.run(list(map(str,args)),cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
    try:
        call(['cmake','-S',ROOT,'-B',build,'-DSATNAV_ENABLE_CUDA=ON','-DCMAKE_BUILD_TYPE=Release'],'configure')
        call(['cmake','--build',build,'--config','Release','--parallel','2'],'build')
        call(['ctest','--test-dir',build,'-C','Release','--output-on-failure'],'ctest')
        exe=build/('satnav.exe' if sys.platform=='win32'else 'satnav')
        if not exe.exists():exe=build/'Release'/'satnav.exe'
        call([exe,'--probe','--device',a.device],'probe')
        for mode in ['texture','global']:
            folder=report/mode
            call([exe,'--input',ROOT/'examples/demo','--out',folder,'--backend','cuda','--read',mode,'--verify','--device',a.device],mode)
            call([sys.executable,ROOT/'tools/verify_run.py','--input',ROOT/'examples/demo','--run',folder],mode+'_independent')
        if a.sanitizer:
            tool=shutil.which('compute-sanitizer')
            if tool is None:
                (report/'status.json').write_text(json.dumps({'cuda_compile':'passed','cuda_execution':'passed','memcheck':'not_run','reason':'compute-sanitizer missing'},indent=2)+'\n');return 3
            for mode in ['texture','global']:
                call([tool,'--tool','memcheck','--error-exitcode','99',exe,'--input',ROOT/'examples/demo','--out',report/('memcheck_'+mode),'--backend','cuda','--read',mode,'--device',a.device],mode+'_memcheck')
        (report/'status.json').write_text(json.dumps({'cuda_compile':'passed','cuda_execution':'passed','independent_comparison':'passed','memcheck':'passed'if a.sanitizer else 'not_requested'},indent=2)+'\n')
        print(report);return 0
    except subprocess.CalledProcessError as exc:
        (report/'status.json').write_text(json.dumps({'status':'failed','command':list(map(str,exc.cmd)),'returncode':exc.returncode},indent=2)+'\n');print(report,file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
