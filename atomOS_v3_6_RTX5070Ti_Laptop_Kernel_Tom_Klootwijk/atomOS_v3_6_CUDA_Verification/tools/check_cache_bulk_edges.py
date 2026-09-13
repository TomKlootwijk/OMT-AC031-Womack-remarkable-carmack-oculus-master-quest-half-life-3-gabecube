#!/usr/bin/env python3
"""Serial supplemental native-TMA checks: 20 conformance, 12 profiles, 14 sanitizers.

These edge shapes and seed/profile combinations supplement the main bulk study.
Conformance, sanitizer findings, and measured cache-floor outcomes are separate.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import study_cache_bulk as bulk
from validate import find_compute_sanitizer

SHAPES = ((1, 65536), (32768, 1), (128, 65536), (511, 16353), (9, 33))
PROFILE_SHAPES = ((32768, 1), (128, 65536), (511, 16353))
COMBINATIONS = (dict(seed=0, mode='provided', profile='source', fringe=False),
                dict(seed=0xffffffff, mode='shift-or', profile='directed', fringe=True))
AUDIT_SOURCES = (*bulk.AUDIT_SOURCES, 'tools/check_cache_bulk_edges.py', 'tools/validate.py')


def task_plan(stages):
    if not isinstance(stages, list) or not stages or len(set(stages)) != len(stages) or any(s not in ('conformance', 'profile', 'sanitizer') for s in stages):
        raise ValueError('invalid/empty edge study stage selection')
    tasks = []
    for kind, shapes, epochs in (('conformance', SHAPES, 3), ('profile', PROFILE_SHAPES, 1)):
        if kind not in stages:
            continue
        for rows, angles in shapes:
            for layout in bulk.LAYOUTS:
                for number, combo in enumerate(COMBINATIONS):
                    tasks.append(dict(kind=kind, label=f'{kind}_{rows}_{angles}_{layout}_combo{number}',
                                      context=bulk.context(rows, angles, layout, epochs=epochs, **combo)))
    if 'sanitizer' in stages:
        for tool, shapes in (('memcheck', ((1, 1), (17, 257), (512, 16384))),
                             ('synccheck', ((17, 257), (512, 16384))),
                             ('racecheck', ((17, 257), (512, 16384)))):
            for rows, angles in shapes:
                for layout in bulk.LAYOUTS:
                    tasks.append(dict(kind='sanitizer', tool=tool, label=f'{tool}_{rows}_{angles}_{layout}',
                                      context=bulk.context(rows, angles, layout, epochs=1)))
    return tasks


def command_for(task, exe, ncu, sanitizer, out):
    command = bulk.command_for(task, exe, ncu, out)
    if task['kind'] == 'sanitizer':
        return [str(sanitizer), '--tool', task['tool'], '--error-exitcode', '86', *command]
    return command


def sample_from_logs(task, command, out, expected_identity=None):
    sample = bulk.sample_from_logs(task, command, out, expected_identity)
    if task['kind'] == 'sanitizer':
        raw = bulk.read_log(bulk.retained_path(out, command['stdout'])) + '\n' + bulk.read_log(bulk.retained_path(out, command['stderr']))
        if task['tool'] == 'racecheck':
            findings = re.findall(r'RACECHECK SUMMARY:\s*(\d+) hazards displayed\s*\((\d+) errors,\s*(\d+) warnings\)', raw)
            if not findings or any(tuple(map(int, values)) != (0, 0, 0) for values in findings):
                raise ValueError('racecheck summary missing or reports hazards/errors/warnings')
            sample['sanitizer_audit'] = dict(status='passed', tool='racecheck', hazards=0, errors=0, warnings=0,
                                             summaries_checked=len(findings))
        else:
            findings = re.findall(r'ERROR SUMMARY:\s*(\d+) errors?', raw)
            if not findings or any(int(value) != 0 for value in findings):
                raise ValueError('sanitizer error summary missing or nonzero')
            sample['sanitizer_audit'] = dict(status='passed', tool=task['tool'], errors=0, summaries_checked=len(findings))
    return sample


def audit_raw(report, out, exe):
    tasks = task_plan(report['stages'])
    if not bulk.exact(tasks, report.get('tasks')) or len(report.get('commands', [])) != len(tasks) or len(report.get('samples', [])) != len(tasks):
        raise ValueError('edge study task/command/sample coverage incomplete')
    if Path(report['executable']).resolve() != exe or report['requested_metrics'] != list(bulk.METRICS):
        raise ValueError('saved edge executable/metric identity differs')
    expected_identity, receipts = None, 0
    for task, command, saved in zip(tasks, report['commands'], report['samples']):
        if not bulk.exact(command['command'], command_for(task, exe, report['profiler_executable'], report['sanitizer_executable'], out)):
            raise ValueError('saved edge command differs from task and selected tools')
        if command['stdout'] != task['label']+'.stdout.log' or command['stderr'] != task['label']+'.stderr.log':
            raise ValueError('saved edge log identity differs')
        actual = sample_from_logs(task, command, out, expected_identity)
        if not bulk.exact(saved, actual):
            raise ValueError('saved edge sample differs from raw receipt/counter/sanitizer output')
        expected_identity = expected_identity or bulk.identity(actual['application_results'][0])
        receipts += len(actual['application_results'])
    return dict(status='passed', commands_checked=len(tasks), application_json_receipts=receipts,
                conformance_runs=sum(t['kind'] == 'conformance' for t in tasks),
                profile_runs=sum(t['kind'] == 'profile' for t in tasks),
                sanitizer_runs={tool: sum(t.get('tool') == tool for t in tasks) for tool in ('memcheck', 'synccheck', 'racecheck')},
                observed_cold_floor_reached_samples=sum(s.get('traffic_audit', {}).get('observed_cold_floor_reached', False) for s in report['samples']),
                execution_identity=expected_identity)


def audit_existing(exe, out):
    audit = dict(schema='atomOS-cache-bulk-edges-audit', status='running', created_at_utc=datetime.now(timezone.utc).isoformat(),
                 scope='Retained-log/hash audit only; no GPU execution; original study.json unchanged.')
    try:
        report = json.loads((out/'study.json').read_text(encoding='utf-8'))
        executable_hash, sources, validators = bulk.digest(exe), bulk.hashes(bulk.SOURCES), bulk.hashes(AUDIT_SOURCES)
        audit.update(study_sha256=bulk.digest(out/'study.json'), executable_sha256=executable_hash,
                     source_hashes_at_audit=sources, audit_source_hashes_at_audit=validators)
        if report.get('status') != 'passed' or executable_hash != report['executable_sha256'] or executable_hash != report['executable_sha256_after']:
            raise ValueError('edge study incomplete or executable changed')
        if sources != report['source_hashes_before'] or sources != report['source_hashes_after']:
            raise ValueError('transitive GPU source hashes changed')
        if validators != report['audit_source_hashes_before'] or validators != report['audit_source_hashes_after']:
            raise ValueError('validation source hashes changed')
        audit['raw_log_validation'] = audit_raw(report, out, exe)
        if bulk.digest(exe) != executable_hash or bulk.hashes(bulk.SOURCES) != sources or bulk.hashes(AUDIT_SOURCES) != validators or bulk.digest(out/'study.json') != audit['study_sha256']:
            raise ValueError('evidence/executable/source changed during audit')
        audit['status'] = 'passed'
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        audit.update(status='failed', reason=str(exc))
    destination = out / ('study_audit_'+str(time.time_ns())+'.json')
    destination.write_text(json.dumps(audit, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(destination)
    return 0 if audit['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New evidence directory, except for --audit-existing')
    parser.add_argument('--ncu', type=Path, help='Native Nsight Compute executable')
    parser.add_argument('--sanitizer', type=Path, help='Native Compute Sanitizer executable')
    stages = parser.add_mutually_exclusive_group()
    stages.add_argument('--conformance-only', action='store_true')
    stages.add_argument('--profiles-only', action='store_true')
    stages.add_argument('--sanitizers-only', action='store_true')
    parser.add_argument('--audit-existing', action='store_true')
    args = parser.parse_args()
    exe, out = args.exe.resolve(), args.out.resolve()
    if not exe.is_file():
        parser.error('executable does not exist')
    if args.audit_existing:
        if not (out/'study.json').is_file():
            parser.error('existing study.json required')
        return audit_existing(exe, out)
    if out.exists():
        parser.error('output directory must be new')
    selected = ['conformance'] if args.conformance_only else ['profile'] if args.profiles_only else ['sanitizer'] if args.sanitizers_only else ['conformance', 'profile', 'sanitizer']
    tasks = task_plan(selected)
    ncu = bulk.resolve_ncu(args.ncu) if 'profile' in selected else None
    sanitizer = find_compute_sanitizer(args.sanitizer) if 'sanitizer' in selected else None
    out.mkdir(parents=True)
    report = dict(schema='atomOS-cache-bulk-edges-study', status='running', created_at_utc=datetime.now(timezone.utc).isoformat(),
                  executable=str(exe), executable_sha256=bulk.digest(exe), source_hashes_before=bulk.hashes(bulk.SOURCES),
                  audit_source_hashes_before=bulk.hashes(AUDIT_SOURCES), profiler_executable=str(ncu) if ncu else None,
                  sanitizer_executable=str(sanitizer) if sanitizer else None, requested_metrics=list(bulk.METRICS),
                  stages=selected, tasks=tasks, commands=[], samples=[],
                  scope='Serial supplemental edge checks. Host verification checks each real epoch before commit; Python audits receipts. No exported-trace Python recomputation is claimed here. Successful study status is separate from measured cold miss-floor outcomes.',
                  timing_scope='Profiler GPU duration and application event timings under profiler/sanitizer instrumentation are diagnostic, not ordinary benchmark timings.')

    def save():
        (out/'study.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')

    save()
    absent = (['Nsight Compute'] if 'profile' in selected and ncu is None else []) + (['Compute Sanitizer'] if 'sanitizer' in selected and sanitizer is None else [])
    if absent:
        report.update(status='not_run', reason='Native tool unavailable: '+', '.join(absent)+'; no workload launched')
        save()
        print(report['reason'], file=sys.stderr)
        return 3
    expected_identity = None
    try:
        for task in tasks:
            label = task['label']
            command = dict(command=command_for(task, exe, ncu, sanitizer, out), stdout=label+'.stdout.log', stderr=label+'.stderr.log')
            report['commands'].append(command)
            save()
            print('+', subprocess.list2cmdline(command['command']), flush=True)
            started = time.perf_counter()
            try:
                with (out/command['stdout']).open('w', encoding='utf-8') as stdout, (out/command['stderr']).open('w', encoding='utf-8') as stderr:
                    process = subprocess.run(command['command'], cwd=bulk.ROOT, stdout=stdout, stderr=stderr, timeout=600 if task['kind'] == 'sanitizer' else 240)
                command['exit_code'] = process.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                command.update(exit_code=None, error=str(exc))
                raise
            finally:
                command['wall_seconds'] = time.perf_counter()-started
                save()
            sample = sample_from_logs(task, command, out, expected_identity)
            expected_identity = expected_identity or bulk.identity(sample['application_results'][0])
            report['samples'].append(sample)
            save()
        report['raw_log_validation'] = audit_raw(report, out, exe)
        report.update(executable_sha256_after=bulk.digest(exe), source_hashes_after=bulk.hashes(bulk.SOURCES), audit_source_hashes_after=bulk.hashes(AUDIT_SOURCES))
        if report['executable_sha256_after'] != report['executable_sha256'] or report['source_hashes_after'] != report['source_hashes_before'] or report['audit_source_hashes_after'] != report['audit_source_hashes_before']:
            raise ValueError('executable or transitive GPU/validation source changed during edge study')
        report['status'] = 'passed'
        save()
        print(out/'study.json')
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        report.update(status='failed', reason=str(exc))
        try:
            report.update(executable_sha256_after=bulk.digest(exe), source_hashes_after=bulk.hashes(bulk.SOURCES), audit_source_hashes_after=bulk.hashes(AUDIT_SOURCES))
        except OSError as hash_error:
            report['post_run_hash_error'] = str(hash_error)
        save()
        print(exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
