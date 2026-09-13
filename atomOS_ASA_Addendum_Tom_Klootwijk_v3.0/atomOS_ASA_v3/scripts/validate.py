#!/usr/bin/env python3
"""Build, test and record real tool outcomes. Run from any working directory."""
from __future__ import annotations
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--gpu',action='store_true')
p.add_argument('--sanitizer',action='store_true')
p.add_argument('--build-dir',type=Path)
p.add_argument('--report-dir',type=Path,default=Path('local_validation'))
a=p.parse_args()
report=a.report_dir.resolve();report.mkdir(parents=True,exist_ok=True)
record={'schema':'atomOS.ASA.v3.validation','gpu_requested':a.gpu,'steps':[]}
def done(code:int,reason:str):
    record['status']='pass' if code==0 else ('unavailable' if code==2 else 'fail')
    record['message']=reason
    (report/'status.json').write_text(json.dumps(record,indent=2)+'\n')
    print(reason);raise SystemExit(code)
if not shutil.which('cmake'):done(2,'CMake is not available.')
if a.gpu and not shutil.which('nvcc'):done(2,'CUDA compiler nvcc is not available; GPU build not executed.')
if a.gpu and a.sanitizer and not shutil.which('compute-sanitizer'):
    done(2,'Compute Sanitizer is not available; requested GPU sanitizer checks were not executed.')
build=(a.build_dir or ROOT/('build_gpu' if a.gpu else ('build_sanitize' if a.sanitizer else 'build'))).resolve()
def run(name,cmd):
    cmd=list(map(str,cmd));result=subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (report/(name+'.log')).write_text(result.stdout)
    record['steps'].append({'name':name,'command':cmd,'returncode':result.returncode})
    if result.returncode:done(1,name+' failed; see '+str(report/(name+'.log')))
configure=['cmake','-S',ROOT,'-B',build,'-DCMAKE_BUILD_TYPE=Release']
if a.gpu:configure+=['-DASA_ENABLE_CUDA=ON','-DCMAKE_CUDA_ARCHITECTURES=120-real;120-virtual']
else:configure+=['-DASA_ENABLE_CUDA=OFF','-DASA_SANITIZE='+('ON' if a.sanitizer else 'OFF')]
run('configure',configure)
run('build',['cmake','--build',build,'--config','Release','--parallel','2'])
run('ctest',['ctest','--test-dir',build,'-C','Release','--output-on-failure'])
if a.gpu:
    exe=build/('asa_cuda.exe' if os.name=='nt' else 'asa_cuda')
    if not exe.exists():exe=build/'Release'/'asa_cuda.exe'
    run('device',[exe,'--device-info'])
    if a.sanitizer:
        import tempfile
        for tool in ('memcheck','initcheck','racecheck','synccheck'):
            with tempfile.TemporaryDirectory(prefix='asa_cuda_'+tool+'_') as name:
                run(tool,['compute-sanitizer','--tool',tool,'--error-exitcode','1',exe,'--samples','4097','--out',Path(name)/'run'])
done(0,'All requested build and test stages passed. Reports: '+str(report))
