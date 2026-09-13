"""Retain cold native counters and ordinary timings for the SDF/NOR kernel."""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys, time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from sdf_nor_reference import verify_export
from profile_cache import METRICS,parse_metrics,read_log,resolve_ncu

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--exe',type=Path,required=True);p.add_argument('--atlas',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True);args=p.parse_args()
 out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
 ncu=resolve_ncu(None)
 if ncu is None: raise RuntimeError('native Nsight Compute unavailable')
 exe=args.exe.resolve();atlas=args.atlas.resolve();program=ROOT/'examples/universal/bounded_oscillator.atomos'
 report=dict(status='running',schema='atomOS-sdf-nor-cache-study-v1',executable=str(exe),executable_sha256=sha(exe),atlas=str(atlas),atlas_sha256=sha(atlas),program_sha256=sha(program),profiler=str(ncu),runs=[])
 sources=['tools/profile_sdf_nor.py','tools/profile_cache.py','python/sdf_nor_reference.py','experiments/sdf_universal.cu','include/atomos/sdf_nor.hpp','include/atomos/universal.hpp']
 report['source_hashes']={f:sha(ROOT/f) for f in sources}
 def save(): (out/'study.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 save()
 try:
  for layout in ('linear','morton8'):
   for kind in ('ordinary','cold'):
    for trial in range(2):
     label=f'{kind}_{layout}_{trial}';folder=out/label
     cmd=[exe,'--program',program,'--atlas',atlas,'--steps',256,'--origin',0,'--cells',2,'--layout',layout,'--out',folder]
     raw=out/(label+'.csv.log')
     if kind=='cold': cmd=[ncu,'--replay-mode','kernel','--cache-control','all','--clock-control','none','--launch-count',1,'--check-exit-code',1,'--metrics',','.join(METRICS),'--csv','--page','raw','--print-units','base','--log-file',raw,*cmd]
     cmd=list(map(str,cmd));print(label,flush=True);started=time.perf_counter()
     with (out/(label+'.stdout.log')).open('w',encoding='utf-8') as stdout,(out/(label+'.stderr.log')).open('w',encoding='utf-8') as stderr:
      done=subprocess.run(cmd,cwd=ROOT,stdout=stdout,stderr=stderr)
     rec=dict(label=label,kind=kind,layout=layout,trial=trial,command=cmd,exit_code=done.returncode,wall_seconds=time.perf_counter()-started)
     report['runs'].append(rec);save()
     if done.returncode: raise RuntimeError(label+' native execution failed')
     rec['verification']=verify_export(folder)
     receipt=json.loads((folder/'summary.json').read_text(encoding='utf-8'));rec['receipt']=receipt
     if kind=='cold':
      metrics=parse_metrics(read_log(raw),METRICS)
      if any(v.get('status')!='collected' for v in metrics.values()): raise ValueError('missing native counters')
      sectors=metrics[METRICS[1]]['value'];hits=metrics[METRICS[2]]['value'];misses=metrics[METRICS[3]]['value']
      floor=receipt['atlas_texture_bytes']//32
      if hits+misses!=sectors or misses<floor: raise ValueError('counter conservation/floor mismatch')
      rec.update(metrics=metrics,compulsory_miss_floor=floor,extra_misses=misses-floor,at_compulsory_floor=misses==floor,whole_run_hit_percent=100*hits/sectors)
     save()
  if sha(exe)!=report['executable_sha256'] or {f:sha(ROOT/f) for f in sources}!=report['source_hashes']: raise ValueError('code changed during study')
  report['status']='passed'
 except Exception as exc:
  report.update(status='failed',reason=str(exc));save();raise
 save();print(json.dumps(dict(status=report['status'],runs=len(report['runs']),study=str(out/'study.json'))))
if __name__=='__main__': main()
