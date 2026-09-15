"""Run the persistent CUDA worker under Compute Sanitizer on real prepared input."""
from pathlib import Path
import argparse,json,shutil,subprocess,sys,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from reference import load,solve

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    sanitizer=shutil.which('compute-sanitizer')
    if not sanitizer:raise RuntimeError('compute-sanitizer unavailable')
    a.out.mkdir(parents=True,exist_ok=False);epochs=load(a.input);lines=[]
    for e in epochs:
        fields=['SOLVE',str(e['id']),repr(e['time']),*[repr(x) for x in e['seed']],str(e['asa']),str(e['na']),str(e['boundary']),str(len(e['observations']))]
        for channel,o in e['observations'].items():fields.extend([str(channel),*[repr(x) for x in o['sat']],repr(o['corrected']),'0',repr(o['sigma']),str(int(o['ready']))])
        lines.append(' '.join(fields))
    text='\n'.join(lines+['QUIT'])+'\n';(a.out/'requests.txt').write_text(text)
    command=[sanitizer,'--tool','memcheck','--error-exitcode','99','--log-file',str((a.out/'memcheck.log').resolve()),str(a.binary.resolve()),'--backend','cuda']
    run=subprocess.run(command,input=text,text=True,capture_output=True,timeout=180)
    (a.out/'stdout.jsonl').write_text(run.stdout);(a.out/'stderr.txt').write_text(run.stderr)
    if run.returncode:raise RuntimeError('sanitized worker failed '+str(run.returncode))
    rows=[json.loads(line) for line in run.stdout.splitlines()];solutions=[r for r in rows if r['type']=='solution']
    assert len(solutions)==len(epochs)
    maxerr=0.;comparisons=0
    for e,row in zip(epochs,solutions):
        ref=solve(e)
        assert row['epoch_id']==e['id'] and row['status']==ref['status'];comparisons+=2
        if ref['status']=='CONVERGED':
            for x,y in zip(row['state'],ref['state']):maxerr=max(maxerr,abs(x-y));assert abs(x-y)<1e-4;comparisons+=1
    log=(a.out/'memcheck.log').read_text();assert 'ERROR SUMMARY: 0 errors' in log
    report=dict(status='passed',epochs=len(epochs),comparisons=comparisons,max_state_component_difference_m=maxerr,
        command=command,return_code=run.returncode,memcheck='zero_errors',
        worker_sha256=hashlib.sha256(a.binary.read_bytes()).hexdigest(),scope='One persistent CUDA worker; real final-pass GPS inputs; independent Householder position/clock comparison')
    (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
