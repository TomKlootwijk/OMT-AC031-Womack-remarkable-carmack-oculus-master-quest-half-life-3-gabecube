"""Summarize the completed September 13 review without rewriting old evidence."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'results/review_20260913'; CACHE=Path('C:/Users/Tom/.cache/ak1')
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    gp=CACHE/'gpu128/evidence_1789293705720626800/validation.json'
    cp=CACHE/'cpu/evidence_1789293352596987800/validation.json'
    bp=CACHE/'cache_benchmark/benchmark.json'; pp=CACHE/'cache_profiles/profile_summary.json'; sp=CACHE/'launch_memchecks/supplemental.json'
    g,c,b,p,s=map(read,(gp,cp,bp,pp,sp))
    assert all(x['status']=='passed' for x in (g,c,b,s)) and p['status']=='collected'
    assert len(g['runs'])==150 and len(c['runs'])==48 and len(b['runs'])==180 and len(p['runs'])==30 and len(s['runs'])==6
    exe=CACHE/'gpu128/Release/atomos_cuda.exe';digest=sha(exe)
    assert digest==b['executable_sha256']==p['executable_sha256']
    original=E/'preparation_validation_status.json'
    if not original.exists():shutil.copy2(ROOT/'results/validation_status.json',original)
    (ROOT/'output/bin').mkdir(parents=True,exist_ok=True)
    shutil.copy2(exe,ROOT/'output/bin/atomos_cuda.exe')
    assert sha(ROOT/'output/bin/atomos_cuda.exe')==digest
    summary=dict(schema='atomOS-v3.6-K1-review',date='2026-09-13',status='passed',
        gpu_validation_path=str(gp),cpu_validation_path=str(cp),benchmark_path=str(bp),profile_path=str(pp),supplemental_path=str(sp),
        executable_path=str(ROOT/'output/bin/atomos_cuda.exe'),executable_sha256=digest,
        ordinary_gpu_lane_epochs=sum(r['lane_epochs'] for r in g['runs'] if not r['path'].startswith('memcheck_')),
        matrix_gpu_lane_epochs=sum(r['lane_epochs'] for r in g['runs']),
        supplemental_memchecks=len(s['runs']),max_float_difference_radians=max(r['max_float_difference_radians'] for r in g['runs']),
        complete_texture_residency='not_established',packed_linear_sectors=2048,packed_linear_lookup_misses=2048,
        source_proof_scope='SMT specification claims, not compiler/binary proof',
        original_failures=[str(ROOT/'build_cpu/evidence_1789293007931007200/configure.log'),str(ROOT/'build_gpu/evidence_1789293024702278500/configure.log'),str(CACHE/'gpu/evidence_1789293066570379300/configure.log'),str(CACHE/'gpu128/evidence_1789293312980970500/validation.json')],
        repaired_defects=['free VRAM reserve admission','execution metadata consistency','Windows native Compute Sanitizer discovery'],
        performance_options='texture-packed; max-L1 preference; 64/128/256-thread scheduling; original defaults unchanged')
    write(E/'review_summary.json',summary)
    status=dict(engine='atomOS v3.6',kernel_revision='K1',date='2026-09-13',status='passed',concept_author='Tom Klootwijk',
        cpp_test_groups=31,cpp_assertions=134509,cpp_tests='passed',cpu_ctest_cases=7,
        python_unit_tests=31,python_unit_status='passed',symbolic_obligations=15,symbolic_result='all_unsat',solver='Z3 4.16.0',
        cpu_run_configurations=48,cpu_lane_epochs=sum(r['lane_epochs'] for r in c['runs']),
        cuda_compilation='passed',gpu_execution='passed',gpu_run_configurations=144,gpu_memcheck='passed',gpu_matrix_memchecks=6,supplemental_gpu_memchecks=6,
        windows_compilation='passed',cpu_address_undefined_sanitizers='not_run_in_this_review',
        gpu_device=g['device'],nvcc='12.8.61',msvc='19.44.35221.0',nvidia_driver='591.59',cmake='4.3.2',python='3.13.9',
        benchmark_configurations=36,benchmark_trials_per_configuration=5,profile_launch_samples=30,
        complete_texture_cache_residency='not_established',max_gpu_reference_error_radians=summary['max_float_difference_radians'],
        proof_scope='Symbolic specifications, not compiler or GPU machine-code verification',
        review_summary='results/review_20260913/review_summary.json',preparation_status='results/review_20260913/preparation_validation_status.json',
        evidence=dict(cpu=str(cp),gpu=str(gp),benchmark=str(bp),cache_counters=str(pp),supplemental_memchecks=str(sp)))
    import platform
    status['python']=platform.python_version()
    write(ROOT/'results/validation_status.json',status)
    for src,name in ((gp,'gpu_validation.json'),(cp,'cpu_validation.json'),(bp,'benchmark.json'),(pp,'profile_summary.json'),(sp,'supplemental_memchecks.json')):
        shutil.copy2(src,E/name)
    changed=[]
    for line in (ROOT/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        expected,name=line.split('  ',1);path=ROOT/name
        if not path.exists() or sha(path)!=expected:changed.append(name)
    summary['original_manifest_changed_files']=changed;write(E/'review_summary.json',summary)
    names=[]
    for folder in ('cuda','include','src','tools','tests','python','proofs','docs'):
        for f in (ROOT/folder).rglob('*'):
            if f.is_file() and f.suffix in ('.cu','.hpp','.cpp','.py','.md','.json','.csv','.smt2'):names.append(f)
    names.extend(ROOT/n for n in ('CMakeLists.txt','AUTHORSHIP.json','README.md','AGENTS.md'))
    write(E/'source_sha256.json',{'schema':'atomOS-review-source-hashes','scope':'Unsigned integrity list of current reviewed sources; original preparation manifest preserved','files':{str(f.relative_to(ROOT)).replace('\\','/'):sha(f) for f in sorted(set(names))}})
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
