#!/usr/bin/env python3
"""Validate and profile the padded native-TMA warm/work/probe experiment.

Default: 192 conformance commands, 20 ordinary timing trials, 12 cold profiles,
plus two maximum-size export commands. Twenty-four conformance commands also
export traces, giving 26 separately checked Python-reference runs.
Every proposed logical result is independently checked by the executable before
host commit. This runner audits receipts and measured traffic, not cache pinning.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time

from profile_cache import METRICS as CACHE_METRICS, parse_metrics, read_log, resolve_ncu
from study_cache_partition import traffic_geometry
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from reference import verify_execution_metadata, verify_run
from provenance import seal_run, verify_seal

DEFAULT_EXE = Path('C:/Users/Tom/.cache/ak1/bulk_export_sm120/Release/atomos_cache_bulk.exe')
SOURCES = ('experiments/cache_bulk.cu', 'cuda/kernel.cu', 'include/atomos/host.hpp', 'include/atomos/core.hpp')
AUDIT_SOURCES = ('tools/study_cache_bulk.py', 'tools/study_cache_partition.py', 'tools/profile_cache.py', 'python/reference.py', 'python/provenance.py')
METRICS = CACHE_METRICS + (
    'l1tex__t_sectors_pipe_lsu_mem_global_op_ld.sum',
    'l1tex__t_sectors_pipe_lsu_mem_global_op_ld_lookup_miss.sum',
    'dram__bytes_read.sum', 'launch__shared_mem_config_size',
)
LAYOUTS = ('linear', 'morton8')
MODES = ('provided', 'recurrent', 'shift-xor', 'shift-or')
PROFILES = ('source', 'directed', 'mixed')
SIZES = {'tiny': (1, 1), 'tail': (17, 257), 'default': (128, 1024), 'max': (512, 16384)}
RESOURCE_FIELDS = ('multiprocessors', 'grid_blocks', 'registers_per_thread', 'local_bytes_per_thread',
                   'static_shared_bytes', 'binary_version', 'preferred_shared_carveout')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hashes(names):
    return {name: digest(ROOT / name) for name in names}


def exact(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def context(rows, angles, layout, epochs=3, mode='recurrent', fringe=True, profile='mixed', seed=130):
    if any(type(v) is not int for v in (rows, angles, epochs, seed)):
        raise ValueError('integer workload dimensions/epochs/seed required')
    if not (1 <= rows <= 65536 and 1 <= angles <= 65536 and 1 <= epochs <= 16 and 0 <= seed <= 0xffffffff):
        raise ValueError('workload dimensions/epochs/seed out of range')
    if layout not in LAYOUTS or mode not in MODES or profile not in PROFILES or type(fringe) is not bool:
        raise ValueError('invalid layout/mode/fringe/profile')
    geometry = traffic_geometry(rows, angles, layout)
    if geometry['logical_texels'] * epochs > 2**20:
        raise ValueError('lane-epoch cap exceeded')
    return dict(rows=rows, angles=angles, layout=layout, epochs=epochs, mode=mode, fringe=fringe, profile=profile, seed=seed)


def identity(receipt):
    return dict(device=receipt['device'], resources={key: receipt[key] for key in RESOURCE_FIELDS})


def validate_result(receipt, c, expected_identity=None):
    if not isinstance(receipt, dict):
        raise ValueError('application receipt must be an object')
    integers = ('rows', 'angles', 'epochs', 'seed', 'block_size', 'tile_texels', *RESOURCE_FIELDS,
                'shared_union_bytes', 'input_tile_bytes', 'result_tile_bytes', 'bulk_barrier_bytes',
                'padded_rows', 'padded_words', 'stored_texels', 'logical_texels', 'padding_texels',
                'chunk_texels', 'maximum_assigned_mask_bytes', 'warm_texel_reads_per_epoch',
                'work_texel_reads_per_epoch', 'post_texel_reads_per_epoch', 'expected_total_texel_reads_per_epoch',
                'tiles_per_epoch', 'bulk_input_bytes_per_epoch', 'bulk_result_bytes_per_epoch',
                'bulk_diagnostic_bytes_per_epoch', 'mask_bytes', 'payload_bytes', 'diagnostic_bytes',
                'planned_bytes', 'verified_lane_epochs', 'checksum_components', 'checksum_disagreements',
                'setup_launches', 'active_blocks_per_sm_limit')
    if any(type(receipt.get(key)) is not int for key in integers):
        raise ValueError('integer bulk execution metadata required')
    fixed = dict(status='passed', scope='experimental_bulk_io_warm_work_retention_probe',
                 io='native_cp_async_bulk_1d', barrier='grid', phase_order_scope='whole_cooperative_grid',
                 padding_and_tails_supported=True, device_records='padded_row_major', results='canonical_row_major',
                 block_size=512, tile_texels=64, active_blocks_per_sm_limit=1, max_l1_requested=True,
                 preferred_shared_carveout=0, shared_union_bytes=10752, input_tile_bytes=5632,
                 result_tile_bytes=10752, bulk_barrier_bytes=8, candidate_verification='passed',
                 checksum_scheme='per_thread_componentwise_xor', checksum_components=4, checksum_disagreements=0,
                 sm_mapping_verified=True, setup_launches=1, setup_launch_verified=True,
                 setup_checksum_verified=True, host_tile_coverage_verified=True, padding_output_verified_zero=True,
                 timing_scope='entire_warm_bulk_io_work_probe_kernel_including_barriers_and_diagnostics', **c)
    for key, value in fixed.items():
        if not exact(receipt.get(key), value):
            raise ValueError(f'bulk receipt context/verification differs: {key}')
    sm = receipt['multiprocessors']
    if sm <= 0 or receipt['grid_blocks'] != sm or not 1 <= receipt['registers_per_thread'] <= 255:
        raise ValueError('invalid cooperative launch/resource geometry')
    if receipt['local_bytes_per_thread'] < 0 or receipt['static_shared_bytes'] < 10760 or receipt['binary_version'] < 90:
        raise ValueError('invalid native-TMA resource metadata')
    verify_execution_metadata(dict(backend='cuda', read='texture-packed', device=receipt.get('device'), candidate_verification='passed'),
                              expected_device=expected_identity['device'] if expected_identity else None)
    if receipt['device']['cc_major'] < 9:
        raise ValueError('native bulk copy requires compute capability at least 9')
    if expected_identity and not exact(identity(receipt)['resources'], expected_identity['resources']):
        raise ValueError('kernel/device resource metadata changed within the same binary study')
    geometry = traffic_geometry(c['rows'], c['angles'], c['layout'])
    atlas, logical = geometry['stored_texels'], geometry['logical_texels']
    words = (c['angles'] + 31) // 32
    chunk = ((atlas + sm * 64 - 1) // (sm * 64)) * 64
    diagnostics = 2 * sm * 512 * 16 + 2 * sm * 16
    expected = {key: geometry[key] for key in ('stored_texels', 'logical_texels', 'mask_bytes',
                'warm_texel_reads_per_epoch', 'work_texel_reads_per_epoch', 'post_texel_reads_per_epoch',
                'expected_total_texel_reads_per_epoch')}
    expected.update(padded_rows=(c['rows'] + 7) // 8 * 8, padded_words=(words + 7) // 8 * 8,
                    padding_texels=atlas-logical, chunk_texels=chunk, maximum_assigned_mask_bytes=min(chunk, atlas)*16,
                    tiles_per_epoch=atlas//64, bulk_input_bytes_per_epoch=atlas*88,
                    bulk_result_bytes_per_epoch=atlas*168, bulk_diagnostic_bytes_per_epoch=diagnostics,
                    diagnostic_bytes=diagnostics, payload_bytes=atlas*272+diagnostics,
                    planned_bytes=atlas*272+diagnostics+64*2**20, verified_lane_epochs=logical*c['epochs'])
    for key, value in expected.items():
        if receipt[key] != value:
            raise ValueError(f'bulk receipt geometry/payload differs: {key}')
    if receipt['planned_bytes'] > 512*2**20:
        raise ValueError('bulk plan exceeds experiment budget')
    mappings = receipt.get('sm_mappings')
    if not isinstance(mappings, list) or len(mappings) != c['epochs'] + 1:
        raise ValueError('missing setup/epoch SM mappings')
    for launch, mapping in enumerate(mappings):
        if not isinstance(mapping, dict) or type(mapping.get('launch')) is not int or mapping['launch'] != launch or not exact(mapping.get('setup'), launch == 0):
            raise ValueError('SM mapping launch identity differs')
        before, after = mapping.get('before'), mapping.get('after')
        if not isinstance(before, list) or not isinstance(after, list) or len(before) != sm or len(after) != sm:
            raise ValueError('SM mapping count differs')
        if any(type(value) is not int or not 0 <= value < 0xffffffff for value in before + after):
            raise ValueError('invalid/unwritten physical SM identifier')
        # Physical SM IDs can be sparse; SM count is not an upper ID bound.
        if before != after or len(set(before)) != sm:
            raise ValueError('SM mapping changed or partitions shared an observed SM')
    times = receipt.get('compute_ms')
    if not isinstance(times, list) or len(times) != c['epochs'] or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in times):
        raise ValueError('missing/nonfinite/negative epoch timings')
    return receipt


def application_results(raw, c, allow_replay=False, expected_identity=None):
    decoder, receipts, position = json.JSONDecoder(), [], 0
    while (start := raw.find('{', position)) >= 0:
        try:
            receipt, length = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError as exc:
            raise ValueError('malformed application JSON in stdout') from exc
        validate_result(receipt, c, expected_identity)
        expected_identity = expected_identity or identity(receipt)
        receipts.append(receipt)
        position = start + length
    if not receipts or (not allow_replay and len(receipts) != 1):
        raise ValueError('missing or unexpected duplicate application receipt')
    return receipts


def validate_traffic(metrics, c, receipt):
    if set(metrics) != set(METRICS) or any(m.get('status') != 'collected' or type(m.get('value')) is not int or m['value'] < 0 for m in metrics.values()):
        raise ValueError('required profiler counter unavailable or invalid')
    geometry = traffic_geometry(c['rows'], c['angles'], c['layout'])
    requests, sectors, hits, misses = (metrics[name]['value'] for name in METRICS[:4])
    if requests < geometry['expected_texture_requests'] or sectors < geometry['expected_texture_sectors']:
        raise ValueError('measured texture traffic below independently computed three-phase minimum')
    if hits + misses != sectors or misses < geometry['cold_warm_sector_floor']:
        raise ValueError('inconsistent texture hit/miss totals or cold compulsory floor')
    if metrics[METRICS[6]]['value'] > metrics[METRICS[5]]['value']:
        raise ValueError('LSU misses exceed LSU sectors')
    if metrics[CACHE_METRICS[-1]]['unit'] not in ('ns', 'nsecond'):
        raise ValueError('profiler GPU duration must use base nanoseconds')
    shared = metrics['launch__shared_mem_config_size']
    if shared['unit'] not in ('byte', 'bytes') or shared['value'] < receipt['static_shared_bytes']:
        raise ValueError('measured shared-memory configuration is invalid or below kernel allocation')
    return dict(status='passed', nominal_minimum_requests=geometry['expected_texture_requests'],
                nominal_minimum_sectors=geometry['expected_texture_sectors'], actual_requests=requests,
                actual_sectors=sectors, actual_hits=hits, actual_misses=misses,
                excess_requests=requests-geometry['expected_texture_requests'],
                excess_sectors=sectors-geometry['expected_texture_sectors'],
                cold_compulsory_miss_floor=geometry['cold_warm_sector_floor'],
                excess_misses_over_cold_floor=misses-geometry['cold_warm_sector_floor'],
                observed_cold_floor_reached=misses == geometry['cold_warm_sector_floor'],
                hit_fraction=hits/sectors, actual_shared_configuration_bytes=shared['value'],
                interpretation='Actual aggregate includes warm, real work, and probe; geometry conformance does not assert residency. Reaching the cold floor is an observation for this launch, not permanent cache pinning.')


def task_plan(layouts, sizes, conformance_sizes, modes, fringes, profiles, timing_trials, profile_trials, stages, exports=True):
    for selected, allowed in ((layouts, LAYOUTS), (sizes, ('default', 'max')), (conformance_sizes, tuple(SIZES)),
                              (modes, MODES), (profiles, PROFILES), (stages, ('conformance', 'timing', 'profile'))):
        if not isinstance(selected, list) or not selected or len(set(selected)) != len(selected) or any(v not in allowed for v in selected):
            raise ValueError('empty, duplicate, or invalid study selection')
    if not isinstance(fringes, list) or not fringes or any(type(v) is not bool for v in fringes) or len(set(fringes)) != len(fringes):
        raise ValueError('invalid fringe selection')
    if type(exports) is not bool or type(timing_trials) is not int or type(profile_trials) is not int or not 1 <= timing_trials <= 20 or not 1 <= profile_trials <= 10:
        raise ValueError('invalid export/repetition selection')
    tasks = []
    if 'conformance' in stages:
        for size, layout, mode, fringe, profile in itertools.product(conformance_sizes, layouts, modes, fringes, profiles):
            label = f'conformance_{size}_{layout}_{mode}_{"on" if fringe else "off"}_{profile}'
            task = dict(kind='conformance', label=label, size=size,
                        context=context(*SIZES[size], layout, mode=mode, fringe=fringe, profile=profile))
            if exports and size in ('tiny', 'tail', 'default'):
                rotation = ('tiny', 'tail', 'default').index(size) + LAYOUTS.index(layout) + MODES.index(mode)
                if profile == PROFILES[rotation % 3] and fringe == bool(rotation % 2):
                    task['export'] = label + '.run'
            tasks.append(task)
        if exports and 'max' in conformance_sizes:
            for layout in layouts:
                label = f'python_export_max_{layout}'
                tasks.append(dict(kind='export', label=label, size='max', export=label+'.run',
                                  context=context(*SIZES['max'], layout, epochs=1)))
    selected = list(itertools.product(sizes, layouts))
    if 'timing' in stages:
        for trial in range(timing_trials):
            order = list(selected)
            random.Random(20260913 + trial).shuffle(order)
            for size, layout in order:
                tasks.append(dict(kind='timing', label=f'time_{trial}_{size}_{layout}', trial=trial, size=size,
                                  context=context(*SIZES[size], layout)))
    if 'profile' in stages:
        for size, layout in selected:
            for trial in range(profile_trials):
                tasks.append(dict(kind='profile', label=f'cold_{trial}_{size}_{layout}', trial=trial, size=size,
                                  context=context(*SIZES[size], layout, epochs=1)))
    return tasks


def command_for(task, exe, ncu, out):
    c = task['context']
    application = [str(exe), '--rows', str(c['rows']), '--angles', str(c['angles']), '--epochs', str(c['epochs']),
                   '--seed', str(c['seed']), '--layout', c['layout'], '--mode', c['mode'],
                   '--fringe', 'on' if c['fringe'] else 'off', '--profile', c['profile']]
    if task.get('export'):
        application += ['--out', str(out / task['export'])]
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


def sample_from_logs(task, command, out, expected_identity=None, create_export_seal=False):
    if type(command.get('exit_code')) is not int or command['exit_code'] != 0:
        raise ValueError('application/profiler did not exit successfully')
    retained_path(out, command['stderr'])
    receipts = application_results(read_log(retained_path(out, command['stdout'])), task['context'], task['kind'] == 'profile', expected_identity)
    sample = dict(task=task, application_results=receipts)
    if task.get('export'):
        directory = (out / task['export']).resolve()
        if not directory.is_relative_to(out) or not directory.is_dir():
            raise ValueError('missing or out-of-directory exported run')
        summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
        if summary.get('execution_profile') != 'bulk-warm-work-probe-v1' or summary.get('allocation_layout') != 'bulk-padded-row-major-v1':
            raise ValueError('exported run lacks the explicit bulk execution/allocation profiles')
        if any(not exact(summary.get(key), value) for key, value in task['context'].items()):
            raise ValueError('exported run context differs from requested workload')
        if not exact(summary.get('bulk_receipt'), receipts[0]):
            raise ValueError('exported embedded receipt differs from application stdout')
        result = verify_run(directory, expected_backend='cuda', expected_read='texture-packed', expected_device=receipts[0]['device'])
        if result['status'] != 'passed' or result['lane_epochs'] != receipts[0]['verified_lane_epochs']:
            raise ValueError('independent Python exported-result verification failed or count differs')
        if create_export_seal:
            seal_run(directory, ['atomOS:synthetic:K1'])
        if not verify_seal(directory):
            raise ValueError('exported run seal verification failed')
        files = {}
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                if not path.resolve().is_relative_to(directory):
                    raise ValueError('exported run contains an external file link')
                files[path.relative_to(directory).as_posix()] = digest(path)
        sample['python_export_verification'] = result
        sample['export_seal_verification'] = dict(status='passed', seal_sha256=digest(directory/'run_seal.json'))
        sample['export_file_hashes'] = files
    if task['kind'] == 'timing':
        sample['ordinary_event_median_ms'] = statistics.median(receipts[0]['compute_ms'])
    if task['kind'] == 'profile':
        sample['csv'] = task['label'] + '.csv.log'
        sample['metrics'] = parse_metrics(read_log(retained_path(out, sample['csv'])), METRICS)
        sample['traffic_audit'] = validate_traffic(sample['metrics'], task['context'], receipts[0])
    return sample


def aggregates(report):
    result = []
    selection = report['selection']
    for size, layout in itertools.product(selection['sizes'], selection['layouts']):
        samples = [s for s in report['samples'] if s['task']['size'] == size and s['task']['context']['layout'] == layout]
        times = [s['ordinary_event_median_ms'] for s in samples if s['task']['kind'] == 'timing']
        profiles = [s for s in samples if s['task']['kind'] == 'profile']
        if len(times) != (selection['timing_trials'] if 'timing' in selection['stages'] else 0) or len(profiles) != (selection['profile_trials'] if 'profile' in selection['stages'] else 0):
            raise ValueError('selected repetitions incomplete')
        if not times and not profiles:
            continue
        entry = dict(size=size, layout=layout, ordinary_timing_trials=len(times), profile_trials=len(profiles),
                     ordinary_event_median_ms=statistics.median(times) if times else None,
                     ordinary_event_min_ms=min(times) if times else None, ordinary_event_max_ms=max(times) if times else None)
        if profiles:
            entry['metrics'] = {}
            for name in METRICS:
                if len({s['metrics'][name]['unit'] for s in profiles}) != 1:
                    raise ValueError('counter units changed across repetitions')
                values = [s['metrics'][name]['value'] for s in profiles]
                entry['metrics'][name] = dict(min=min(values), median=statistics.median(values), max=max(values), unit=profiles[0]['metrics'][name]['unit'])
            entry['cold_floor_reached_samples'] = sum(s['traffic_audit']['observed_cold_floor_reached'] for s in profiles)
            entry['cold_compulsory_miss_floor'] = profiles[0]['traffic_audit']['cold_compulsory_miss_floor']
        result.append(entry)
    return result


def audit_raw(report, out, exe):
    tasks = task_plan(**report['selection'])
    if not exact(report.get('tasks'), tasks) or len(report.get('commands', [])) != len(tasks) or len(report.get('samples', [])) != len(tasks):
        raise ValueError('saved study coverage differs from complete task plan')
    if Path(report['executable']).resolve() != exe or report['requested_metrics'] != list(METRICS):
        raise ValueError('saved executable/metrics identity differs')
    expected_identity, count = None, 0
    for task, command, saved in zip(tasks, report['commands'], report['samples']):
        if not exact(command['command'], command_for(task, exe, report['profiler_executable'], out)):
            raise ValueError('saved command differs from planned workload/profiling conditions')
        if command['stdout'] != task['label'] + '.stdout.log' or command['stderr'] != task['label'] + '.stderr.log':
            raise ValueError('saved log names differ from command identity')
        actual = sample_from_logs(task, command, out, expected_identity)
        if not exact(saved, actual):
            raise ValueError('saved sample differs from retained application output/counters')
        expected_identity = expected_identity or identity(actual['application_results'][0])
        count += len(actual['application_results'])
    if not exact(report.get('aggregates'), aggregates(report)):
        raise ValueError('saved aggregates differ from retained samples')
    return dict(status='passed', commands_checked=len(tasks), application_json_receipts=count,
                conformance_runs=sum(t['kind'] == 'conformance' for t in tasks),
                timing_runs=sum(t['kind'] == 'timing' for t in tasks), profile_runs=sum(t['kind'] == 'profile' for t in tasks),
                additional_export_runs=sum(t['kind'] == 'export' for t in tasks),
                python_verified_export_runs=sum(bool(t.get('export')) for t in tasks),
                python_verified_lane_epochs=sum(s['python_export_verification']['lane_epochs'] for s in report['samples'] if 'python_export_verification' in s),
                execution_identity=expected_identity)


def audit_existing(exe, out):
    audit = dict(schema='atomOS-cache-bulk-audit', status='running', created_at_utc=datetime.now(timezone.utc).isoformat(),
                 scope='Retained-log/hash audit only; no GPU execution; original study.json unchanged.')
    try:
        report = json.loads((out / 'study.json').read_text(encoding='utf-8'))
        before, sources, validators = digest(exe), hashes(SOURCES), hashes(AUDIT_SOURCES)
        audit.update(study_sha256=digest(out / 'study.json'), executable_sha256=before,
                     source_hashes_at_audit=sources, audit_source_hashes_at_audit=validators)
        if report.get('status') != 'passed' or before != report['executable_sha256'] or before != report['executable_sha256_after']:
            raise ValueError('study incomplete or executable hash differs')
        if sources != report['source_hashes_before'] or sources != report['source_hashes_after']:
            raise ValueError('transitive GPU source hashes differ')
        if validators != report['audit_source_hashes_before'] or validators != report['audit_source_hashes_after']:
            raise ValueError('receipt/traffic validation source hashes differ')
        audit['raw_log_validation'] = audit_raw(report, out, exe)
        if digest(exe) != before or hashes(SOURCES) != sources or hashes(AUDIT_SOURCES) != validators or digest(out / 'study.json') != audit['study_sha256']:
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
    parser.add_argument('--out', type=Path, required=True, help='New evidence directory (except --audit-existing)')
    parser.add_argument('--ncu', type=Path)
    parser.add_argument('--layout', dest='layouts', choices=LAYOUTS, action='append')
    parser.add_argument('--size', dest='sizes', choices=('default', 'max'), action='append', help='Timing/profiling size selection')
    parser.add_argument('--conformance-size', dest='conformance_sizes', choices=tuple(SIZES), action='append')
    parser.add_argument('--mode', dest='modes', choices=MODES, action='append', help='Conformance selection; timings/profiles use recurrent')
    parser.add_argument('--fringe', dest='fringes', choices=('on', 'off'), action='append', help='Conformance selection; timings/profiles use on')
    parser.add_argument('--profile', dest='profiles', choices=PROFILES, action='append', help='Conformance selection; timings/profiles use mixed')
    parser.add_argument('--timing-trials', type=int, default=5)
    parser.add_argument('--profile-trials', type=int, default=3)
    parser.add_argument('--no-exports', action='store_true', help='Disable representative exported-trace/Python checks; native host checks still run')
    stages = parser.add_mutually_exclusive_group()
    stages.add_argument('--conformance-only', action='store_true')
    stages.add_argument('--profiles-only', action='store_true')
    stages.add_argument('--timings-only', action='store_true')
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
    selected_stages = ['conformance'] if args.conformance_only else ['profile'] if args.profiles_only else ['timing'] if args.timings_only else ['conformance', 'timing', 'profile']
    unique = lambda values: list(dict.fromkeys(values))
    selection = dict(layouts=unique(args.layouts or LAYOUTS), sizes=unique(args.sizes or ('default', 'max')),
                     conformance_sizes=unique(args.conformance_sizes or SIZES), modes=unique(args.modes or MODES),
                     fringes=unique([v == 'on' for v in args.fringes] if args.fringes else [False, True]),
                     profiles=unique(args.profiles or PROFILES), timing_trials=args.timing_trials,
                     profile_trials=args.profile_trials, stages=selected_stages, exports=not args.no_exports)
    tasks = task_plan(**selection)
    ncu = resolve_ncu(args.ncu) if 'profile' in selected_stages else None
    out.mkdir(parents=True)
    report = dict(schema='atomOS-cache-bulk-study', status='running', created_at_utc=datetime.now(timezone.utc).isoformat(),
                  executable=str(exe), executable_sha256=digest(exe), source_hashes_before=hashes(SOURCES),
                  audit_source_hashes_before=hashes(AUDIT_SOURCES), profiler_executable=str(ncu) if ncu else None,
                  requested_metrics=list(METRICS), selection=selection, tasks=tasks, commands=[], samples=[],
                  scope='Standalone padded native-TMA experiment. The executable verifies every logical candidate before each host commit and verifies zero output padding. Python audits all receipts/traffic and independently recomputes representative exported traces; exported Python coverage is counted separately from native host conformance. A passing study means the selected checks ran successfully; it does not mean full cache residency.',
                  timing_scope='Ordinary event timings include all warm/bulk-I/O/work/probe/barrier/diagnostic phases. Application event timings under profiling are retained but excluded from ordinary aggregates; gpu__time_duration.sum is separately labeled profiler time.',
                  checksum_scope='Four-component XOR diagnostics are collision-prone integrity checks, not residency proofs.',
                  source_scope='Transitive GPU and validation source hashes captured before/after; mathematical, binary, conformance and hardware-counter evidence remain distinct.')

    def save():
        (out / 'study.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')

    save()
    if 'profile' in selected_stages and ncu is None:
        report.update(status='not_run', reason='Native Nsight Compute unavailable; no study workload launched')
        save()
        print(report['reason'], file=sys.stderr)
        return 3
    expected_identity = None
    try:
        for task in tasks:
            label = task['label']
            command = dict(command=command_for(task, exe, ncu, out), stdout=label+'.stdout.log', stderr=label+'.stderr.log')
            report['commands'].append(command)
            save()
            print('+', subprocess.list2cmdline(command['command']), flush=True)
            started = time.perf_counter()
            try:
                with (out / command['stdout']).open('w', encoding='utf-8') as stdout, (out / command['stderr']).open('w', encoding='utf-8') as stderr:
                    process = subprocess.run(command['command'], cwd=ROOT, stdout=stdout, stderr=stderr, timeout=240)
                command['exit_code'] = process.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                command.update(exit_code=None, error=str(exc))
                raise
            finally:
                command['wall_seconds'] = time.perf_counter() - started
                save()
            sample = sample_from_logs(task, command, out, expected_identity, create_export_seal=True)
            expected_identity = expected_identity or identity(sample['application_results'][0])
            report['samples'].append(sample)
            save()
        report['aggregates'] = aggregates(report)
        report['raw_log_validation'] = audit_raw(report, out, exe)
        report.update(executable_sha256_after=digest(exe), source_hashes_after=hashes(SOURCES), audit_source_hashes_after=hashes(AUDIT_SOURCES))
        if report['executable_sha256_after'] != report['executable_sha256'] or report['source_hashes_after'] != report['source_hashes_before'] or report['audit_source_hashes_after'] != report['audit_source_hashes_before']:
            raise ValueError('executable or transitive GPU/validation source changed during study')
        report['status'] = 'passed'
        save()
        print(out / 'study.json')
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        report.update(status='failed', reason=str(exc))
        try:
            report.update(executable_sha256_after=digest(exe), source_hashes_after=hashes(SOURCES), audit_source_hashes_after=hashes(AUDIT_SOURCES))
        except OSError as hash_error:
            report['post_run_hash_error'] = str(hash_error)
        save()
        print(exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
