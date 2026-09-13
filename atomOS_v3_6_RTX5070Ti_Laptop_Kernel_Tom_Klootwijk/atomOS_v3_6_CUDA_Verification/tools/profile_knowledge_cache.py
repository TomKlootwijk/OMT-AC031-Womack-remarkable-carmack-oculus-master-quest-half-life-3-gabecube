"""Measure four cold texture-cache profiles for a small immutable knowledge bank.

Every run verifies its native chain and complete physical pool initialization,
readback, warm sweep and reread. Extra misses are recorded honestly. Results are
within-launch observations, not permanent residency or cache-pinning guarantees.
Profiler-perturbed timings are never labeled ordinary kernel benchmark timings.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from program_bank_reference import decode_bank
from profile_cache import METRICS, parse_metrics, read_log, resolve_ncu
from validate_knowledge_bank import STUDY_SOURCES, require_unchanged, verify_native


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def verify_pool(receipt, bank, physical_page_bytes):
    """Full-pool footprint follows the padded texture storage, not file size."""
    pool_bytes = bank['capsule_count'] * physical_page_bytes
    expected = dict(texture_sweep='full_pool', distinct_programs=bank['capsule_count'],
                    pool_slots=bank['capsule_count'], replicas_per_program=1,
                    program_page_bytes=physical_page_bytes,
                    logical_program_page_bytes=bank['rows'] * bank['angles'] // 8,
                    pool_bytes=pool_bytes, pool_initialized_bytes=pool_bytes,
                    pool_verified_bytes=pool_bytes, program_texture_swept_bytes=pool_bytes,
                    program_sweep_reads=pool_bytes // 2, operator_texture_bytes=1024,
                    operator_sweep_reads=128, rows=bank['rows'], angles=bank['angles'],
                    texture_inputs_mutated_during_launch=False,
                    native_executor_changed_during_run=False, cache_pinning=False)
    for key, wanted in expected.items():
        if type(receipt.get(key)) is not type(wanted) or receipt[key] != wanted:
            raise ValueError('complete pool/sweep receipt mismatch: ' + key)
    for first, last in [('operator_warm', 'operator_reread'), ('program_warm', 'program_reread')]:
        if first not in receipt or last not in receipt or receipt[first] != receipt[last]:
            raise ValueError('warm/reread checksum mismatch: ' + first)
    footprint = pool_bytes + receipt['operator_texture_bytes']
    # Native texture rows/pages and uint4 operator allocation are sector-aligned.
    if physical_page_bytes % 32 or pool_bytes % 32 or receipt['operator_texture_bytes'] % 32:
        raise ValueError('texture footprint is not aligned to complete 32-byte sectors')
    floor = (footprint + 31) // 32
    if (receipt.get('unique_texture_footprint_bytes') != footprint or
            receipt.get('unique_texture_sector_floor') != floor):
        raise ValueError('native unique texture footprint disagrees with independent padded extent')
    return dict(physical_program_page_bytes=physical_page_bytes, complete_pool_bytes=pool_bytes,
                operator_bytes=receipt['operator_texture_bytes'], unique_texture_footprint_bytes=footprint,
                compulsory_miss_floor=floor)


def profile(*, exe, bank_path, atlas, out, initial_slot=4):
    exe, bank_path, atlas, out = [Path(p).resolve() for p in (exe, bank_path, atlas, out)]
    if out.exists():
        raise ValueError('refusing to overwrite cache study evidence')
    manifest_path = bank_path.parent / 'manifest.json'
    sources = sorted(set(STUDY_SOURCES + ['tools/profile_knowledge_cache.py', 'tools/profile_cache.py',
                      'tools/validate_knowledge_bank.py', 'tools/validate.py', 'python/knowledge_admission.py']))
    bindings = {str(path): sha(path) for path in [exe, bank_path, manifest_path, atlas] + [ROOT / name for name in sources]}
    bank = decode_bank(bank_path, manifest_path)
    if type(initial_slot) is not int or not 0 <= initial_slot < bank['capsule_count']:
        raise ValueError('initial slot outside immutable bank')
    padded_rows = ((bank['rows'] + 7) // 8) * 8
    padded_words = (((bank['angles'] // 32) + 7) // 8) * 8
    physical_page_bytes = padded_rows * padded_words * 4
    if bank['capsule_count'] * physical_page_bytes > 1 << 20:
        raise ValueError('this complete-pool study is bounded to the native one-MiB full-sweep profile')
    value = min(7, (1 << bank['capsules'][initial_slot]['input_bits']) - 1)
    hops = 24
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema='atomos-knowledge-cold-cache-study-v1', status='running',
                  started_at_utc=datetime.now(timezone.utc).isoformat(),
                  scope='four within-launch full-pool cold texture-cache measurements; immutable chained programs',
                  initial_slot=initial_slot, input_initial=value, hops=hops,
                  bank_sha256=bindings[str(bank_path)], manifest_sha256=bindings[str(manifest_path)],
                  executable_sha256=bindings[str(exe)], atlas_sha256=bindings[str(atlas)],
                  dependency_sha256=bindings, native_runs=0, runs=[],
                  cache_pinning=False, permanent_residency='not_claimed',
                  timing_scope='Nsight-perturbed native events and profiler duration only; no ordinary timing benchmark',
                  extra_misses_policy='record observed additional misses; they do not invalidate independently correct execution')
    def retain():
        save(out / 'cache_study.json', report)
    retain()
    ncu = resolve_ncu(None)
    if ncu is None:
        report.update(status='not_run', reason='Nsight Compute executable unavailable', gpu_execution='not_run')
        retain()
        return report
    bindings[str(ncu)] = sha(ncu)
    report['profiler_executable'] = str(ncu)
    try:
        for layout in ('linear', 'morton8'):
            for repeat in range(2):
                require_unchanged(bindings)
                label = f'cold_{layout}_{repeat}'
                folder, counters = out / label, out / (label + '.counters.log')
                command = [str(ncu), '--replay-mode', 'kernel', '--cache-control', 'all', '--clock-control', 'none',
                           '--kernel-name', 'regex:atomos_program_bank', '--launch-count', '1', '--check-exit-code', '1',
                           '--metrics', ','.join(METRICS), '--csv', '--page', 'raw', '--print-units', 'base',
                           '--log-file', str(counters), str(exe), '--bank', str(bank_path), '--atlas', str(atlas),
                           '--layout', layout, '--mode', 'chain', '--initial-slot', str(initial_slot),
                           '--input', str(value), '--hops', str(hops), '--inject', 'none',
                           '--reserve-mib', '1536', '--sweep-limit-mib', '1', '--out', str(folder)]
                print(json.dumps(dict(profile=label, status='running')), flush=True)
                started = time.perf_counter()
                with (out / (label + '.log')).open('w', encoding='utf-8') as log:
                    completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                record = dict(label=label, layout=layout, repeat=repeat, command=command,
                              exit_code=completed.returncode, wall_seconds=time.perf_counter() - started)
                report['runs'].append(record)
                report['native_runs'] = len(report['runs'])
                retain()
                if completed.returncode:
                    raise RuntimeError('native/profiler execution failed: ' + label)
                require_unchanged(bindings)
                verified = verify_native(folder, bank, bank_hash=bindings[str(bank_path)], atlas_hash=bindings[str(atlas)],
                                         layout=layout, mode='chain', first=initial_slot, value=value, hops=hops)
                receipt = verified['receipt']
                footprint = verify_pool(receipt, bank, physical_page_bytes)
                metrics = parse_metrics(read_log(counters), METRICS)
                record.update(receipt=receipt, independent_trace=verified['verification'], metrics=metrics, **footprint)
                retain()
                if any(metric.get('status') != 'collected' for metric in metrics.values()):
                    raise ValueError('required cache metric unavailable or not from exactly one profiled launch')
                sectors, hits, misses = [metrics[METRICS[i]]['value'] for i in (1, 2, 3)]
                if hits + misses != sectors or misses < footprint['compulsory_miss_floor']:
                    raise ValueError('texture-sector conservation or compulsory-miss lower bound failed')
                with (folder / 'trace.csv').open(encoding='utf-8', newline='') as stream:
                    visited = sorted({int(row['program_id']) for row in csv.DictReader(stream)})
                record.update(extra_misses=misses - footprint['compulsory_miss_floor'],
                              at_compulsory_floor=misses == footprint['compulsory_miss_floor'],
                              program_slots_executed=visited,
                              complete_pool_pages_swept=bank['capsule_count'],
                              profiler_perturbed_kernel_ms=receipt['kernel_ms'],
                              profiler_gpu_duration_ns=metrics[METRICS[4]]['value'], status='measured_and_verified')
                save(folder / 'PYTHON_VERIFIED.json', verified['verification'])
                retain()
                # Freeze completed raw outputs as well as the actual input files.
                bindings.update({str(path): sha(path) for path in folder.rglob('*') if path.is_file()})
                bindings[str(counters)] = sha(counters)
                bindings[str(out / (label + '.log'))] = sha(out / (label + '.log'))
                print(json.dumps(dict(profile=label, status=record['status'], extra_misses=record['extra_misses'])), flush=True)
        require_unchanged(bindings)
        report.update(status='passed', gpu_execution='run_and_independently_verified',
                      profiles_at_compulsory_floor=sum(run['at_compulsory_floor'] for run in report['runs']),
                      all_profiles_at_compulsory_floor=all(run['at_compulsory_floor'] for run in report['runs']),
                      observed_extra_misses=[run['extra_misses'] for run in report['runs']],
                      accepted_program_evaluations=len(report['runs']) * hops,
                      finished_at_utc=datetime.now(timezone.utc).isoformat())
        retain()
        return report
    except Exception as error:
        report.update(status='failed', reason=str(error), finished_at_utc=datetime.now(timezone.utc).isoformat())
        retain()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('exe', 'bank', 'atlas', 'out'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--initial-slot', type=int, default=4)
    args = parser.parse_args()
    result = profile(exe=args.exe, bank_path=args.bank, atlas=args.atlas, out=args.out, initial_slot=args.initial_slot)
    print(json.dumps(dict(status=result['status'], native_runs=result['native_runs'],
                          all_profiles_at_compulsory_floor=result.get('all_profiles_at_compulsory_floor'),
                          study=str(args.out / 'cache_study.json'))))
    return 3 if result['status'] == 'not_run' else 0


if __name__ == '__main__':
    raise SystemExit(main())
