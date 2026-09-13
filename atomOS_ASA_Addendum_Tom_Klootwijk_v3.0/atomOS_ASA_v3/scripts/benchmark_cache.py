#!/usr/bin/env python3
"""Measure real texture-cache activity and repeated timings without altering outputs."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.reference import verify_directory

METRICS = (
    'l1tex__t_sector_pipe_tex_mem_texture_op_ld_hit_rate.pct',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_hit.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_miss.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld.sum',
    'l1tex__t_requests_pipe_tex_mem_texture_op_ld.sum',
)


def profiler_number(value: str, percentage: bool) -> float:
    # Percentages are ungrouped in 0..100; the other requested metrics are
    # integer counts. Accept Dutch and English separators without guessing
    # whether a decimal point in 67.82 is a thousands separator.
    if percentage:
        return float(value.replace(',', '.'))
    return float(value.replace('.', '').replace(',', ''))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    parser.add_argument('--ncu', required=True, type=Path)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--samples', type=int, default=65536)
    parser.add_argument('--timing-runs', type=int, default=5)
    parser.add_argument('--profile-runs', type=int, default=3)
    args = parser.parse_args()
    if min(args.timing_runs, args.profile_runs) < 1:
        parser.error('repeat counts must be positive')
    report = args.report_dir.resolve()
    report.mkdir(parents=True, exist_ok=False)
    exe = args.executable.resolve()
    record = {'status': 'running', 'samples': args.samples,
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
                label = layout+'_'+order
                condition = {'timing': [], 'profiles': []}
                record['conditions'][label] = condition
                base = [exe, '--samples', args.samples, '--layout', layout, '--sample-order', order, '--warmup', 5]
                for n in range(args.timing_runs):
                    name = label+f'_timing_{n}'
                    output = report/name
                    _, elapsed = run(name, [*base, '--repeat', 30, '--out', output])
                    meta = json.loads((output/'run.json').read_text())
                    oracle = verify_directory(output)
                    results = (output/'results.bin').read_bytes()
                    samples = (output/'samples.f64x2').read_bytes()
                    if expected_results is None:
                        expected_results, expected_samples = results, samples
                    if results != expected_results or samples != expected_samples:
                        raise AssertionError('sample ordering or result bytes changed across benchmark conditions')
                    condition['timing'].append({'process_wall_ms': elapsed, 'run': meta, 'oracle': oracle})
                for n in range(args.profile_runs):
                    name = label+f'_profile_{n}'
                    output = report/name
                    stdout, _ = run(name, [args.ncu.resolve(), '--metrics', ','.join(METRICS),
                                           '--cache-control', 'all', '--clock-control', 'base',
                                           '--replay-mode', 'kernel', '--kernel-name', 'regex:asa_texture_kernel',
                                           '--launch-skip', 5, '--launch-count', 1, '--csv',
                                           *base, '--repeat', 1, '--out', output])
                    rows = list(csv.DictReader(io.StringIO(stdout[stdout.index('"ID","Process ID"'):])) )
                    metrics = {row['Metric Name']: profiler_number(row['Metric Value'], row['Metric Unit']=='%') for row in rows}
                    if set(metrics) != set(METRICS):
                        raise RuntimeError('profiler did not emit every requested texture-only metric')
                    total = metrics[METRICS[3]]
                    hit, miss = metrics[METRICS[1]], metrics[METRICS[2]]
                    if total != hit+miss or abs(metrics[METRICS[0]]-100*hit/total) > .02:
                        raise RuntimeError('profiler sector counts disagree with hit percentage; check locale parsing')
                    oracle = verify_directory(output)
                    if (output/'results.bin').read_bytes() != expected_results:
                        raise AssertionError('profiled result differs from natural output')
                    condition['profiles'].append({'metrics': metrics, 'oracle': oracle})
                condition['summary'] = {
                    'process_wall_ms_median': statistics.median(x['process_wall_ms'] for x in condition['timing']),
                    'texture_compute_ms_median': statistics.median(x['run']['compute_ms'] for x in condition['timing']),
                    'texture_hit_pct_median': statistics.median(x['metrics'][METRICS[0]] for x in condition['profiles']),
                    'texture_hit_pct_range': [min(x['metrics'][METRICS[0]] for x in condition['profiles']), max(x['metrics'][METRICS[0]] for x in condition['profiles'])],
                    'texture_miss_sectors_median': statistics.median(x['metrics'][METRICS[2]] for x in condition['profiles']),
                    'texture_requested_sectors_median': statistics.median(x['metrics'][METRICS[3]] for x in condition['profiles']),
                    'texture_requests_median': statistics.median(x['metrics'][METRICS[4]] for x in condition['profiles']),
                }
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
