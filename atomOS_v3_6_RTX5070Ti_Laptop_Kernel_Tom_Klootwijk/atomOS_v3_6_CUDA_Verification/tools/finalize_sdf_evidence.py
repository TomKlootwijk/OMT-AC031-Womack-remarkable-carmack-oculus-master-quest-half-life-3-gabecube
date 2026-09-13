"""Summarize completed evidence without promoting scoped results to global claims."""
from pathlib import Path
import hashlib,json,re,shutil,statistics
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'results/sdf_klein_20260913';AK=Path('C:/Users/Tom/.cache/ak1')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')
paths={
 'cpu':AK/'sdf_cpu/evidence_1789306629417199700/validation.json',
 'original_gpu':AK/'sdf_gpu/evidence_1789306726916312500/validation.json',
 'bulk_conformance':AK/'sdf_conformance_tma/study.json',
 'bulk_edges':AK/'sdf_tma_edges/study.json',
 'bulk_capacity':AK/'sdf_capacity_tma/study.json',
 'bulk_refinement':AK/'sdf_capacity_refinement/study.json',
 'nor':AK/'sdf_nor_validation/summary.json',
 'lineage':AK/'sdf_lineage_validation/summary.json',
 'joint_dense':AK/'sdf_joint_validation_dense/summary.json',
 'joint_sparse':AK/'sdf_joint_validation_sparse/summary.json',
 'nor_sparse_cache':AK/'sdf_nor_cache/study.json',
 'nor_dense_cache':AK/'sdf_nor_cache_dense/study.json',
 'nor_cg_experiment':AK/'sdf_nor_cache_cg/study.json',
 'joint_cache':AK/'sdf_joint_cache/study.json',
 'nor_proofs':E/'nor_proofs.json','tape_proofs':E/'universal_packing_proofs.json',
}
studies={name:read(p) for name,p in paths.items()}
if any(s.get('status')!='passed' for s in studies.values()):raise ValueError('incomplete or failed required evidence')
for name,s in studies.items():
 if 'executable' in s and sha(s['executable'])!=s['executable_sha256']:raise ValueError(name+' executable bytes changed')
 for rel,value in s.get('source_hashes_after',s.get('source_hashes',{})).items():
  if sha(ROOT/rel)!=value:raise ValueError(name+' source changed: '+rel)
cpu_log=(E/'final_cpu_ctest.log').read_text(encoding='utf-8')
py_log=(E/'final_python_tests.log').read_text(encoding='utf-8')
assert '100% tests passed, 0 tests failed out of 12' in cpu_log
assert re.search(r'Ran 105 tests',py_log) and py_log.rstrip().endswith('OK')
bulk_profiles=[r for key in ('bulk_capacity','bulk_refinement') for r in studies[key]['runs'] if r['kind']=='cold_profile']
cache_table=[]
for size in sorted({r['mask_bytes'] for r in bulk_profiles}):
 row=[f'{size/2**20:g} MiB']
 for layout in ('linear','morton8'):
  rr=[r for r in bulk_profiles if r['mask_bytes']==size and r['layout']==layout]
  row.append(' / '.join(f'{r["extra_misses"]:,}' for r in rr))
 cache_table.append(row)
