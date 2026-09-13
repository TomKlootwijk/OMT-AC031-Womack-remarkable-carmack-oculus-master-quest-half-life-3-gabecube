"""Finalize actual continuation evidence without replacing baseline validation."""
from pathlib import Path
import hashlib,json,shutil
from profile_cache import parse_metrics,read_log
ROOT=Path(__file__).resolve().parents[1]; E=ROOT/'results/residency_continuation'; CACHE=Path('C:/Users/Tom/.cache/ak1')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,d):p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 exe=CACHE/'gpu128/Release/atomos_cache_partition.exe'; h=sha(exe)
 studies=[];m='l1tex__t_sectors_pipe_tex_mem_texture_op_ld'
 for name in ('partition_grid_cg','partition_grid_noalloc'):
  p=CACHE/name/'study.json';s=read(p)
  assert s['status']=='passed' and s['raw_log_validation']['status']=='passed' and len(s['commands'])==40
  assert s['executable_sha256']==s['executable_sha256_after']==h
  a=[]
  for x in s['aggregates']:
   ms=x['metrics'];floor=2048 if x['size']=='default' else 131072
   a.append(dict(size=x['size'],layout=x['layout'],sectors=ms[m+'.sum']['median'],misses=ms[m+'_lookup_miss.sum']['median'],
     misses_min=ms[m+'_lookup_miss.sum']['min'],misses_max=ms[m+'_lookup_miss.sum']['max'],compulsory_misses=floor,
     all_repeats_at_compulsory_floor=ms[m+'_lookup_miss.sum']['min']==ms[m+'_lookup_miss.sum']['max']==floor,
     median_ms=x['median_ms'],min_ms=x['min_ms'],max_ms=x['max_ms']))
  studies.append(dict(path=str(p),sha256=sha(p),barrier=s['selection']['barrier'],io=s['selection']['io'],
   label=s['selection']['barrier']+' / '+('CG' if s['selection']['io']=='cg' else 'NA'),aggregates=a,audit=s['raw_log_validation']))
 san=read(E/'partition_sanitizers.json');native=read(E/'final_native_findings.json')
 assert san['status']=='passed' and len(san['runs'])==10 and san['executable_sha256']==h
 assert native['status']=='passed' and native['executable_sha256']==h
 warm=read(CACHE/'warm_study/study.json');assert warm['status']=='passed'
 assert all(a['all_repeats_at_compulsory_floor'] for s in studies for a in s['aggregates'] if a['size']=='default' and a['layout']=='linear')
 assert not any(a['all_repeats_at_compulsory_floor'] for s in studies for a in s['aggregates'] if a['size']=='max' or a['layout']=='morton8')
 summary=dict(schema='atomOS-residency-continuation-1',date='2026-09-13',status='execution_validated_residency_partial',
  executable=str(exe),executable_sha256=h,partition_studies=studies,partition_sanitizer_path=str(E/'partition_sanitizers.json'),
  native_audit_path=str(E/'final_native_findings.json'),warm_study_path=str(CACHE/'warm_study/study.json'),
  source_and_binary_scope='Final partition studies capture exact source/binary hashes before and after all runs. Earlier exploratory variants are retained separately with archive-time provenance; those hashes were not captured before every quick run.',
  residency_interpretation='The 64 KiB LINEAR dictionary reached exactly 2,048 compulsory misses in all six final profiles across the two I/O policies. Under the cold-start and coverage assumptions, the work and final probe added no observed dictionary misses. This establishes measured retention for that fixture during these launches. The same-size Morton8 cases added 84-264 misses; all 4 MiB cases also failed the cold-miss-floor criterion. Full residency across the supported domain remains unachieved.',
  validation_description='The final binary passed 16 conformance executions covering tiny, padded-tail, default and maximum fixtures under both layouts and both I/O policies. Forty unprofiled timing trials and 24 cold profile samples also passed the host candidate checks and independent receipt/geometry audit. Six memory checks and four synchronization checks reported zero errors; the memory checks include the maximum Morton8 fixture under both policies. These are additional to the production validation on page 2.',
  resource_description='Both sm_120 partition templates use 96 registers per thread, zero local/stack allocation and zero static shared memory. Native disassembly distinguishes STRONG.GPU from NA global accesses. Loop unrolling creates 15 static TLD sites per template; the dynamic phase counts, not that static count, determine traffic. The experiment allocates 754,032 extra bytes for per-thread checksums and SM records, included in memory admission and payload accounting.',
  control_rows=[
   ['Global warming (64 KiB)','L1 prefetch, read-only global loads and cache-all loads left all 2,048 productive texture misses intact.'],
   ['Extra texture read (64 KiB)','Block and cooperative positive controls: 4,096 sectors, 2,048 cold misses. Added traffic is counted; this is deliberate warming.'],
   ['Block vs grid barrier','Removing grid barriers removed extra sector requests but did not remove the larger-case failure.'],
   ['Retain-only (256 KiB)','8,192 compulsory misses and 8,192 hits, with no K1 work or state commit. At 4 MiB this control also exceeded the cold floor.'],
   ['Word-only (256 KiB)','16,384 misses versus an 8,192 cold floor, same as the full epoch. Floating-point diagnostics were omitted; full K1 verification was not run.'],
   ['No-allocation hint (4 MiB)','Linear median misses fell from 383,787 to 291,832; both exceed 131,072. Median event time was 1.134 vs 1.136 ms, so fewer misses did not show a speedup.']
  ],
  causal_interpretation='The 256 KiB word-only counterexample shows that full diagnostic arithmetic is not required for the loss. Removing productive work removed those extra misses. The experiments do not isolate which remaining memory instruction, replacement, bank-traffic or interruption mechanism causes it; neither nominal capacity nor the grid-barrier invalidation instructions alone explain all observations.',
  practical_result='The production fixes and measured 33.1% best-median improvement remain available. The explicit linear partition experiment reaches the residency floor at the default size, with all warming and probing overhead included. It is retained as a reproducible experiment, not promoted as a universal replacement: the larger-domain residency target remains unresolved, and no supported interface used here guarantees pinned texture lines.',
  goal_status_description='Kernel validation, repairs, native-code inspection and the PDF are delivered. The broader complete-residency target remains unresolved; no maximum-domain or across-launch pinning pass is claimed.',
  complete_texture_residency='not_established_for_full_supported_domain',default_linear_measured_retention='compulsory_miss_floor_reached_in_6_of_6_final_profiles',
  warm_sanitizers=[str(x.relative_to(ROOT)) for x in sorted(E.glob('memcheck_*.log'))]+[str(E.relative_to(ROOT)/'synccheck_cooperative.log')])
 write(E/'summary.json',summary)
 (ROOT/'output/bin').mkdir(exist_ok=True);shutil.copy2(exe,ROOT/'output/bin/atomos_cache_partition.exe')
 assert sha(ROOT/'output/bin/atomos_cache_partition.exe')==h
 status=read(ROOT/'results/validation_status.json')
 status['residency_continuation']={'status':summary['status'],'summary':str((E/'summary.json').relative_to(ROOT)),
   'full_epoch_conformance_executions':16,'unprofiled_timing_trials':40,'cold_profile_launches':24,'memchecks':6,'syncchecks':4,
   'default_linear_retention':summary['default_linear_measured_retention'],'maximum_domain_residency':'not_established','cache_pinning':'not_established'}
 status['evidence']['residency_continuation']=str(E/'summary.json');write(ROOT/'results/validation_status.json',status)
 review=read(ROOT/'results/review_20260913/review_summary.json');review['residency_continuation']=str(E/'summary.json');write(ROOT/'results/review_20260913/review_summary.json',review)
 paths=[]
 for folder in ('cuda','experiments','include','src','tools','tests','python','proofs','docs'):
  paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.cu','.hpp','.cpp','.py','.md','.json','.csv','.smt2'))
 paths.extend(ROOT/n for n in ('CMakeLists.txt','AUTHORSHIP.json','README.md','AGENTS.md'))
 write(E/'source_sha256.json',dict(scope='Current unsigned source hashes after continuation; prior review manifest preserved.',files={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sorted(set(paths))}))
 print(E/'summary.json')
if __name__=='__main__':main()
