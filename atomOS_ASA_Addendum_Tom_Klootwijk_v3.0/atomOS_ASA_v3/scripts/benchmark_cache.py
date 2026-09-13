#!/usr/bin/env python3
"""Measure real texture-cache activity and repeated timings without altering outputs."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.reference import verify_directory
from scripts.integration import verify_execution_metadata

METRICS = (
    'l1tex__t_sector_pipe_tex_mem_texture_op_ld_hit_rate.pct',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_hit.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_miss.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld.sum',
    'l1tex__t_requests_pipe_tex_mem_texture_op_ld.sum',
)
AGGREGATE_METRIC = 'l1tex__t_sector_hit_rate.pct'
REQUESTED_METRICS = (*METRICS, AGGREGATE_METRIC)


def profiler_number(value: str, percentage: bool) -> float:
    # Percentages are ungrouped in 0..100; the other requested metrics are
    # integer counts. Accept Dutch and English separators without guessing
    # whether a decimal point in 67.82 is a thousands separator.
    if percentage:
        return float(value.replace(',', '.'))
    return float(value.replace('.', '').replace(',', ''))


def validate_metrics(metrics: dict) -> None:
    if not set(METRICS) <= set(metrics) <= set(REQUESTED_METRICS) or not all(math.isfinite(v) for v in metrics.values()):
        raise ValueError('missing or nonfinite texture metrics')
    percentage = metrics[METRICS[0]]
    if not 0 <= percentage <= 100:
        raise ValueError('invalid texture hit percentage')
    if AGGREGATE_METRIC in metrics and not 0 <= metrics[AGGREGATE_METRIC] <= 100:
        raise ValueError('invalid aggregate L1/TEX hit percentage')
    counts = [metrics[name] for name in METRICS[1:]]
    if any(v < 0 or v != int(v) for v in counts):
        raise ValueError('invalid texture sector/request count')
    hit, miss, total, requests = counts
    if total <= 0 or requests <= 0 or total != hit+miss or abs(percentage-100*hit/total) > .02:
        raise ValueError('texture counts disagree with hit percentage or show no texture work')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    parser.add_argument('--ncu', required=True, type=Path)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--samples', type=int, default=65536)
    parser.add_argument('--block-size', type=int, choices=(128,256,512,1024), default=256)
    parser.add_argument('--timing-runs', type=int, default=5)
    parser.add_argument('--profile-runs', type=int, default=3)
    args = parser.parse_args()
    if min(args.timing_runs, args.profile_runs) < 1:
        parser.error('repeat counts must be positive')
    report = args.report_dir.resolve()
    report.mkdir(parents=True, exist_ok=False)
    exe = args.executable.resolve()
    record = {'status': 'running', 'samples': args.samples, 'block_size': args.block_size,
              'binary_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
              'warmup_launches_per_path': 5, 'timed_launches_per_path': 30,
              'profile_cache_control': 'all', 'profile_clock_control': 'base',
              'profile_replay_mode': 'kernel', 'steps': [], 'conditions': {}}

    def run(label, command):
        command = list(map(str, command))
        started = time.perf_counter()
        done = subprocess.run(command, cwd=ROOT, text=True, encoding='utf-8', errors='replace',
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        elapsed = (time.perf_counter()-started)*1000
        (report/(label+'.log')).write_text(done.stdout, encoding='utf-8')
        record['steps'].append({'label': label, 'command': command, 'returncode': done.returncode,
                                'process_wall_ms': elapsed})
        if done.returncode:
            raise RuntimeError(f'{label} failed; see its log')
        return done.stdout, elapsed

    try:
        expected_results = None
        expected_samples = None
        for layout in ('linear', 'morton'):
            for order in ('natural', 'locality'):
                record['conditions'][layout+'_'+order] = {'timing': [], 'profiles': []}
        # Finish all unprofiled runs before clock-controlled profiling. Alternate
        # A/B and B/A within a layout to reduce time-order/thermal bias.
        for layout in ('linear', 'morton'):
            for n in range(args.timing_runs):
                for order in (('natural', 'locality') if n % 2 == 0 else ('locality', 'natural')):
                    label = layout+'_'+order
                    condition = record['conditions'][label]
                    base = [exe, '--samples', args.samples, '--layout', layout, '--sample-order', order, '--warmup', 5, '--block-size', args.block_size, '--l2-policy', 'normal']
                    name = label+f'_timing_{n}'
                    output = report/name
                    _, elapsed = run(name, [*base, '--repeat', 30, '--out', output])
                    meta = json.loads((output/'run.json').read_text())
                    verify_execution_metadata(meta, [str(v) for v in [*base[1:], '--repeat', 30]], True)
                    oracle = verify_directory(output)
                    results = (output/'results.bin').read_bytes()
                    samples = (output/'samples.f64x2').read_bytes()
                    if expected_results is None:
                        expected_results, expected_samples = results, samples
                    if results != expected_results or samples != expected_samples:
                        raise AssertionError('sample ordering or result bytes changed across benchmark conditions')
                    condition['timing'].append({'process_wall_ms': elapsed, 'run': meta, 'oracle': oracle})
        for layout in ('linear', 'morton'):
            for n in range(args.profile_runs):
                for order in (('natural', 'locality') if n % 2 == 0 else ('locality', 'natural')):
                    label = layout+'_'+order
                    condition = record['conditions'][label]
                    base = [exe, '--samples', args.samples, '--layout', layout, '--sample-order', order, '--warmup', 5, '--block-size', args.block_size, '--l2-policy', 'normal']
                    name = label+f'_profile_{n}'
                    output = report/name
                    stdout, _ = run(name, [args.ncu.resolve(), '--metrics', ','.join(REQUESTED_METRICS),
                                           '--cache-control', 'all', '--clock-control', 'base',
                                           '--replay-mode', 'kernel', '--kernel-name', 'regex:asa_texture_kernel',
                                           '--launch-skip', 5, '--launch-count', 1, '--csv', '--print-units', 'base',
                                           *base, '--repeat', 1, '--out', output])
                    rows = list(csv.DictReader(io.StringIO(stdout[stdout.index('"ID","Process ID"'):])))
                    if len(rows) != len(REQUESTED_METRICS):
                        raise RuntimeError('profiler did not emit exactly one row per metric')
                    metrics = {row['Metric Name']: profiler_number(row['Metric Value'], row['Metric Unit']=='%') for row in rows}
                    if set(metrics) != set(REQUESTED_METRICS):
                        raise RuntimeError('profiler metric names do not match the requested set')
                    validate_metrics(metrics)
                    meta = json.loads((output/'run.json').read_text())
                    verify_execution_metadata(meta, [str(v) for v in [*base[1:], '--repeat', 1]], True)
                    oracle = verify_directory(output)
                    if (output/'results.bin').read_bytes() != expected_results or (output/'samples.f64x2').read_bytes() != expected_samples:
                        raise AssertionError('profiled sample order or result differs from natural output')
                    condition['profiles'].append({'metrics': metrics, 'oracle': oracle})
        for condition in record['conditions'].values():
            condition['summary'] = {
                    'process_wall_ms_median': statistics.median(x['process_wall_ms'] for x in condition['timing']),
                    'texture_compute_ms_median': statistics.median(x['run']['compute_ms'] for x in condition['timing']),
                    'global_compute_ms_median': statistics.median(x['run']['global_mean_ms'] for x in condition['timing']),
                    'reorder_ms_median': statistics.median(x['run']['reorder_ms'] for x in condition['timing']),
                    'restore_ms_median': statistics.median(x['run']['restore_ms'] for x in condition['timing']),
                    'texture_hit_pct_median': statistics.median(x['metrics'][METRICS[0]] for x in condition['profiles']),
                    'aggregate_l1tex_hit_pct_median': statistics.median(x['metrics'][AGGREGATE_METRIC] for x in condition['profiles']),
                    'texture_hit_pct_range': [min(x['metrics'][METRICS[0]] for x in condition['profiles']), max(x['metrics'][METRICS[0]] for x in condition['profiles'])],
                    'texture_miss_sectors_median': statistics.median(x['metrics'][METRICS[2]] for x in condition['profiles']),
                    'texture_requested_sectors_median': statistics.median(x['metrics'][METRICS[3]] for x in condition['profiles']),
                    'texture_requests_median': statistics.median(x['metrics'][METRICS[4]] for x in condition['profiles']),
                }
        if hashlib.sha256(exe.read_bytes()).hexdigest() != record['binary_sha256']:
            raise RuntimeError('executable changed during the benchmark')
        record['status'] = 'pass'
        record['all_results_and_sample_order_exact'] = True
    except Exception as error:
        record['status'] = 'fail'
        record['error'] = str(error)
        raise
    finally:
        (report/'benchmark.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v['summary'] for k,v in record['conditions'].items()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
