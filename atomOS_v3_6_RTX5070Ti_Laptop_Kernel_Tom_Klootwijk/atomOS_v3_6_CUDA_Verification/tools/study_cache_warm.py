"""Measure explicit in-kernel warmup and its traffic without calling it pinning."""
import argparse,hashlib,json,math,random,statistics,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from profile_cache import parse_metrics,resolve_ncu,read_log
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from reference import verify_execution_metadata
MODES=('none','prefetch','load','ca','texture-control','cooperative-texture-control')
METRICS=('l1tex__t_requests_pipe_tex_mem_texture_op_ld.sum',
 'l1tex__t_sectors_pipe_tex_mem_texture_op_ld.sum',
 'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_hit.sum',
 'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_miss.sum',
 'l1tex__t_sectors_pipe_lsu_mem_global_op_ld.sum',
 'l1tex__t_sectors_pipe_lsu_mem_global_op_ld_lookup_miss.sum',
 'dram__bytes_read.sum','gpu__time_duration.sum')
SOURCES=('experiments/cache_warm.cu','cuda/kernel.cu','include/atomos/host.hpp','include/atomos/core.hpp')

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def source_hashes():return {name:digest(ROOT/name) for name in SOURCES}
def exact_record(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
def context(mode,rows=128,angles=1024,block=128,epochs=3):
 return dict(mode=mode,rows=rows,angles=angles,block=block,epochs=epochs,layout='linear')
def kernel_args(exe,c):
 return [str(exe),'--warm',c['mode'],'--rows',str(c['rows']),'--angles',str(c['angles']),'--block-size',str(c['block']),'--epochs',str(c['epochs']),'--layout',c['layout']]

def validate_result(result,c,expected_device=None):
 if not isinstance(result,dict) or result.get('status')!='passed' or result.get('scope')!='experimental_warming_included_in_each_epoch':raise ValueError('invalid application conformance status/scope')
 fields=('rows','angles','epochs','block_size','warm_mode','verified_lane_epochs','warm_disagreements')
 if any(type(result.get(key)) is not int for key in fields):raise ValueError('integer experiment metadata required')
 expected={'rows':c['rows'],'angles':c['angles'],'epochs':c['epochs'],'block_size':c['block'],'warm_mode':MODES.index(c['mode']),
  'verified_lane_epochs':c['rows']*((c['angles']+31)//32)*c['epochs'],'warm_disagreements':0,'layout':c['layout']}
 if any(result.get(key)!=value for key,value in expected.items()):raise ValueError('application mode/dimensions/epochs/block/layout/verified count or warm disagreement differs')
 if not (1<=result['rows']<=65536 and 1<=result['angles']<=65536 and 1<=result['epochs']<=16 and result['block_size'] in (64,128,256)):raise ValueError('experiment metadata bounds')
 if result['verified_lane_epochs']>2**20:raise ValueError('experiment lane-epoch cap')
 times=result.get('compute_ms')
 if not isinstance(times,list) or len(times)!=c['epochs'] or any(type(value) not in (int,float) or not math.isfinite(value) or value<0 for value in times):raise ValueError('invalid epoch timings')
 verify_execution_metadata(dict(backend='cuda',read='texture-packed',device=result.get('device'),candidate_verification='passed'),expected_device=expected_device)
 return result

def application_results(raw,c,allow_replay=False,expected_device=None):
 """Validate every complete application JSON object, including replay receipts."""
 decoder=json.JSONDecoder();results=[];position=0;device=expected_device
 while True:
  start=raw.find('{',position)
  if start<0:break
  try:result,length=decoder.raw_decode(raw[start:])
  except json.JSONDecodeError as exc:raise ValueError('malformed application JSON in stdout') from exc
  validate_result(result,c,device)
  if device is None:device=result['device']
  results.append(result);position=start+length
 if not results or (not allow_replay and len(results)!=1):raise ValueError('missing or unexpected duplicate application result')
 return results

def aggregates(report):
 result=[]
 for mode in MODES:
  times=[r['median_ms'] for r in report['timings'] if r['mode']==mode]
  profiles=[r for r in report['profiles'] if r['mode']==mode]
  if len(times)!=5 or len(profiles)!=3:raise ValueError('incomplete per-mode repetitions')
  for name in METRICS:
   if len({r['metrics'][name]['unit'] for r in profiles})!=1:raise ValueError('inconsistent metric units')
  result.append({'mode':mode,'median_ms':statistics.median(times),'min_ms':min(times),'max_ms':max(times),
   'metrics':{name:{'min':min(r['metrics'][name]['value'] for r in profiles),'median':statistics.median(r['metrics'][name]['value'] for r in profiles),'max':max(r['metrics'][name]['value'] for r in profiles),'unit':profiles[0]['metrics'][name]['unit']} for name in METRICS}})
 return result

def retained_path(out,name):
 if not isinstance(name,str):raise ValueError('invalid retained log name')
 path=(out/name).resolve()
 if not path.is_relative_to(out) or not path.is_file():raise ValueError('missing or out-of-directory retained log')
 return path

def audit_raw(report,out,exe):
 """Reconstruct saved receipts and metrics without executing the application."""
 if report.get('status')!='passed' or report.get('modes')!=list(MODES):raise ValueError('study status/mode list differs')
 if Path(report['executable']).resolve()!=exe:raise ValueError('recorded executable path differs')
 specifications={}
 for mode in MODES:
  for rows,angles in ((1,1),(17,257)):specifications[f'conformance_{mode}_{rows}_{angles}']=('conformance',context(mode,rows,angles),None)
  for trial in range(5):specifications[f'time_{trial}_{mode}']=('timing',context(mode),trial)
  for trial in range(3):specifications[f'cold_{mode}_{trial}']=('profile',context(mode,epochs=1),trial)
 if len(report.get('commands',[]))!=len(specifications):raise ValueError('study command count differs')
 commands={}
 for command in report['commands']:
  stdout=command.get('stdout','')
  if not stdout.endswith('.stdout.log'):raise ValueError('unexpected stdout log name')
  label=stdout[:-len('.stdout.log')]
  if label not in specifications or label in commands or type(command.get('exit_code')) is not int or command['exit_code']!=0:raise ValueError('duplicate/unexpected/failed retained command')
  commands[label]=command
 if set(commands)!=set(specifications):raise ValueError('missing retained command')
 actual_conformance=[];actual_timings=[];actual_profiles=[];receipt_counts={};device=None
 for label,(kind,c,trial) in specifications.items():
  command=commands[label];argv=command['command'];expected_args=kernel_args(exe,c)
  if not isinstance(argv,list) or any(not isinstance(v,str) for v in argv):raise ValueError('invalid command argv')
  if kind=='profile':
   csv_path=retained_path(out,label+'.csv.log')
   expected_prefix=['--replay-mode','kernel','--cache-control','all','--clock-control','none','--launch-skip','1','--launch-count','1','--check-exit-code','1','--metrics',','.join(METRICS),'--csv','--page','raw','--print-units','base','--log-file',str(csv_path)]
   if argv[1:]!=expected_prefix+expected_args:raise ValueError('profiling command/replay/metrics context differs')
  elif argv!=expected_args:raise ValueError('application command differs from study context')
  retained_path(out,command['stderr'])
  receipts=application_results(read_log(retained_path(out,command['stdout'])),c,kind=='profile',device)
  if device is None:device=receipts[0]['device']
  receipt_counts[label]=len(receipts)
  if kind=='conformance':actual_conformance.append(receipts[0])
  elif kind=='timing':actual_timings.append({'mode':c['mode'],'trial':trial,'summary':receipts[0],'median_ms':statistics.median(receipts[0]['compute_ms'])})
  else:
   metrics=parse_metrics(read_log(csv_path),METRICS)
   if any(metric['status']!='collected' for metric in metrics.values()):raise ValueError('required retained counter missing')
   actual_profiles.append({'mode':c['mode'],'trial':trial,'metrics':metrics,'csv':csv_path.name,'application_results':receipts})
 def compare_unique(recorded,actual,key,fields):
  if not isinstance(recorded,list) or len(recorded)!=len(actual):raise ValueError('saved result count differs from raw logs')
  actual_map={key(row):row for row in actual};seen=set()
  for row in recorded:
   identity=key(row)
   if identity in seen or identity not in actual_map:raise ValueError('duplicate/unexpected saved result')
   seen.add(identity)
   if any(not exact_record(row.get(field),actual_map[identity].get(field)) for field in fields):raise ValueError('saved result differs from raw stdout/CSV')
   if 'application_results' in row and not exact_record(row['application_results'],actual_map[identity].get('application_results')):raise ValueError('saved profiler receipts differ from actual stdout')
 compare_unique(report.get('conformance'),actual_conformance,lambda r:(r['warm_mode'],r['rows'],r['angles']),tuple(actual_conformance[0]))
 compare_unique(report.get('timings'),actual_timings,lambda r:(r['mode'],r['trial']),('summary','median_ms'))
 compare_unique(report.get('profiles'),actual_profiles,lambda r:(r['mode'],r['trial']),('metrics','csv'))
 if not exact_record(report.get('aggregates'),aggregates(report)):raise ValueError('saved aggregates differ from reconstructed repetitions')
 return {'commands_checked':len(commands),'conformance_runs':len(actual_conformance),'timing_runs':len(actual_timings),'profile_runs':len(actual_profiles),
  'application_json_receipts':sum(receipt_counts.values()),'profile_receipts_per_command':{name:count for name,count in receipt_counts.items() if name.startswith('cold_')},'device':device}

def audit_existing(exe,out):
 audit={'schema':'atomOS-cache-warm-post-run-audit','status':'running','audit_time_utc':datetime.now(timezone.utc).isoformat(),
  'scope':'Read-only validation of existing study evidence; no GPU or profiler execution; original study.json remains unchanged.',
  'study':str(out/'study.json'),'executable':str(exe),
  'source_evidence_boundary':'Transitive source hashes collected now are audit-time snapshots. They do not establish that these dependencies were recorded before the original run.'}
 destination=out/('study_audit_'+str(time.time_ns())+'.json')
 try:
  report=json.loads((out/'study.json').read_text(encoding='utf-8'));audit['study_sha256']=digest(out/'study.json')
  before=digest(exe);sources=source_hashes();audit.update(executable_sha256_at_audit=before,transitive_source_sha256_at_audit=sources)
  if before!=report.get('executable_sha256'):raise ValueError('current executable hash differs from saved pre-run hash')
  if sources[SOURCES[0]]!=report.get('source_sha256'):raise ValueError('current experiment source differs from original recorded source hash')
  audit.update(original_executable_hash_matches=True,original_experiment_source_hash_matches=True)
  if 'source_hashes_before' in report:
   if report['source_hashes_before']!=sources or report.get('source_hashes_after')!=sources:raise ValueError('transitive source hashes differ from new-run retained snapshots')
   audit['original_transitive_source_hashes']='recorded_and_matching'
  else:audit['original_transitive_source_hashes']='not_recorded; audit-time snapshot only'
  if 'executable_sha256_after' in report and report['executable_sha256_after']!=before:raise ValueError('saved post-run executable hash differs')
  audit['raw_log_validation']=audit_raw(report,out,exe)
  if digest(exe)!=before or source_hashes()!=sources or digest(out/'study.json')!=audit['study_sha256']:raise ValueError('executable/source/study changed during audit')
  audit.update(status='passed',executable_unchanged_during_audit=True,sources_unchanged_during_audit=True)
 except (OSError,RuntimeError,ValueError,KeyError,TypeError) as exc:audit.update(status='failed',reason=str(exc))
 destination.write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n',encoding='utf-8');print(destination)
 return 0 if audit['status']=='passed' else 1
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--exe',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--audit-existing',action='store_true',help='Validate retained raw logs and current hashes; write a separate post-run audit without GPU execution');a=p.parse_args()
 exe=a.exe.resolve();out=a.out.resolve()
 if a.audit_existing:
  if not (out/'study.json').is_file():p.error('existing study.json required')
  return audit_existing(exe,out)
 out.mkdir(parents=True,exist_ok=False)
 hashes_before=source_hashes()
 report={'status':'running','scope':'in-kernel cache-warming experiment; all warmup costs included; no cache-pinning claim',
  'executable':str(exe),'executable_sha256':digest(exe),
  'source_sha256':hashes_before[SOURCES[0]],'source_hashes_before':hashes_before,
  'source_hash_scope':'Pre/post-run hashes of experiment and its local CUDA/host/core dependencies; not a compiler correctness proof.',
  'modes':list(MODES),'commands':[],'timings':[],'profiles':[],'conformance':[]}
 def save():(out/'study.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 def run(cmd,label):
  stdout=out/(label+'.stdout.log');stderr=out/(label+'.stderr.log');rec={'command':cmd,'stdout':stdout.name,'stderr':stderr.name};report['commands'].append(rec);save()
  with stdout.open('w',encoding='utf-8') as o,stderr.open('w',encoding='utf-8') as e:r=subprocess.run(cmd,stdout=o,stderr=e,cwd=ROOT,timeout=120)
  rec['exit_code']=r.returncode;save()
  if r.returncode:raise RuntimeError(f'{label} failed with exit {r.returncode}')
  return stdout.read_text(encoding='utf-8')
 def args(mode,rows=128,angles=1024,block=128,epochs=3):return kernel_args(exe,context(mode,rows,angles,block,epochs))
 try:
  # All modes use the same actual recurrent/fringe-on K1 equation; candidates
  # are validated and committed on the host after every epoch.
  for mode in MODES:
   for rows,angles in ((1,1),(17,257)):
    result=application_results(run(args(mode,rows,angles),f'conformance_{mode}_{rows}_{angles}'),context(mode,rows,angles))[0]
    report['conformance'].append(result);save()
  for trial in range(5):
   order=list(MODES);random.Random(20260913+trial).shuffle(order)
   for mode in order:
    result=application_results(run(args(mode),f'time_{trial}_{mode}'),context(mode))[0];times=result['compute_ms']
    report['timings'].append({'mode':mode,'trial':trial,'summary':result,'median_ms':statistics.median(times)});save()
  ncu=resolve_ncu(None)
  if ncu is None:raise RuntimeError('native Nsight unavailable')
  for mode in MODES:
   for trial in range(3):
    label=f'cold_{mode}_{trial}';csv=out/(label+'.csv.log')
    cmd=[str(ncu),'--replay-mode','kernel','--cache-control','all','--clock-control','none','--launch-skip','1','--launch-count','1','--check-exit-code','1','--metrics',','.join(METRICS),'--csv','--page','raw','--print-units','base','--log-file',str(csv),*args(mode,epochs=1)]
    receipts=application_results(run(cmd,label),context(mode,epochs=1),allow_replay=True);metrics=parse_metrics(read_log(csv),METRICS)
    if any(x['status']!='collected' for x in metrics.values()):raise ValueError('required counter missing')
    report['profiles'].append({'mode':mode,'trial':trial,'metrics':metrics,'csv':csv.name,'application_results':receipts});save()
  report['aggregates']=aggregates(report)
  report['executable_sha256_after']=digest(exe);report['source_hashes_after']=source_hashes()
  if report['executable_sha256_after']!=report['executable_sha256'] or report['source_hashes_after']!=hashes_before:raise ValueError('executable or GPU source changed during study')
  report['status']='passed';report['raw_log_validation']=audit_raw(report,out,exe)
  if digest(exe)!=report['executable_sha256'] or source_hashes()!=hashes_before:raise ValueError('executable or GPU source changed during final verification')
  save();print(out/'study.json');return 0
 except (OSError,RuntimeError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
  report.update(status='failed',reason=str(exc));save();print(exc,file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
