"""Package completed bulk-residency evidence; never launches workloads or repeats numerical audits.

Run only after both selected studies finish. Saved validation/audit receipts,
retained hashes, coverage, and current source/binary identity are checked before
delivery files or validation_status.json are changed.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import itertools
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / 'results/residency_followup'
CACHE = Path('C:/Users/Tom/.cache/ak1')
CPU = CACHE / 'cpu_fold_final/evidence_1789299038566882500/validation.json'
GPU = CACHE / 'gpu_fold_final/evidence_1789299027401576500/validation.json'
MAIN = CACHE / 'bulk_final_study_v2/study.json'
EDGES = CACHE / 'bulk_final_edges/study.json'
NATIVE = E / 'final_native.json'
STATUS = ROOT / 'results/validation_status.json'
OLD_PRODUCTION = 'c2e551dec5b9251945eeabe0a1ad701aa883f9dd2af1a477babc55a57bccbb4f'
EXPECTED_PRODUCTION = 'cdfe79ac3e48e35f7837954b680ad9bbef0a2a4ba353422e54724ff6bed75d95'
EXPECTED_CPU = 'd0199da586b0ef092943008c5e8aa452473aa53555c811ca870b631019b2a597'
EXPECTED_BULK = 'fc25b2f435bc3c1ccbcdc2ed8f494ef3247285b357541b72f2855e8b83a175e4'


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    data = Path(path).read_bytes()
    return json.loads(data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def inside(directory, name):
    path = (directory / name).resolve()
    require(path.is_relative_to(directory.resolve()) and path.is_file(), f'missing or external evidence: {path}')
    return path


def check_hashes(mapping, directory):
    require(bool(mapping), 'missing retained hash mapping')
    for name, expected in mapping.items():
        require(sha(inside(directory, name)) == expected, f'retained hash differs: {name}')


def validation(path, backend):
    result = read(path)
    require(result['status'] == result['cpu'] == result['proofs'] == 'passed', f'incomplete validation: {path}')
    if backend == 'cuda':
        require(result['cuda_build'] == result['gpu'] == result['gpu_memcheck'] == 'passed', 'GPU validation incomplete')
    else:
        require(result['gpu'] == 'not_run', 'CPU evidence unexpectedly claims GPU execution')
    for command in result['commands']:
        require(command['exit_code'] == 0, 'failed recorded validation command')
        inside(path.parent, command['log'])
    expected = {f'{r}_{a}_{mode}_{fringe}_{layout}_{access}' for (r, a), mode, fringe, layout, access in itertools.product(
        ((1, 1), (17, 257), (128, 1024)), ('provided', 'recurrent', 'shift-xor', 'shift-or'),
        ('off', 'on'), ('linear', 'morton8'), ('texture', 'texture-packed', 'global') if backend == 'cuda' else ('texture',))}
    normal = [run for run in result['runs'] if not run['path'].startswith('memcheck_')]
    memory = [run for run in result['runs'] if run['path'].startswith('memcheck_')]
    require(len(normal) == len(expected) and {run['path'] for run in normal} == expected, 'validation matrix coverage differs')
    require(len(memory) == (6 if backend == 'cuda' else 0), 'validation memcheck count differs')
    if memory:
        require({run['path'] for run in memory} == {f'memcheck_{layout}_{access}' for layout, access in itertools.product(
            ('linear', 'morton8'), ('texture', 'texture-packed', 'global'))}, 'memcheck coverage differs')
    for run in result['runs']:
        require(run['status'] == 'passed' and run['backend_recorded'] == backend, 'failed or wrong-backend reference receipt')
        directory = path.parent / run['path']
        summary = read(directory / 'summary.json')
        require(summary['candidate_verification'] == 'passed' and summary['backend'] == backend, 'candidate verification not passed')
        require(summary['committed_lane_epochs'] == run['lane_epochs'], 'committed/reference count differs')
        if run in normal:
            # Integrity only. Numerical recomputation and seal-chain verification
            # already completed inside tools/validate.py.
            check_hashes(read(directory / 'run_seal.json')['header']['files'], directory)
    proofs = read(path.parent / 'proofs.json')
    require(proofs['status'] == 'passed' and len(proofs['obligations']) == 15 and
            all(item['passed'] and item['observed'] == item['expected'] for item in proofs['obligations']), 'symbolic receipts incomplete')
    for item in proofs['obligations']:
        require(sha(ROOT / 'proofs' / item['file']) == item['sha256'], 'symbolic source differs')
    ctest = (path.parent / 'cpu_ctest.log').read_text(encoding='utf-8')
    python_tests = (path.parent / 'python_tests.log').read_text(encoding='utf-8')
    require('100% tests passed, 0 tests failed out of 7' in ctest, 'CTest receipt count differs')
    require(re.search(r'Ran 37 tests\b', python_tests) and re.search(r'^OK\s*$', python_tests, re.M), 'Python test receipt differs')
    contract_log = path.parent.parent / 'Testing/Temporary/LastTest.log'
    require('RESULT 32 groups; 134521 assertions passed' in contract_log.read_text(encoding='utf-8'), 'C++ contract receipt differs')
    return result, normal, memory


def study(path, expected_counts):
    result = read(path)
    require(result['status'] == result['raw_log_validation']['status'] == 'passed', f'incomplete study/audit: {path}')
    exe = Path(result['executable'])
    require(sha(exe) == result['executable_sha256'] == result['executable_sha256_after'] == EXPECTED_BULK, 'bulk executable identity differs')
    for category in ('source_hashes', 'audit_source_hashes'):
        require(result[category + '_before'] == result[category + '_after'], 'study source changed during execution')
        check_hashes(result[category + '_before'], ROOT)
    tasks, commands, samples = result['tasks'], result['commands'], result['samples']
    require(len(tasks) == len(commands) == len(samples) == result['raw_log_validation']['commands_checked'], 'incomplete study command/sample counts')
    require(dict(Counter(task['kind'] for task in tasks)) == expected_counts, 'selected study stage counts differ')
    for task, command, sample in zip(tasks, commands, samples):
        require(command['exit_code'] == 0 and sample['task'] == task, 'study command failed or task differs')
        inside(path.parent, command['stdout']); inside(path.parent, command['stderr'])
        require(all(receipt['status'] == receipt['candidate_verification'] == 'passed'
                    for receipt in sample['application_results']), 'study candidate receipt failed')
        if task['kind'] == 'profile':
            inside(path.parent, sample['csv'])
            require(sample['traffic_audit']['status'] == 'passed', 'traffic geometry audit failed')
            require(sample['traffic_audit']['excess_misses_over_cold_floor'] >= 0, 'invalid negative excess miss count')
        if task['kind'] == 'sanitizer':
            require(sample['sanitizer_audit']['status'] == 'passed' and sample['sanitizer_audit']['errors'] == 0, 'sanitizer audit failed')
        if task.get('export'):
            require(sample['python_export_verification']['status'] == sample['export_seal_verification']['status'] == 'passed', 'Python export audit incomplete')
            check_hashes(sample['export_file_hashes'], path.parent / task['export'])
    return result


def copy_verified(source, target, expected):
    require(sha(source) == expected, f'source binary hash changed: {source}')
    temporary = target.with_name(target.name + '.tmp')
    shutil.copy2(source, temporary)
    require(sha(temporary) == expected, f'copied binary hash differs: {target}')
    temporary.replace(target)


def main():
    cpu, cpu_runs, _ = validation(CPU, 'cpu')
    gpu, gpu_runs, gpu_memchecks = validation(GPU, 'cuda')
    main_study = study(MAIN, {'conformance': 192, 'export': 2, 'timing': 20, 'profile': 12})
    edge_study = study(EDGES, {'conformance': 20, 'profile': 12, 'sanitizer': 14})
    native = read(NATIVE)
    require(native['executable_unchanged_during_audit'] and native['executable_sha256'] == native['executable_sha256_after'] == EXPECTED_BULK, 'native binary receipt differs')
    require(all(command['exit_code'] == 0 for command in native['commands']), 'native tool command failed')
    check_hashes(native['source_hashes'], ROOT)
    require(native['source_hashes'] == main_study['source_hashes_before'] == edge_study['source_hashes_before'], 'native/study source identity differs')
    for artifact in native['artifacts'].values():
        require(sha(Path(artifact['path'])) == artifact['sha256'], 'native artifact hash differs')
    require(native['important_static_counts']['LDG'] == native['important_static_counts']['STG'] == 0 and
            native['resources']['registers_per_thread'] == 84 and native['resources']['local_bytes'] == native['resources']['stack_bytes'] == 0,
            'final native code/resources differ from reviewed result')
    require(native['comparison_to_folded_pre_export']['encoded_64bit_words_equal'], 'export changed reviewed kernel instructions')
    production = CACHE / 'gpu_fold_final/Release/atomos_cuda.exe'
    cpu_exe = CACHE / 'cpu_fold_final/Release/atomos_cpu.exe'
    bulk_exe = Path(main_study['executable'])
    require(sha(production) == EXPECTED_PRODUCTION and sha(cpu_exe) == EXPECTED_CPU, 'final production/CPU binary differs')
    require(sum(run['lane_epochs'] for run in cpu_runs) == 204000 and
            sum(run['lane_epochs'] for run in gpu_runs) == 612000 and
            sum(run['lane_epochs'] for run in gpu_runs + gpu_memchecks) == 614754, 'final validation lane-epoch counts differ')
    audit, edge_audit = main_study['raw_log_validation'], edge_study['raw_log_validation']
    require(audit['python_verified_export_runs'] == 26, 'independent bulk export count differs')
    require(edge_audit['sanitizer_runs'] == {'memcheck': 6, 'synccheck': 4, 'racecheck': 4}, 'bulk sanitizer coverage differs')
    profile_rows = []
    for source, report in (('main', main_study), ('edges', edge_study)):
        for sample in report['samples']:
            if sample['task']['kind'] == 'profile':
                profile_rows.append(dict(study=source, label=sample['task']['label'], context=sample['task']['context'], **sample['traffic_audit']))
    at_floor = sum(row['observed_cold_floor_reached'] for row in profile_rows)
    all_floor = at_floor == len(profile_rows)
    status = 'execution_validated_residency_observed' if all_floor else 'execution_validated_residency_partial'
    counts = dict(cpp_test_groups=32, cpp_assertions=134521, cpp_ctest_cases=7, python_unit_tests=37, symbolic_obligations=15,
        cpu_verified_runs=48, cpu_lane_epochs=204000, production_gpu_verified_runs=144,
        production_gpu_lane_epochs=612000, production_gpu_memchecks=6, production_gpu_runs_including_memcheck=150,
        production_gpu_lane_epochs_including_memcheck=614754, bulk_native_conformance_runs=192,
        bulk_additional_export_runs=2, bulk_python_verified_export_runs=26,
        bulk_python_verified_lane_epochs=audit['python_verified_lane_epochs'], bulk_unprofiled_timing_trials=20,
        bulk_cold_profile_samples=12, edge_native_conformance_runs=20, edge_cold_profile_samples=12,
        bulk_memchecks=6, bulk_syncchecks=4, bulk_racechecks=4, native_audits_passed=1,
        cold_profile_geometry_audits_passed=len(profile_rows), cold_profiles_at_compulsory_floor=at_floor,
        cold_profiles_above_compulsory_floor=len(profile_rows)-at_floor)
    limitations = [
        'Residency is measured in the explicit cooperative warm/work/post experiment across distributed SM-local caches; no hardware pinning or persistence across arbitrary later work is claimed.',
        'Whole-kernel counters include deliberate warming and retention probes. All phase, bulk-I/O, synchronization and diagnostic overhead is included in ordinary event timings.',
        'Passing conformance, sanitizer and traffic-geometry audits does not imply every workload reaches the cold miss floor. Every observed excess-miss profile is retained below.',
        'The constant change also changes register allocation; the evidence establishes the compiled change effect, not unique attribution of each avoided miss.',
        'Zero LDG/STG static sites does not mean zero global traffic: bulk transfers, generic synchronization loads, atomics and cache-control instructions remain.',
        'SMT obligations concern mathematical specifications, not compiler or GPU machine-code equivalence.',
        'The earlier 33.1% timing comparison belongs to historical production binary c2e551de and has not been rerun for the final production binary.']
    delivery = ROOT / 'output/bin'
    old_target = delivery / 'atomos_cuda.exe'
    archive = delivery / 'atomos_cuda_historical_c2e551de.exe'
    if old_target.exists():
        require(sha(old_target) in (OLD_PRODUCTION, EXPECTED_PRODUCTION), 'unexpected existing production delivery binary')
        if sha(old_target) == EXPECTED_PRODUCTION:
            require(archive.is_file() and sha(archive) == OLD_PRODUCTION, 'historical production archive missing')
    else:
        require(archive.is_file() and sha(archive) == OLD_PRODUCTION, 'historical production evidence unavailable')
    source_paths = []
    for folder in ('cuda', 'experiments', 'include', 'src', 'tools', 'tests', 'python', 'proofs', 'docs'):
        source_paths.extend(path for path in (ROOT / folder).rglob('*') if path.is_file() and path.suffix in ('.cu', '.hpp', '.cpp', '.py', '.md', '.json', '.csv', '.smt2'))
    source_paths.extend(ROOT / name for name in ('CMakeLists.txt', 'AUTHORSHIP.json', 'README.md', 'AGENTS.md'))
    source_manifest = dict(schema='atomOS-bulk-final-source-hashes', scope='Current unsigned source integrity manifest; the manifest itself is excluded.',
        files={path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(set(source_paths))})
    evidence_hashes = {}
    for directory in (CPU.parent, GPU.parent, MAIN.parent, EDGES.parent):
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                require(path.resolve().is_relative_to(directory.resolve()), 'external retained evidence link')
                evidence_hashes[str(path)] = sha(path)
    evidence_hashes[str(NATIVE)] = sha(NATIVE)
    prior_attempt = CACHE / 'bulk_final_study/study.json'
    prior_record = dict(path=str(prior_attempt), sha256=sha(prior_attempt), status=read(prior_attempt).get('status'),
                        scope='Historical first attempt; excluded from final passed evidence and counts.') if prior_attempt.exists() else None
    summary = dict(schema='atomOS-bulk-final-review-1', date=datetime.now(timezone.utc).date().isoformat(), status=status,
        cpu_validation_path=str(CPU), gpu_validation_path=str(GPU), bulk_study_path=str(MAIN), edge_study_path=str(EDGES), native_path=str(NATIVE),
        device=audit['execution_identity']['device'], executable=str(delivery / 'atomos_cache_bulk.exe'), executable_sha256=EXPECTED_BULK,
        production_executable=str(old_target), production_executable_sha256=EXPECTED_PRODUCTION,
        cpu_executable=str(delivery / 'atomos_cpu.exe'), cpu_executable_sha256=EXPECTED_CPU,
        historical_production_executable=str(archive), historical_production_executable_sha256=OLD_PRODUCTION,
        counts=counts, residency_scope=dict(status='observed_for_all_profiled_cases' if all_floor else 'partial_across_profiled_cases',
            all_profiled_cases_reached_compulsory_floor=all_floor, profiles_at_floor=at_floor, profiles_total=len(profile_rows),
            interpretation='Complete dictionary retention is assessed by measured cold compulsory misses through real verified work and a final probe; this is a tested-launch observation, not a cache-pinning guarantee.',
            profiles=profile_rows), limitations=limitations, aggregates=main_study['aggregates'],
        raw_audit_receipts=dict(main=audit, edges=edge_audit), prior_attempt=prior_record,
        max_gpu_reference_error_radians=max(run['max_float_difference_radians'] for run in gpu['runs']),
        source_manifest=str(E / 'source_sha256.json'), evidence_manifest=str(E / 'final_evidence_sha256.json'),
        packaging_scope='Saved pass/audit receipt and integrity validation only; no GPU launches or repeated numerical/profiler audits.')
    # All read-only checks completed before changing delivery/status artifacts.
    E.mkdir(parents=True, exist_ok=True); delivery.mkdir(parents=True, exist_ok=True)
    previous_status = E / 'pre_final_validation_status.json'
    if not previous_status.exists():
        shutil.copy2(STATUS, previous_status)
        require(sha(previous_status) == sha(STATUS), 'previous validation-status copy differs')
    if not archive.exists():
        copy_verified(old_target, archive, OLD_PRODUCTION)
    require(sha(archive) == OLD_PRODUCTION, 'historical production archive differs')
    for source, target, expected in ((production, old_target, EXPECTED_PRODUCTION),
        (bulk_exe, delivery / 'atomos_cache_bulk.exe', EXPECTED_BULK), (cpu_exe, delivery / 'atomos_cpu.exe', EXPECTED_CPU)):
        copy_verified(source, target, expected)
    current = read(STATUS)
    historical = {key: current.pop(key) for key in ('benchmark_configurations', 'benchmark_trials_per_configuration', 'profile_launch_samples', 'supplemental_gpu_memchecks') if key in current}
    if historical:
        current['historical_review_counts'] = dict(**historical, executable_sha256=OLD_PRODUCTION, scope='Earlier binary only; no final-binary benchmark rerun claimed.')
    current.update(status=status, cpp_test_groups=32, cpp_assertions=134521, cpp_tests='passed', cpu_ctest_cases=7,
        python_unit_tests=37, python_unit_status='passed', symbolic_obligations=15, symbolic_result='all_unsat',
        cpu_run_configurations=48, cpu_lane_epochs=204000, cuda_compilation='passed', gpu_execution='passed',
        gpu_run_configurations=144, gpu_lane_epochs=612000, gpu_lane_epochs_including_memcheck=614754,
        gpu_memcheck='passed', gpu_matrix_memchecks=6, gpu_device=gpu['device'],
        production_executable_sha256=EXPECTED_PRODUCTION, complete_texture_cache_residency=summary['residency_scope']['status'],
        max_gpu_reference_error_radians=summary['max_gpu_reference_error_radians'], bulk_final_review=dict(summary=str(E / 'summary.json'), status=status, counts=counts))
    current.setdefault('evidence', {}).update(cpu=str(CPU), gpu=str(GPU), bulk_final=str(E / 'summary.json'), bulk_study=str(MAIN), bulk_edges=str(EDGES), bulk_native=str(NATIVE))
    write(E / 'source_sha256.json', source_manifest)
    write(E / 'final_evidence_sha256.json', dict(scope='Retained evidence hashes captured at final packaging; not a signed attestation.', files=evidence_hashes))
    write(E / 'summary.json', summary)
    write(STATUS, current)
    print(json.dumps(dict(status=status, summary=str(E / 'summary.json'), counts=counts), indent=2))


if __name__ == '__main__':
    main()
