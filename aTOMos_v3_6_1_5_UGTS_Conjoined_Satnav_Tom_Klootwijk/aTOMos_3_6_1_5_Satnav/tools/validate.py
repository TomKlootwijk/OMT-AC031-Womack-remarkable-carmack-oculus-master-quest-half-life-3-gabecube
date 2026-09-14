#!/usr/bin/env python3
"""Build/test the local package; optionally compile and execute both CUDA paths."""
from pathlib import Path
import argparse,datetime,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from verify_result import verify
from compare_backends import compare

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--memcheck',action='store_true');p.add_argument('--cpu-sanitizers',action='store_true');a=p.parse_args()
    out=ROOT/'results'/('review_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'));out.mkdir(parents=True)
    if a.gpu and not shutil.which('nvcc'):
        record={'cuda_compile':'not_run','cuda_execute':'not_run','reason':'nvcc not found','out':str(out)};(out/'status.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record));return 3
    if a.memcheck and (not a.gpu or not shutil.which('compute-sanitizer')):raise ValueError('--memcheck requires --gpu and compute-sanitizer')
    build=ROOT/('build_gpu' if a.gpu else 'build_cpu')
    def run(command,name):
        r=subprocess.run([str(x) for x in command],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (out/(name+'.txt')).write_text(r.stdout);print(r.stdout,end='');r.check_returncode()
    run(['cmake','-S','.', '-B',build,'-DCMAKE_BUILD_TYPE=Release','-DAO_ENABLE_CUDA='+('ON'if a.gpu else 'OFF'),'-DAO_SANITIZE='+('ON'if a.cpu_sanitizers else 'OFF')],'configure')
    run(['cmake','--build',build,'--config','Release','--parallel','2'],'build')
    run(['ctest','--test-dir',build,'-C','Release','--output-on-failure'],'ctest')
    exe=next((q for q in [build/'atomos_satnav',build/'atomos_satnav.exe',build/'Release/atomos_satnav.exe'] if q.is_file()),None)
    if exe is None:raise FileNotFoundError('built executable not found')
    run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_python.py','-v'],'python_tests')
    reports=[]
    if a.gpu:run([exe,'--probe'],'device')
    for name in ['clean','noisy_edges']:
        data=ROOT/'examples'/name;cpu=out/(name+'_cpu.csv')
        args=[exe,'--epochs',data/'epochs.csv','--observations',data/'observations.csv']
        run(args+['--out',cpu],name+'_cpu');reports.append(verify(data,cpu))
        if a.gpu:
            for mode in ['global','texture']:
                for chunk in [1,7,8192]:
                    dst=out/f'{name}_{mode}_{chunk}.csv';run(args+['--backend','cuda','--read',mode,'--chunk',chunk,'--out',dst],dst.stem)
                    reports.append(verify(data,dst));reports.append(compare(cpu,dst))
    if a.memcheck:
        data=ROOT/'examples/clean';run(['compute-sanitizer','--tool','memcheck','--error-exitcode','9',exe,'--epochs',data/'epochs.csv','--observations',data/'observations.csv','--backend','cuda','--read','texture','--chunk','7','--out',out/'memcheck.csv'],'memcheck')
    summary={'status':'passed','cuda_compile':'passed'if a.gpu else 'not_requested','cuda_execute':'passed'if a.gpu else 'not_requested','memcheck':'passed'if a.memcheck else 'not_requested','reports':reports}
    (out/'status.json').write_text(json.dumps(summary,indent=2)+'\n');print('Report:',out/'status.json');return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,subprocess.CalledProcessError,AssertionError)as e:print('REVIEW ERROR:',e,file=sys.stderr);raise SystemExit(1)
