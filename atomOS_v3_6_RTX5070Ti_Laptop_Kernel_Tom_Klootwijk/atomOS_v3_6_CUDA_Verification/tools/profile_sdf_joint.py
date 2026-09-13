"""Cold whole-launch retention and ordinary timing for the connected SDF profile."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from sdf_joint_reference import verify_export
from profile_cache import METRICS,parse_metrics,read_log,resolve_ncu
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('exe','atlas','out'):p.add_argument('--'+key,type=Path,required=True)
 args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
 exe=args.exe.resolve();atlas=args.atlas.resolve();program=ROOT/'examples/universal/binary_increment.atomos';ncu=resolve_ncu(None)
 if ncu is None:raise RuntimeError('native Nsight Compute unavailable')
 sources=['tools/profile_sdf_joint.py','tools/profile_cache.py','python/sdf_joint_reference.py','python/sdf_nor_reference.py','python/sdf_lineage_reference.py','experiments/sdf_joint.cu','experiments/sdf_universal.cu','include/atomos/sdf_nor.hpp','include/atomos/sdf_lineage.hpp','include/atomos/universal.hpp']
 report=dict(schema='atomOS-sdf-joint-cache-study-v1',status='running',executable=str(exe),executable_sha256=sha(exe),atlas=str(atlas),atlas_sha256=sha(atlas),program_sha256=sha(program),profiler=str(ncu),source_hashes={f:sha(ROOT/f) for f in sources},runs=[])
 def save():(out/'study.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 save()
 try:
  for layout in ('linear','morton8'):
   for kind in ('ordinary','cold'):
    for trial in range(2):
     label=f'{kind}_{layout}_{trial}';folder=out/label;raw=out/(label+'.csv.log')
     cmd=[exe,'--program',program,'--atlas',atlas,'--steps',6,'--max-frontier',128,'--origin',-11,'--cells',37,'--layout',layout,'--q',0,'--j',1,'--k',1,'--out',folder]
     if kind=='cold':cmd=[ncu,'--replay-mode','kernel','--cache-control','all','--clock-control','none','--launch-count',1,'--check-exit-code',1,'--metrics',','.join(METRICS),'--csv','--page','raw','--print-units','base','--log-file',raw,*cmd]
     cmd=list(map(str,cmd));print(label,flush=True);started=time.perf_counter()
     with (out/(label+'.stdout.log')).open('w',encoding='utf-8') as stdout,(out/(label+'.stderr.log')).open('w',encoding='utf-8') as stderr:done=subprocess.run(cmd,cwd=ROOT,stdout=stdout,stderr=stderr)
     rec=dict(label=label,kind=kind,layout=layout,trial=trial,command=cmd,exit_code=done.returncode,wall_seconds=time.perf_counter()-started);report['runs'].append(rec);save()
     if done.returncode:raise RuntimeError(label+' execution failed')
     expected=dict(layout=layout,budget=6,origin=-11,cells=37,max_frontier=128,
       phi_base=int.from_bytes(atlas.read_bytes()[12:16],'little'),q_initial=0,j=1,k=1,
       diagnostic_profile='source',injection='none',interval=1,seed_id=1,seed_live=1,
       seed_row=0,seed_angle=0,program=program.read_text(encoding='utf-8'))
     rec['verification']=verify_export(folder,expected=expected)
     receipt=json.loads((folder/'summary.json').read_text(encoding='utf-8'));rec['receipt']=receipt
     if sha(folder/'operators.atlas')!=sha(atlas):raise ValueError('runtime atlas copy differs')
     receipts=[json.loads(line) for line in (out/(label+'.stdout.log')).read_text(encoding='utf-8').splitlines() if line.startswith('{')]
     if receipts!=[receipt]:raise ValueError('native stdout differs from export receipt')
     if kind=='cold':
      metrics=parse_metrics(read_log(raw),METRICS)
      if any(v.get('status')!='collected' for v in metrics.values()):raise ValueError('missing native counters')
      sectors=metrics[METRICS[1]]['value'];hits=metrics[METRICS[2]]['value'];misses=metrics[METRICS[3]]['value'];floor=receipt['atlas_texture_bytes']//32
      if hits+misses!=sectors or misses<floor:raise ValueError('counter conservation/floor mismatch')
      rec.update(metrics=metrics,compulsory_miss_floor=floor,extra_misses=misses-floor,at_compulsory_floor=misses==floor,whole_run_hit_percent=100*hits/sectors)
     save()
  if sha(exe)!=report['executable_sha256'] or {f:sha(ROOT/f) for f in sources}!=report['source_hashes']:raise ValueError('code changed during study')
  report['status']='passed'
 except Exception as exc:report.update(status='failed',reason=str(exc));save();raise
 save();print(json.dumps(dict(status=report['status'],runs=len(report['runs']),study=str(out/'study.json'))))
if __name__=='__main__':main()
