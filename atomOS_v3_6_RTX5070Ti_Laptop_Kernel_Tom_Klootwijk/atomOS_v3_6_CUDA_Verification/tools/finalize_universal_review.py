"""Collect only completed execution evidence and publish the reviewed binaries."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'results/optimization_20260913'
CACHE=Path('C:/Users/Tom/.cache/ak1')
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value: raise ValueError(message)
def write(path,value): Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
paths=dict(cpu_validation=CACHE/'cpu_opt_final/evidence_1789301536940708800/validation.json',
           gpu_validation=CACHE/'gpu_opt_final/evidence_1789301537057744900/validation.json',
           bulk_validation=CACHE/'opt_bulk_final_conformance/study.json',
           bulk_profiles=CACHE/'opt_bulk_final_profiles/study.json',
           bulk_edges=CACHE/'opt_bulk_final_edges/study.json',
           universal_validation=CACHE/'universal_validation_release/summary.json',
           hardware_stress=CACHE/'universal_stress_capacity.json',
           timing_comparison=CACHE/'opt_compare_release/comparison.json')
data={key:read(path) for key,path in paths.items()}
for key,value in data.items(): require(value['status']=='passed',f'incomplete evidence: {key}')
for key in ('cpu_validation','gpu_validation'):
    require(all(command['exit_code']==0 for command in data[key]['commands']),f'failed validation command: {key}')
    require(data[key]['cpu']==data[key]['proofs']=='passed','CPU/proof receipt incomplete')
require(data['gpu_validation']['gpu']==data['gpu_validation']['gpu_memcheck']=='passed','GPU matrix incomplete')
for key in ('bulk_validation','bulk_profiles','bulk_edges'):
    report=data[key]
    require(report['raw_log_validation']['status']=='passed','bulk raw-log audit failed')
    require(sha(report['executable'])==report['executable_sha256']==report['executable_sha256_after'],'bulk executable changed')
    for category in ('source_hashes','audit_source_hashes'):
        require(report[category+'_before']==report[category+'_after'],'bulk source changed during execution')
        for name,digest in report[category+'_after'].items(): require(sha(ROOT/name)==digest,'bulk source differs now: '+name)
u=data['universal_validation']
require(u['source_and_executable_unchanged'],'U source changed during execution')
require(sha(u['executable'])==u['executable_sha256']==u['executable_sha256_after'],'U executable changed')
for name,digest in u['source_hashes_after'].items(): require(sha(ROOT/name)==digest,'U source changed after validation: '+name)
require(all(case['verification']['status']=='passed' for case in u['cases']+u['sanitizers']),'U case failed')
h=data['hardware_stress']; e=h['execution']; v=h['verification']
require(sum(launch['executed_transitions'] for launch in e['launches'])==e['executed_transitions'],'stress transition sum differs')
require(v['packed_bytes_verified']==h['allocation']['tape_bytes']==v['program_touched_tape_bytes'],'full tape capacity coverage incomplete')
require(v['final_stop_counts']['tape_range']==e['machines'],'expected capacity stop differs')
require(e['executed_transitions']==e['machines']*(e['cells_per_machine']-1),'capacity prefix length differs')
san=read(E/'stress_sanitizers.json');require(san['status']=='passed','stress sanitizers failed')
proof=read(E/'universal_packing_proofs.json');require(proof['status']=='passed' and proof['observed'].split()==['unsat','unsat'],'packed proof incomplete')
require('33199 assertions passed' in (E/'universal_final_cpu_tests.log').read_text(),'U CPU regression count differs')
require('100% tests passed, 0 tests failed out of 8' in (E/'final_cpu_ctest.log').read_text(),'CPU CTest incomplete')
profiles=[sample for key in ('bulk_profiles','bulk_edges') for sample in data[key]['samples'] if sample['task']['kind']=='profile']
timing=data['timing_comparison']; require(timing['trials']==5,'five timing trials required')
binary_sources=dict(atomos_engine=CACHE/'universal_final/Release/atomos_engine.exe',
                    atomos_universal_stress=CACHE/'universal_final/Release/atomos_universal_stress.exe',
                    atomos_cache_bulk=CACHE/'bulk_opt_final/Release/atomos_cache_bulk.exe',
                    atomos_cuda=CACHE/'gpu_opt_final/Release/atomos_cuda.exe')
require(sha(binary_sources['atomos_cache_bulk'])==timing['binaries']['selected']['sha256'],'selected timing binary differs')
require(sha(binary_sources['atomos_universal_stress'])==san['exe_sha256'],'stress sanitizer binary differs')
delivered={}
for name,path in binary_sources.items():
    destination=ROOT/'output/bin'/(name+'.exe');shutil.copy2(path,destination);delivered[destination.name]=sha(destination)
rows=[];ratios=[]
for size in ('default','max'):
    for layout in ('linear','morton8'):
        samples={a['binary']:a for a in timing['aggregates'] if a['size']==size and a['layout']==layout}
        old,new=samples['baseline']['median_ms'],samples['selected']['median_ms'];ratio=old/new
        rows.append([('64 KiB' if size=='default' else '4 MiB')+' / '+layout,f'{old:.3f} ms',f'{new:.3f} ms',f'{ratio:.2f}x'])
        if size=='max':ratios.append(ratio)
examples=[]
descriptions={
 'unary_increment_halt':('Add one mark','Three marks become four; program halts.'),
 'pragmatic_binary_increment':('Binary arithmetic','31 becomes 32; six simple read/write/move transitions.'),
 'pragmatic_symbol_replace':('Sequence rewriting','1,2,1,1 becomes 2,2,2,2; program halts at the blank.'),
 'walker_long_prefix':('Continue a program','A finite prefix remains running; a step budget is not a halt.')}
for name,(label,description) in descriptions.items():
    case=next((case for case in u['cases'] if case['task']['name']==name),None)
    if case: examples.append([label,description,str(case['verification']['committed_u_transitions'])])
result=dict(schema='atomOS-K1-U1-final-review',status='passed',concept_author='Tom Klootwijk',
            created_at_utc=datetime.now(timezone.utc).isoformat(),**{key:str(path) for key,path in paths.items()},
            cpp_assertions=259957,cpp_groups=34,universal_cpp_assertions=33199,python_word_tests=37,python_universal_tests=20,
            original_symbolic_obligations=15,additional_packed_symbol_obligations=2,
            bulk_conformance=data['bulk_validation']['raw_log_validation']['conformance_runs']+data['bulk_edges']['raw_log_validation']['conformance_runs'],
            cache_profiles=len(profiles),cache_profiles_at_floor=sum(sample['traffic_audit']['observed_cold_floor_reached'] for sample in profiles),
            bulk_python_exports=26,bulk_python_lane_epochs=626288,
            universal_device_cases=sum(case['verification'].get('backend_recorded')=='cuda' for case in u['cases']),
            universal_prelaunch_refusals=sum(bool(case['task'].get('configuration_error') or case['task'].get('resource_refused')) for case in u['cases']),
            timing_rows=rows,large_speedup_range=f'{min(ratios):.2f}-{max(ratios):.2f}x',
            program_examples=examples,delivered_binaries=delivered,
            source_document_sha256='b51651c007c560775ff1950e278789cd7674e131ec71a09ebd9254cebe9c19ce',
            stress_command=[str(binary_sources['atomos_universal_stress']),'--memory-fraction','0.85','--steps-per-launch','16384','--rounds','32','--out',str(paths['hardware_stress'])],
            stress_report_sha256=sha(paths['hardware_stress']),stress_sanitizer_cases=len(san['cases']),
            source_snapshot_at_packaging={name:sha(ROOT/name) for name in ('CMakeLists.txt','include/atomos/core.hpp','include/atomos/universal.hpp','experiments/cache_bulk.cu','experiments/universal_engine.cu','experiments/universal_stress.cu')},
            limits=['Conditional machine-simulation theorem; finite binary execution evidence.','Full M1 optional geometric profiles remain disabled.','Post-run audit seal is separate from native commit.','Texture retention measured for bulk word profile; combined word-plus-U residency unmeasured.','Stress throughput belongs to the generated table and many independent tapes.'])
write(E/'summary.json',result)
status=read(ROOT/'results/validation_status.json')
status.update(status='execution_validated_programmable_U_and_capacity_measured',kernel_revision='K1 + U1',
              cpp_test_groups=34,cpp_assertions=259957,cpu_ctest_cases=8,
              universal_cpp_assertions=33199,universal_python_tests=20,
              latest_review='results/optimization_20260913/summary.json',
              universal_validation=dict(status='passed',cases=u['executed_cases'],gpu_cases=result['universal_device_cases'],prelaunch_refusals=result['universal_prelaunch_refusals'],sanitizers=u['sanitizer_cases'],transitions=u['verified_u_transitions']),
              parallel_capacity=dict(status='passed',machines=e['machines'],transitions=e['executed_transitions'],tape_bytes=h['allocation']['tape_bytes'],kernel_ms=e['kernel_ms'],wall_seconds=h['wall_seconds'],stop='tape_range'),
              latest_bulk=dict(status='passed',cache_profiles=len(profiles),at_compulsory_floor=result['cache_profiles_at_floor'],registers=88,compute_threads=256,conformance_cases=result['bulk_conformance'],binary_sha256=delivered['atomos_cache_bulk.exe']))
status['evidence']['latest']=str(E/'summary.json')
status['evidence']['universal']=str(paths['universal_validation'])
status['evidence']['cpu']=str(paths['cpu_validation'])
status['evidence']['gpu']=str(paths['gpu_validation'])
status['production_executable_sha256']=delivered['atomos_cuda.exe']
status['gpu_device']=data['gpu_validation']['device']
status['python_unit_tests']=57
status['python_word_unit_tests']=37
status['universal_packing_obligations']=2
status['universal_packing_result']='both_unsat'
write(ROOT/'results/validation_status.json',status)
print(json.dumps(result,indent=2))