full_sizes=[size for size in {r['mask_bytes'] for r in bulk_profiles} if all(r['at_compulsory_floor'] for r in bulk_profiles if r['mask_bytes']==size)]
largest=max(full_sizes);next_size=min(r['mask_bytes'] for r in bulk_profiles if r['mask_bytes']>largest)
assert largest==4849664 and next_size==4915200
joint_cold=[r for r in studies['joint_cache']['runs'] if r['kind']=='cold']
assert len(joint_cold)==4 and all(r['extra_misses']==0 and r['compulsory_miss_floor']==32 for r in joint_cold)
smoke=read(AK/'sdf_joint_smoke/summary.json')
assert smoke['candidate_verified'] and smoke['executed_steps']==6 and smoke['committed_frontier_count']==64
joints=[studies[k] for k in ('joint_dense','joint_sparse')]
joint_cases=sum(s['executed_cases'] for s in joints);joint_sanitizers=sum(s['sanitizer_cases'] for s in joints)
joint_counts={key:sum(r['verification'][key] for s in joints for r in s['cases']+s['sanitizers']) for key in ('actual_transitions','gate_evaluations','proposed_children','diagnostic_records','word_records','bst_searches','packed_snapshot_words_verified')}
bulk_normal=sum(r['kind']=='conformance' for k in ('bulk_conformance','bulk_edges') for r in studies[k]['runs'])
bulk_sanitizers=sum(r['kind']=='sanitizer' for k in ('bulk_conformance','bulk_edges') for r in studies[k]['runs'])
timing={r['label'].rsplit('_',1)[-1]:r['median_kernel_ms'] for r in studies['bulk_refinement']['runs'] if r['kind']=='timing' and r['receipt']['rows']==592}
jt=[r['receipt']['kernel_ms'] for r in studies['joint_cache']['runs'] if r['kind']=='ordinary']
report=dict(schema='atomOS-SDF-Klein-final-evidence-v1',date='2026-09-13',concept_author='Tom Klootwijk',evidence_status='passed',
 scope='Declared SDF-word/Klein/NOR/lineage constructions and finite measured binaries; not a recovered scalar SDF for every source operator',
 full_original_operator_scalar_sdf_bank='not_established; source audit records missing geometry, encoders and fields',
 universality='constructive NOR/controller/tape simulation with addressable-state and joint-frontier resource assumptions',
 literal_infinite_device_execution='not_claimed',permanent_texture_cache_pinning='not_claimed',
 bulk_largest_fully_retained_bytes=largest,bulk_next_tested_misses_bytes=next_size,bulk_cold_profiles=len(bulk_profiles),
 bulk_profiles_at_floor=sum(r['at_compulsory_floor'] for r in bulk_profiles),
 joint_cold_profiles=4,joint_profiles_at_floor=4,joint_texture_bytes=1024,
 counts=dict(cpu_ctest=12,python_unittests=105,symbolic_obligations=19,original_gpu=144,original_memchecks=6,
  bulk_native_cases=bulk_normal,bulk_sanitizers=bulk_sanitizers,nor_native_cases=80,nor_sanitizers=9,
  lineage_native_cases=56,lineage_sanitizers=9,joint_native_cases=joint_cases,joint_sanitizers=joint_sanitizers),
 joint_checked_totals_including_sanitizers=joint_counts,
 evidence={k:dict(path=str(v),sha256=sha(v)) for k,v in paths.items()},
 cache_table=cache_table,
 joint_cover=f'{joint_cases} native cases and {joint_sanitizers} sanitizer runs checked the coupled controller/branching profile. Its full 1 KiB atlas met the cold retention floor in all four measured joint profiles.',
 joint_description='The connected profile executes one CUDA launch with one active lane. It warms one immutable NOR-site atlas, computes the program controller through its SDF-word gates, uses the written symbol to select phi, branches on the Klein quotient, filters every logical word, updates JK/tape and searches live IDs, then rereads the atlas.',
 joint_rows=[['Same operator dictionary','8 x 256 sampled sites; 64 logical uint4 entries; 1,024 texture bytes; actual SDF compilation independently checked 8,192 predicate bits.'],
  ['Connected example','Binary input 31 became 32 in 6 steps. First five writes selected one winding; the final write selected two. The run retained 64 distinct IDs.'],
  ['Checks in that run','114 NOR gate evaluations; 126 children/diagnostic records; 384 complete word/JK records; 138 search traces; complete tape/frontier snapshots.'],
  ['Native validation',f'{joint_cases} cases and {joint_sanitizers} sanitizer runs across sparse and dense atlases, both layouts, faults, extinction and resource limits.'],
  ['Search organization','Sorted IDs are searched by repeated midpoint selection: an implicit balanced binary search tree. Exact visited index paths are exported and checked.']],
 joint_transaction='Tape, occupancy, JK, frontier and time are published as one verified candidate prefix. A resource or program stop adds no partial failing step and retains the verified earlier prefix. A verification mismatch rejects the entire proposal and restores every initially committed component. The mutable buffers and traces remain outside the immutable operator texture.',
 joint_performance=f'Four ordinary six-step runs measured {min(jt):.3f}-{max(jt):.3f} ms for the complete kernel. This includes full traces and snapshots; it excludes transfers, CPU checking and export. The native kernel reports 86 registers and 152 local bytes per thread. This is a finite correctness witness, not the distributed bulk throughput profile.',
 bulk_timing_text=f'{timing["linear"]:.3f} ms linear and {timing["morton8"]:.3f} ms Morton: median of three evolving epochs per layout, each including warm, TMA transfers, work, checks and reread. These are kernel timings, not three independent process trials.',
 nor_cache_text='For the 1 KiB sparse 8 x 64 atlas, linear had 0 extra misses and Morton 24. For the dense 8 x 256 atlas, linear had 8 extra misses and Morton 0. Each result repeated twice for a 256-step oscillator. The tested global-cache flags did not fix the sparse Morton result. No universal layout winner is established.',
 joint_cache_text='The dense 1 KiB shared-atlas six-step run had exactly 32 compulsory misses and 0 extra misses in both layouts, twice each. It made 626 TEX requests/sectors: 594 hits + 32 misses. The cold whole-launch hit rate was 94.888%; subsequent work and reread added no misses under this counter test.',
 validation_rows=[['Original K1 regression','48 CPU configurations; 144 GPU configurations and 6 memory-check runs. Required symbolic checks passed. Historical/source-fixture scope retained.'],
  ['Final CPU checks','12 CTest cases and 105 Python unit/oracle/mutation tests passed. Source/geometry, layout, metadata, wrong-output and rollback checks are included.'],
  ['Mathematical checks','15 original obligations, 2 packed-tape obligations and 2 new NOR obligations: all negated properties UNSAT in Z3. Analytic simulation arguments are documented separately.'],
  ['Optimized SDF/Klein bulk',f'{bulk_normal} native conformance/edge cases and {bulk_sanitizers} sanitizer runs passed, including angular tails, padding, both seams and 130-epoch prefixes.'],
  ['SDF/NOR controller','80 cases + 9 sanitizer runs; all finite controller input rows, gate chronology, machine transitions, full packed tape and expected faults independently replayed.'],
  ['Lineage and search','56 cases + 9 sanitizer runs; all child IDs, geometric locations, masks, diagnostics, JK and search results replayed.'],
  ['Connected profile',f'{joint_cases} cases + {joint_sanitizers} sanitizer runs; entire causal controller-to-phi-to-geometry-to-state path and combined publication checked.'],
  ['Native cache evidence','36 bulk cold profiles bracketed capacity; separate sparse/dense NOR and connected-kernel counters retained, with ordinary timings kept separate.']],
 evidence_rows=[['Summary and hashes','results/sdf_klein_20260913/final_summary.json; evidence_seal.json'],
  ['Build / device / native logs','results/sdf_klein_20260913/ (nvcc, sanitizer, build logs and native SASS dumps)'],
  ['Bulk source conformance','C:/Users/Tom/.cache/ak1/sdf_conformance_tma/study.json; sdf_tma_edges/study.json'],
  ['Bulk capacity','C:/Users/Tom/.cache/ak1/sdf_capacity_tma/study.json; sdf_capacity_refinement/study.json'],
  ['NOR and lineage','C:/Users/Tom/.cache/ak1/sdf_nor_validation/summary.json; sdf_lineage_validation/summary.json'],
  ['Connected validation','C:/Users/Tom/.cache/ak1/sdf_joint_validation_dense/summary.json; sdf_joint_validation_sparse/summary.json'],
  ['Connected cache','C:/Users/Tom/.cache/ak1/sdf_joint_cache/study.json'],
  ['Copied native executables','output/bin/sdf_klein_20260913/atomos_cache_bulk.exe; atomos_sdf_universal.exe; atomos_sdf_lineage.exe; atomos_sdf_joint.exe']],
)
binary_output=ROOT/'output/bin/sdf_klein_20260913';binary_output.mkdir(parents=True,exist_ok=True)
report['binaries']={}
for name in ('atomos_cache_bulk','atomos_sdf_universal','atomos_sdf_lineage','atomos_sdf_joint'):
 source=AK/'sdf_gpu/Release'/(name+'.exe');destination=binary_output/source.name
 if destination.exists() and sha(destination)!=sha(source):raise FileExistsError('refuse replacing different delivered binary '+str(destination))
 if not destination.exists():shutil.copyfile(source,destination)
 assert sha(source)==sha(destination)
 report['binaries'][name]=dict(path=str(destination),build_path=str(source),sha256=sha(source))
save(E/'final_summary.json',report)
# Preserve the prior unscoped status in a dated evidence file before replacing it.
status_path=ROOT/'results/validation_status.json';prior=E/'historical_K1_U1_validation_status.json'
if not prior.exists():shutil.copyfile(status_path,prior)
save(status_path,dict(engine='atomOS v3.6',concept_author='Tom Klootwijk',date='2026-09-13',
 status='declared_SDF_Klein_NOR_lineage_joint_profiles_validated',
 latest_evidence='results/sdf_klein_20260913/final_summary.json',historical_status=str(prior.relative_to(ROOT)),
 source_operator_scalar_sdf_bank=report['full_original_operator_scalar_sdf_bank'],
 universality_scope=report['universality'],counts=report['counts'],
 texture_residency=dict(bulk_largest_tested_fully_retained_bytes=largest,next_tested_size_with_extra_misses=next_size,
  joint_tested_texture_bytes=1024,joint_cold_profiles_at_floor=4,joint_cold_profiles=4,
  guarantee='observed scoped within-launch retention; no permanent cache pin or all-workload guarantee')))
print(json.dumps(dict(evidence_status=report['evidence_status'],summary=str(E/'final_summary.json'),counts=report['counts'])))
