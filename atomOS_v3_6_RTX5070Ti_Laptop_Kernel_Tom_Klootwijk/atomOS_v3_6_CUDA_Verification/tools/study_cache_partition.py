#!/usr/bin/env python3
"""Validate and measure the standalone warm/work/retention partition experiment.

Every epoch remains host-verified before commit. All warming, work, probing,
barriers and diagnostic stores are included in timing. Successful conformance
does not assert a cache hit rate or hardware cache pinning.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time

from profile_cache import parse_metrics, read_log, resolve_ncu
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from reference import address, verify_execution_metadata

DEFAULT_EXE = Path('C:/Users/Tom/.cache/ak1/gpu128/Release/atomos_cache_partition.exe')
SOURCES = ('experiments/cache_partition.cu', 'cuda/kernel.cu', 'include/atomos/host.hpp', 'include/atomos/core.hpp')
METRICS = (
    'l1tex__t_requests_pipe_tex_mem_texture_op_ld.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_hit.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_miss.sum',
    'l1tex__t_sectors_pipe_lsu_mem_global_op_ld.sum',
    'l1tex__t_sectors_pipe_lsu_mem_global_op_ld_lookup_miss.sum',
    'dram__bytes_read.sum', 'gpu__time_duration.sum',
)
SIZES = {'default': (128, 1024), 'max': (512, 16384)}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {name: digest(ROOT / name) for name in SOURCES}


def exact(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def context(rows, angles, layout, epochs=3, barrier='grid', io='cg'):
    if any(type(v) is not int for v in (rows, angles, epochs)) or not (1 <= rows <= 65536 and 1 <= angles <= 65536 and 1 <= epochs <= 16):
        raise ValueError('invalid experiment dimensions/epochs')
    if layout not in ('linear', 'morton8'):
        raise ValueError('invalid experiment layout')
    if barrier not in ('grid', 'block'):
        raise ValueError('invalid experiment barrier')
    if io not in ('cg', 'no-allocate'):
        raise ValueError('invalid experiment I/O policy')
    words = (angles + 31) // 32
    atlas = ((rows + 7) // 8 * 8) * ((words + 7) // 8 * 8)
    if atlas > 2**18 or rows * words * epochs > 2**20:
        raise ValueError('experiment atlas/lane-epoch cap')
    return dict(rows=rows, angles=angles, layout=layout, epochs=epochs, barrier=barrier, io=io)


@lru_cache(maxsize=32)
def traffic_geometry(rows, angles, layout):
    context(rows, angles, layout, 1)
    words = (angles + 31) // 32
    padded_rows, padded_words = (rows + 7) // 8 * 8, (words + 7) // 8 * 8
    atlas, logical = padded_rows * padded_words, rows * words
    if rows == padded_rows and words == padded_words:
        work_requests, work_sectors = atlas // 32, atlas // 2
    else:
        # Partition boundaries are aligned to 32 uint4 texels. Consequently,
        # physical k//32 identifies each warp fetch, and k//2 its 32-byte sector.
        positions = [address(r, w, padded_words, layout) for r in range(rows) for w in range(words)]
        work_requests, work_sectors = len({k // 32 for k in positions}), len({k // 2 for k in positions})
    return dict(stored_texels=atlas, logical_texels=logical, mask_bytes=16 * atlas,
                warm_texel_reads_per_epoch=atlas, work_texel_reads_per_epoch=logical,
                post_texel_reads_per_epoch=atlas, expected_total_texel_reads_per_epoch=2 * atlas + logical,
                expected_texture_requests=2 * (atlas // 32) + work_requests,
                expected_texture_sectors=atlas + work_sectors,
                cold_warm_sector_floor=atlas // 2,
                base_payload_bytes=16 * atlas + 256 * logical)


def validate_result(result, c, expected_device=None):
    if not isinstance(result, dict):
        raise ValueError('application result must be an object')
    if result.get('control', 'epoch') != 'epoch':
        raise ValueError('retention-only control cannot replace the actual K1 epoch workload')
    fields = ('rows', 'angles', 'epochs', 'seed', 'block_size', 'grid_blocks', 'multiprocessors',
              'active_blocks_per_sm_limit', 'registers_per_thread', 'local_bytes_per_thread',
              'static_shared_bytes', 'preferred_shared_carveout', 'stored_texels', 'logical_texels',
              'chunk_texels', 'maximum_assigned_mask_bytes', 'warm_texel_reads_per_epoch',
              'work_texel_reads_per_epoch', 'post_texel_reads_per_epoch', 'expected_total_texel_reads_per_epoch',
              'mask_bytes', 'payload_bytes', 'diagnostic_bytes', 'planned_bytes', 'verified_lane_epochs',
              'checksum_components', 'checksum_disagreements', 'setup_launches')
    if any(type(result.get(key)) is not int for key in fields):
        raise ValueError('integer partition metadata required')
    fixed = dict(status='passed', scope='experimental_partition_warm_work_retention_probe',
                 mode='recurrent', fringe=True, profile='mixed', seed=130, block_size=512,
                 active_blocks_per_sm_limit=1, max_l1_requested=True, preferred_shared_carveout=0,
                 checksum_components=4, checksum_scheme='per_thread_componentwise_xor',
                 checksum_disagreements=0, candidate_verification='passed', sm_mapping_verified=True,
                 setup_launches=1, setup_launch_verified=True,
                 host_state_committed=True, setup_checksum_verified=True,
                 io_cache_policy_scope='explicit_lane_state_result_checksum_smid_accesses', io_cache_policy_is_hint=True,
                 timing_scope='entire_warm_work_probe_kernel_including_barriers_and_diagnostic_stores', **c)
    if any(not exact(result.get(key), value) for key, value in fixed.items()):
        raise ValueError('partition execution context/checksum/verification metadata differs')
    sm = result['multiprocessors']
    if sm <= 0 or result['grid_blocks'] != sm or result['registers_per_thread'] <= 0 or result['local_bytes_per_thread'] < 0 or result['static_shared_bytes'] < 0:
        raise ValueError('invalid partition resource geometry')
    geometry = traffic_geometry(c['rows'], c['angles'], c['layout'])
    atlas, logical = geometry['stored_texels'], geometry['logical_texels']
    chunk = ((atlas + sm * 32 - 1) // (sm * 32)) * 32
    diagnostics = 2 * (sm * 512) * 16 + 2 * sm * 4
    expected = {key: value for key, value in geometry.items() if key in result}
    expected.update(chunk_texels=chunk, maximum_assigned_mask_bytes=min(chunk, atlas) * 16,
                    diagnostic_bytes=diagnostics, payload_bytes=geometry['base_payload_bytes'] + diagnostics,
                    planned_bytes=geometry['base_payload_bytes'] + diagnostics + 64 * 2**20,
                    verified_lane_epochs=logical * c['epochs'])
    if any(result.get(key) != value for key, value in expected.items()):
        raise ValueError('partition coverage/traffic/payload metadata differs from independent geometry')
    if result['planned_bytes'] > 512 * 2**20:
        raise ValueError('partition plan exceeds fixed experiment budget')
    mappings = result.get('sm_mappings')
    if not isinstance(mappings, list) or len(mappings) != c['epochs'] + 1:
        raise ValueError('missing setup/epoch SM mappings')
    for launch, mapping in enumerate(mappings):
        if not isinstance(mapping, dict) or type(mapping.get('launch')) is not int or mapping['launch'] != launch or not exact(mapping.get('setup'), launch == 0):
            raise ValueError('SM mapping launch identity differs')
        before, after = mapping.get('before'), mapping.get('after')
        if not isinstance(before, list) or not isinstance(after, list) or len(before) != sm or len(after) != sm:
            raise ValueError('SM mapping count differs')
        # Physical SM IDs can be sparse: do not bound them by SM count.
        if any(type(value) is not int or not 0 <= value < 0xffffffff for value in before + after):
            raise ValueError('invalid/unwritten physical SM identifier')
        if before != after or len(set(before)) != sm:
            raise ValueError('SM mapping changed or multiple blocks occupied one observed SM')
    times = result.get('compute_ms')
    if not isinstance(times, list) or len(times) != c['epochs'] or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in times):
        raise ValueError('invalid partition epoch timings')
    verify_execution_metadata(dict(backend='cuda', read='texture-packed', device=result.get('device'), candidate_verification='passed'), expected_device=expected_device)
    return result


def application_results(raw, c, allow_replay=False, expected_device=None):
    decoder = json.JSONDecoder()
    results, position, device = [], 0, expected_device
    while True:
        start = raw.find('{', position)
        if start < 0:
            break
        try:
            result, length = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError as exc:
            raise ValueError('malformed application JSON in stdout') from exc
        validate_result(result, c, device)
        device = result['device'] if device is None else device
        results.append(result)
        position = start + length
    if not results or (not allow_replay and len(results) != 1):
        raise ValueError('missing or unexpected duplicate application result')
    return results


def validate_traffic(metrics, c):
    if set(metrics) != set(METRICS) or any(record.get('status') != 'collected' or type(record.get('value')) is not int or record['value'] < 0 for record in metrics.values()):
        raise ValueError('required profiling counter unavailable or invalid')
    geometry = traffic_geometry(c['rows'], c['angles'], c['layout'])
    requests, sectors, hits, misses = (metrics[name]['value'] for name in METRICS[:4])
    if requests < geometry['expected_texture_requests'] or sectors < geometry['expected_texture_sectors']:
        raise ValueError('actual texture request/sector totals fall below the three-phase geometry minimum')
    if hits + misses != sectors:
        raise ValueError('texture hits plus misses do not equal measured sectors')
    if metrics[METRICS[5]]['value'] > metrics[METRICS[4]]['value']:
        raise ValueError('LSU misses exceed LSU sectors')
    if metrics[METRICS[-1]]['unit'] not in ('ns', 'nsecond'):
        raise ValueError('profiler GPU duration must be in base nanoseconds')
    return dict(status='passed', expected_texture_requests=geometry['expected_texture_requests'],
                expected_texture_sectors=geometry['expected_texture_sectors'], actual_texture_requests=requests,
                actual_texture_sectors=sectors, actual_lookup_hits=hits, actual_lookup_misses=misses,
                excess_texture_requests=requests-geometry['expected_texture_requests'],
                excess_texture_sectors=sectors-geometry['expected_texture_sectors'],
                geometry_check='actual traffic is at least the independently computed nominal minimum; excess requests/sectors retained',
                lookup_hit_fraction=hits / sectors if sectors else None,
                cold_warm_sector_floor=geometry['cold_warm_sector_floor'],
                interpretation='Three-phase aggregate including initial warming; hit distribution across phases and permanent residency are not established by this check.')


def task_plan(layouts, sizes, timing_trials, profile_trials, validation_only, barrier='grid', explicit_control=False, io='cg'):
    tasks = []
    for rows, angles in ((1, 1), (17, 257), SIZES['default'], SIZES['max']):
        for layout in layouts:
            tasks.append(dict(kind='conformance', label=f'conformance_{rows}_{angles}_{layout}', context=context(rows, angles, layout, barrier=barrier, io=io)))
    if validation_only:
        return [dict(task, explicit_control=explicit_control) for task in tasks]
    selected = [(size, layout) for size in sizes for layout in layouts]
    for trial in range(timing_trials):
        order = list(selected)
        random.Random(20260913 + trial).shuffle(order)
        for size, layout in order:
            tasks.append(dict(kind='timing', label=f'time_{trial}_{size}_{layout}', trial=trial, size=size, context=context(*SIZES[size], layout, barrier=barrier, io=io)))
    for size, layout in selected:
        for trial in range(profile_trials):
            tasks.append(dict(kind='profile', label=f'cold_{trial}_{size}_{layout}', trial=trial, size=size, context=context(*SIZES[size], layout, epochs=1, barrier=barrier, io=io)))
    return [dict(task, explicit_control=explicit_control) for task in tasks]


def command_for(task, exe, ncu, out):
    c = task['context']
    application = [str(exe), '--rows', str(c['rows']), '--angles', str(c['angles']), '--epochs', str(c['epochs']), '--layout', c['layout'], '--barrier', c['barrier'], '--io', c['io']]
    if task.get('explicit_control'):
        application += ['--control', 'epoch']
    if task['kind'] != 'profile':
        return application
    return [str(ncu), '--replay-mode', 'kernel', '--cache-control', 'all', '--clock-control', 'none',
            '--launch-skip', '1', '--launch-count', '1', '--check-exit-code', '1', '--metrics', ','.join(METRICS),
            '--csv', '--page', 'raw', '--print-units', 'base', '--log-file', str(out / (task['label'] + '.csv.log')), *application]


def retained_path(out, name):
    if not isinstance(name, str):
        raise ValueError('invalid retained path')
    path = (out / name).resolve()
    if not path.is_relative_to(out) or not path.is_file():
        raise ValueError('missing or out-of-directory retained evidence')
    return path


def sample_from_logs(task, command, out, expected_device=None):
    if type(command.get('exit_code')) is not int or command['exit_code'] != 0:
        raise ValueError('profiler/application command did not exit successfully')
    retained_path(out, command['stderr'])
    receipts = application_results(read_log(retained_path(out, command['stdout'])), task['context'], task['kind'] == 'profile', expected_device)
    sample = dict(task=task, application_results=receipts)
    if task['kind'] == 'timing':
        sample['median_ms'] = statistics.median(receipts[0]['compute_ms'])
    if task['kind'] == 'profile':
        csv_path = retained_path(out, task['label'] + '.csv.log')
        sample['csv'] = csv_path.name
        sample['metrics'] = parse_metrics(read_log(csv_path), METRICS)
        sample['traffic_audit'] = validate_traffic(sample['metrics'], task['context'])
    return sample


def aggregates(report):
    result = []
    for size in report['selection']['sizes']:
        for layout in report['selection']['layouts']:
            samples = [s for s in report['samples'] if s['task'].get('size') == size and s['task']['context']['layout'] == layout]
            times = [s['median_ms'] for s in samples if s['task']['kind'] == 'timing']
            profiles = [s for s in samples if s['task']['kind'] == 'profile']
            if not times and not profiles:
                continue
            if len(times) != report['selection']['timing_trials'] or len(profiles) != report['selection']['profile_trials']:
                raise ValueError('incomplete selected repetitions')
            for name in METRICS:
                if len({sample['metrics'][name]['unit'] for sample in profiles}) != 1:
                    raise ValueError('profile units differ across repetitions')
            result.append(dict(size=size, layout=layout, median_ms=statistics.median(times), min_ms=min(times), max_ms=max(times),
                metrics={name: dict(min=min(s['metrics'][name]['value'] for s in profiles), median=statistics.median(s['metrics'][name]['value'] for s in profiles),
                                   max=max(s['metrics'][name]['value'] for s in profiles), unit=profiles[0]['metrics'][name]['unit']) for name in METRICS}))
    return result


def audit_raw(report, out, exe):
    selection = report['selection']
    tasks = task_plan(**selection)
    if not exact(report.get('tasks'), tasks) or len(report.get('commands', [])) != len(tasks) or len(report.get('samples', [])) != len(tasks):
        raise ValueError('saved study task/command/sample coverage differs')
    if Path(report['executable']).resolve() != exe:
        raise ValueError('saved executable path differs')
    device, count = None, 0
    for task, command, saved in zip(tasks, report['commands'], report['samples']):
        if not exact(command['command'], command_for(task, exe, report['profiler_executable'], out)):
            raise ValueError('saved command differs from planned workload/profiling conditions')
        if command['stdout'] != task['label'] + '.stdout.log' or command['stderr'] != task['label'] + '.stderr.log':
            raise ValueError('retained command log identity differs')
        actual = sample_from_logs(task, command, out, device)
        if not exact(saved, actual):
            raise ValueError('saved sample differs from raw application output/counters')
        device = actual['application_results'][0]['device'] if device is None else device
        count += len(actual['application_results'])
    if not exact(report.get('aggregates'), aggregates(report)):
        raise ValueError('saved aggregates differ from retained samples')
    return dict(status='passed', commands_checked=len(tasks), application_json_receipts=count,
                conformance_runs=sum(t['kind'] == 'conformance' for t in tasks), timing_runs=sum(t['kind'] == 'timing' for t in tasks),
                profile_runs=sum(t['kind'] == 'profile' for t in tasks), device=device)


def audit_existing(exe, out):
    audit = dict(schema='atomOS-cache-partition-audit', status='running', created_at_utc=datetime.now(timezone.utc).isoformat(),
                 scope='Retained-log/hash audit only; no GPU execution; original study.json unchanged.')
    try:
        report = json.loads((out / 'study.json').read_text(encoding='utf-8'))
        before, sources = digest(exe), source_hashes()
        audit.update(study_sha256=digest(out / 'study.json'), executable_sha256=before, source_hashes_at_audit=sources)
        if report.get('status') != 'passed' or before != report['executable_sha256'] or before != report['executable_sha256_after']:
            raise ValueError('study incomplete or executable hash differs')
        if sources != report['source_hashes_before'] or sources != report['source_hashes_after']:
            raise ValueError('transitive GPU source hashes differ')
        audit['raw_log_validation'] = audit_raw(report, out, exe)
        if digest(exe) != before or source_hashes() != sources or digest(out / 'study.json') != audit['study_sha256']:
            raise ValueError('executable/source/study changed during audit')
        audit['status'] = 'passed'
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        audit.update(status='failed', reason=str(exc))
    destination = out / ('study_audit_' + str(time.time_ns()) + '.json')
    destination.write_text(json.dumps(audit, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(destination)
    return 0 if audit['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=DEFAULT_EXE)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ncu', type=Path)
    parser.add_argument('--layout', dest='layouts', choices=('linear', 'morton8'), action='append')
    parser.add_argument('--size', dest='sizes', choices=tuple(SIZES), action='append')
    parser.add_argument('--timing-trials', type=int, default=5)
    parser.add_argument('--profile-trials', type=int, default=3)
    parser.add_argument('--barrier', choices=('grid', 'block'), default='grid', help='One explicitly recorded barrier variant per study')
    parser.add_argument('--io', choices=('cg', 'no-allocate'), default='cg', help='Explicit nontexture I/O cache-policy hint; recorded and checked against every receipt')
    parser.add_argument('--explicit-control', action='store_true', help='Pass --control epoch for binaries supporting that option; all receipts must represent full epoch work regardless')
    parser.add_argument('--validation-only', action='store_true')
    parser.add_argument('--audit-existing', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.timing_trials <= 20 or not 1 <= args.profile_trials <= 10:
        parser.error('timing/profile trial limits are 1..20 and 1..10')
    exe, out = args.exe.resolve(), args.out.resolve()
    if not exe.is_file():
        parser.error('experiment executable does not exist')
    if args.audit_existing:
        if not (out / 'study.json').is_file():
            parser.error('existing study.json required')
        return audit_existing(exe, out)
    if out.exists():
        parser.error('output directory must be new')
    out.mkdir(parents=True)
    selection = dict(layouts=list(dict.fromkeys(args.layouts or ('linear', 'morton8'))),
                     sizes=list(dict.fromkeys(args.sizes or SIZES)), timing_trials=args.timing_trials,
                     profile_trials=args.profile_trials, validation_only=args.validation_only, barrier=args.barrier,
                     explicit_control=args.explicit_control, io=args.io)
    tasks = task_plan(**selection)
    ncu = None if args.validation_only else resolve_ncu(args.ncu)
    report = dict(schema='atomOS-cache-partition-study', status='running', created_at_utc=datetime.now(timezone.utc).isoformat(),
                  executable=str(exe), executable_sha256=digest(exe), source_hashes_before=source_hashes(),
                  runner_sha256=digest(__file__), profiler_executable=str(ncu) if ncu else None, requested_metrics=list(METRICS),
                  selection=selection, tasks=tasks, commands=[], samples=[],
                  scope='Standalone partition experiment, not the production backend. Each actual K1 epoch is checked on the host before commit. Python audits receipts, SM mappings, traffic geometry and retained counters; cache pinning is not asserted.',
                  timing_scope='Unprofiled CUDA event timings include all warm/work/probe phases. Profiler GPU duration and application event times during profiling are separate and excluded from ordinary timing aggregates.',
                  checksum_scope='The executable checks per-thread four-component XOR against host expectations. These checksums are collision-prone integrity diagnostics, not a proof of residency.',
                  source_scope='Four transitive GPU source hashes captured before and after execution; distinct from compiler or binary proof.')

    def save():
        (out / 'study.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')

    save()
    if not args.validation_only and ncu is None:
        report.update(status='not_run', reason='Native Nsight Compute unavailable; no study workload launched')
        save()
        print(report['reason'], file=sys.stderr)
        return 3
    device = None
    try:
        for task in tasks:
            label = task['label']
            command = dict(command=command_for(task, exe, ncu, out), stdout=label + '.stdout.log', stderr=label + '.stderr.log')
            report['commands'].append(command)
            save()
            print('+', subprocess.list2cmdline(command['command']), flush=True)
            start = time.perf_counter()
            try:
                with (out / command['stdout']).open('w', encoding='utf-8') as stdout, (out / command['stderr']).open('w', encoding='utf-8') as stderr:
                    process = subprocess.run(command['command'], cwd=ROOT, stdout=stdout, stderr=stderr, timeout=180)
                command['exit_code'] = process.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                command.update(exit_code=None, error=str(exc))
                raise
            finally:
                command['wall_seconds'] = time.perf_counter() - start
                save()
            sample = sample_from_logs(task, command, out, device)
            device = sample['application_results'][0]['device'] if device is None else device
            report['samples'].append(sample)
            save()
        report['aggregates'] = aggregates(report)
        report['raw_log_validation'] = audit_raw(report, out, exe)
        report['executable_sha256_after'], report['source_hashes_after'] = digest(exe), source_hashes()
        if report['executable_sha256_after'] != report['executable_sha256'] or report['source_hashes_after'] != report['source_hashes_before']:
            raise ValueError('executable or transitive GPU source changed during study')
        report['status'] = 'passed'
        save()
        print(out / 'study.json')
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        report.update(status='failed', reason=str(exc))
        save()
        print(exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
