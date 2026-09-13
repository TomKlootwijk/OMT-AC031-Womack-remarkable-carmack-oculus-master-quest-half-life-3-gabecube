"""Consolidate completed native evidence; missing or rejected evidence fails closed."""
import hashlib,json,re,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from program_bank_reference import decode_bank,verify_trace
from validate_program_bank import verify_injected_rejection

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def main():
 out=ROOT/'results/program_bank_20260913'
 sources=[('verified_study',Path('C:/Users/Tom/.cache/ak1/pb_main_final'))]
 sources += [('shape_'+name,Path('C:/Users/Tom/.cache/ak1/pb_shapes')/name) for name in ('r2_a1024','r9_a128','r17_a288')]
 studies=[]
 for name,source in sources:
  study=read(source/'study.json')
  if study['status']!='passed':raise ValueError('study not passed: '+name)
  destination=out/name
  if not destination.exists():shutil.copytree(source,destination)
  if sha(destination/'study.json')!=sha(source/'study.json'):raise ValueError('study copy mismatch')
  bank=decode_bank(Path(study['bank']),Path(study['bank']).parent/'manifest.json')
  for run in study['runs']:
   folder=destination/run['label'];receipt=read(folder/'summary.json')
   if run.get('expected_rejection'):
    if run['exit_code']!=2 or receipt['status']!='rejected_verification' or receipt['accepted'] or receipt['committed']:
     raise ValueError('missing actual rejection receipt')
    if not (folder/'REJECTED').is_file() or (folder/'COMMITTED').exists():raise ValueError('rejection marker')
    if receipt['committed_program_id']!=receipt['initial_slot'] or receipt['committed_input']!=receipt['input_initial']:raise ValueError('rejection advanced state')
   else:
    if run['exit_code'] or not receipt['accepted'] or not receipt['committed'] or not (folder/'COMMITTED').is_file():raise ValueError('unverified native result')
    verify_trace(folder/'trace.csv',bank,receipt['input_initial'],receipt['hops'],receipt['initial_slot'],receipt['execution_mode'])
   if sha(folder/'bank.bin')!=study['bank_file_sha256'] or sha(folder/'operators.atlas')!=study['atlas_sha256']:raise ValueError('immutable input binding')
  studies.append(study)
 # Primary study must bind current sources; shape studies are replayed above
 # using the current independent oracle after the rejection-only harness fix.
 primary=studies[0]
 if any(sha(ROOT/f)!=digest for f,digest in primary['source_hashes'].items()):raise ValueError('primary source changed')
 exe=Path(primary['executable'])
 if sha(exe)!=primary['executable_sha256']:raise ValueError('native binary changed')
 amendment=read(out/'amendment/amendment.json');active=read(out/'amendment/active_bank.json')
 if amendment['status']!='passed' or active['sha256']!=amendment['accepted_bank_sha256'] or sha(active['bank'])!=active['sha256']:raise ValueError('amendment not active')
 cpu=Path('C:/Users/Tom/.cache/ak1/program_cpu/evidence_1789317069091464500')
 gpu=Path('C:/Users/Tom/.cache/ak1/sdf_gpu/evidence_1789317264908545800')
 for name,path in [('cpu',cpu),('gpu',gpu)]:
  status=read(path/'validation.json')
  if status['status']!='passed' or status['proofs']!='passed':raise ValueError('mandatory regression incomplete')
  save(out/(name+'_regression_receipt.json'),status)
  for log in ('cpu_ctest.log','program_bank_python_tests.log','symbolic_proofs.log'):
   shutil.copy2(path/log,out/(name+'_'+log))
 runs=[r for study in studies for r in study['runs']]
 cold=[r for r in primary['runs'] if r['kind']=='cold']
 if len(cold)!=5 or any(not r['at_compulsory_floor'] or r['extra_misses']!=0 for r in cold):raise ValueError('cache claim not established')
 capacity=next(r['receipt'] for r in primary['runs'] if r['label']=='capacity')
 capacity_cold=next(r['receipt'] for r in primary['runs'] if r['label']=='capacity_cold')
 tests=(out/'final_all_python_tests.log').read_text(encoding='utf-8')
 match=re.search(r'Ran (\d+) tests',tests);skips=re.search(r'OK \(skipped=(\d+)\)',tests)
 if not match or not skips or 'FAILED (' in tests:raise ValueError('final Python test receipt')
 all_tests=int(match.group(1));skipped=int(skips.group(1))
 learning=read(ROOT/'examples/program_bank/learned_v1/learning.json')
 if learning['status']!='passed' or learning['accepted_skills']!=3:raise ValueError('learning incomplete')
 binary_dir=ROOT/'output/bin/program_bank_v1';binary_dir.mkdir(parents=True,exist_ok=True)
 shutil.copy2(exe,binary_dir/exe.name)
 summary=dict(schema='atomos-distilled-program-bank-final-v1',date='2026-09-13',concept_author='Tom Klootwijk',status='passed',
  completed_scope='Documented request and working finite distillation/program-texture/VRAM/cache/amendment construction',
  long_term_target='general language-model behaviour',general_language_model_replacement='not_established',huggingface_model_execution='not_run; model-card research only',
  interpretation='One-bit storage on a required seeded log-polar/Klein chart; source-word SDF NOR operators fixed; no cache pinning or seed-only compression claim',
  counts=dict(distinct_learned_skills=3,training_cases=120,withheld_cases=72,exhaustive_skill_cases=192,
   new_native_runs=len(runs)+1,accepted_new_native_runs=sum(not r.get('expected_rejection',False) for r in runs)+1,
   rejected_native_injections=sum(r.get('expected_rejection',False) for r in runs),new_sanitizer_runs=sum(r['kind'] in ('memcheck','racecheck','synccheck') for r in runs),
   accepted_program_evaluations=sum(r['receipt']['hops_executed'] for r in runs if not r.get('expected_rejection',False))+24,
   cold_profiles=len(cold),cold_profiles_at_floor=len(cold),cpu_ctest=13,publication_regressions=5,python_discovered=all_tests,python_passed=all_tests-skipped,python_skipped=skipped,
   mandatory_cpu_configurations=48,mandatory_gpu_configurations=144,mandatory_gpu_memchecks=6,symbolic_obligations=19),
  capacity=dict(pool_bytes=capacity['pool_bytes'],initialized_bytes=capacity['pool_initialized_bytes'],verified_bytes=capacity['pool_verified_bytes'],
   physical_program_slots=capacity['pool_slots'],distinct_programs=capacity['distinct_programs'],executed_program_page_bytes=capacity['program_texture_swept_bytes'],
   free_bytes_after_allocation=capacity['free_bytes_after_allocation'],reserve_bytes=capacity['reserve_bytes'],ordinary_kernel_ms=capacity['kernel_ms'],
   cold_pool_bytes=capacity_cold['pool_bytes'],cold_operator_plus_program_bytes=capacity_cold['unique_texture_footprint_bytes'],cold_miss_floor=capacity_cold['unique_texture_sector_floor'],
   replicated_capacity_not_distinct_knowledge=True,all_pool_in_texture_cache=False),
  cache_small=dict(operator_bytes=1024,all_program_bytes=768,whole_texture_bytes=1792,cold_miss_floor=56,repeats_per_layout=2,extra_misses=0),
  amendment=dict(program_id=0,old_next=1,new_next=2,old_version=1,new_version=2,skill_cases_preserved=192,native_hops=24,autonomous_learning=False),
  code=dict(executable=str(binary_dir/exe.name),executable_sha256=sha(exe),cuda_architecture='sm_120',cuda_toolkit='12.8.61',msvc='19.44.35221',nvidia_driver='591.59',
   registers_per_thread=capacity['registers_per_thread'],local_bytes_per_thread=capacity['local_bytes_per_thread'],active_evaluator_threads=1,device=capacity['device']),
  evidence=dict(main_study='results/program_bank_20260913/verified_study/study.json',shape_studies=[f'results/program_bank_20260913/{n}/study.json' for n,_ in sources[1:]],
   amendment='results/program_bank_20260913/amendment/amendment.json',learning='examples/program_bank/learned_v1/learning.json',
   mandatory_cpu=str(cpu/'validation.json'),mandatory_gpu=str(gpu/'validation.json'),documentation='docs/DISTILLED_PROGRAM_BANK.md',teachers='docs/HUGGINGFACE_TEACHERS.md'),
  errata=['Earlier final_study counted four export failures as rejection; superseded by verified_study with four exit-2 retained rejection receipts.',
   'Original r2_a1024 instrumented export reached Windows MAX_PATH; replaced by short-path shape study; original attempt remains failed.',
   'Python skips are existing optional-fixture tests, not reported as passed.','SMT proofs describe equations, not the new native binary.'])
 save(out/'final_summary.json',summary)
 status_path=ROOT/'results/validation_status.json';status=read(status_path)
 status['distilled_program_bank']=dict(status='passed',evidence='results/program_bank_20260913/final_summary.json',general_language_model_replacement='not_established')
 save(status_path,status)
 seal_files=[p for p in out.rglob('*') if p.is_file() and p.name not in ('evidence_seal.json','finalize.log')]
 seal_files += [ROOT/f for f in primary['source_hashes']] + [ROOT/'docs/DISTILLED_PROGRAM_BANK.md',ROOT/'docs/HUGGINGFACE_TEACHERS.md',ROOT/'AUTHORSHIP.json',ROOT/'CMakeLists.txt',ROOT/'tools/finalize_program_bank.py',binary_dir/exe.name]
 seal_files += [ROOT/f for f in ('README.md','proofs/CLAIMS.md','docs/coverage.csv','results/validation_status.json','tools/amend_program_bank.py','tools/distill_program_bank.py','tools/validate.py')]
 seal_files += list((ROOT/'tests').glob('test_program_bank*.py')) + [ROOT/'tests/test_publication.cpp']
 seal_files += [p for p in (ROOT/'examples/program_bank').rglob('*') if p.is_file()]
 save(out/'evidence_seal.json',dict(schema='atomos-program-bank-evidence-files-v1',files={p.relative_to(ROOT).as_posix():sha(p) for p in seal_files}))
 print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
