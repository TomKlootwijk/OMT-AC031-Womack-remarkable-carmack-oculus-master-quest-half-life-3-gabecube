#!/usr/bin/env python3
"""Retain and independently check real GPU runs of the integrated atomOS U lane.

This tool never substitutes CPU output for device output. --prepare-only records
not_run. Invoke on the CUDA host with --exe and a fresh evidence directory.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from universal_reference import read_program, initial_state, simulate, growing_extent
AUDIT_SOURCES = ('python/universal_reference.py', 'python/reference.py', 'tools/validate_universal.py',
                 'include/atomos/universal.hpp', 'include/atomos/core.hpp', 'include/atomos/host.hpp',
                 'include/atomos/log_polar.hpp', 'cuda/kernel.cu', 'experiments/universal_engine.cu')


def program_text(states=2, alphabet=2, head=0, halts=(1,), cells=(), rules=()):
    lines = ['atomos-universal 1', f'states {states}', f'alphabet {alphabet}', f'start 0 {head}']
    if halts:
        lines.append('halt ' + ' '.join(map(str, halts)))
    lines.extend(f'cell {a} {s}' for a, s in cells)
    lines.extend(f'rule {q} {r} {n} {w} {d}' for q, r, n, w, d in rules)
    return '\n'.join(lines) + '\n'


def cases():
    jobs = []

    def add(name, text, *, budget=8, epochs=1, origin=-16, cells=41, **extra):
        jobs.append(dict(name=name, program=text, budget=budget, epochs=epochs,
                         origin=origin, cells=cells, **extra))

    unary = program_text(cells=((0, 1), (1, 1), (2, 1)),
                         rules=((0, 1, 0, 1, 'R'), (0, 0, 1, 1, 'S')))
    add('unary_increment_halt', unary, budget=4)
    add('unary_increment_across_epochs', unary, budget=2, epochs=3)
    add('unary_zero_budget', unary, budget=0, epochs=2)
    add('initial_halt', program_text(states=1, halts=(0,)), budget=0, epochs=2)
    add('erase_negative_addresses', program_text(cells=((-2, 1), (-1, 1), (0, 1)),
        rules=((0, 1, 0, 0, 'L'), (0, 0, 1, 0, 'S'))))
    add('missing_rule_first_step', program_text(), budget=2)
    add('missing_rule_after_candidate_write', program_text(states=3, halts=(2,),
        rules=((0, 0, 1, 1, 'R'),)), budget=3)
    add('range_reject_before_write_or_halt', program_text(head=-2, rules=((0, 0, 1, 1, 'L'),)),
        origin=-2, cells=7)
    walker = program_text(states=1, halts=(), rules=((0, 0, 0, 1, 'R'), (0, 1, 0, 0, 'R')))
    add('walker_running_prefix', walker, budget=5, epochs=2)
    add('walker_later_epoch_rejection', walker, budget=5, epochs=3, origin=-1, cells=13)
    add('long_prefix_12288_transitions', walker, budget=4096, epochs=3, origin=-19, cells=12321)
    add('growing_tape_twenty_epochs', walker, budget=2, epochs=20, growing=True)
    add('alphabet_one_blank_walker', program_text(states=1, alphabet=1, halts=(),
        rules=((0, 0, 0, 0, 'R'),)), budget=7, epochs=2)
    add('left_boundary_after_candidate_write', program_text(states=1, halts=(),
        rules=((0, 0, 0, 1, 'L'), (0, 1, 0, 0, 'L'))), budget=3, origin=-1, cells=5)
    for name, head, origin, direction in (
        ('i64_max_destination_overflow', (1 << 63) - 1, (1 << 63) - 3, 'R'),
        ('i64_min_destination_overflow', -(1 << 63), -(1 << 63), 'L')):
        add(name, program_text(head=head, rules=((0, 0, 1, 1, direction),)), origin=origin, cells=3)
    for alphabet in (3, 5, 33):
        add(f'alphabet_{alphabet}_packed_writes', program_text(states=1, alphabet=alphabet,
            head=-1, halts=(), cells=((-2, alphabet - 2), (0, 1), (3, alphabet - 1)),
            rules=tuple((0, symbol, 0, alphabet - 1 - symbol, 'R') for symbol in range(alphabet))),
            budget=11, epochs=2, origin=-11, cells=37)
        for seed in range(6):
            rng = random.Random(0xA7036000 + alphabet * 101 + seed)
            table = tuple((q, symbol, rng.randrange(6), rng.randrange(alphabet), rng.choice(('L', 'S', 'R')))
                          for q in range(5) for symbol in range(alphabet))
            initial = tuple((address, rng.randrange(1, alphabet)) for address in range(-7, 8, 2))
            add(f'random_alphabet_{alphabet}_seed_{seed}', program_text(states=6, alphabet=alphabet,
                head=-3, halts=(5,), cells=initial, rules=table), budget=19, epochs=3,
                origin=-17, cells=43)
    add('reject_explicit_zero_outside_window', program_text(cells=((99, 0),)),
        origin=-1, cells=5, configuration_error=True)
    add('reject_explicit_nonzero_outside_window', program_text(cells=((99, 1),)),
        origin=-1, cells=5, configuration_error=True)
    add('reject_duplicate_transition', program_text(rules=((0, 0, 0, 0, 'R'), (0, 0, 1, 1, 'S'))),
        configuration_error=True)
    for edge, head, inward, outward in (('min', -(1 << 63), 'R', 'L'),
                                       ('max', (1 << 63) - 1, 'L', 'R')):
        for movement, direction in (('inward', inward), ('outward', outward)):
            add(f'growing_i64_{edge}_{movement}', program_text(head=head, rules=((0, 0, 1, 1, direction),)),
                budget=8, growing=True)
    add('pragmatic_binary_increment', (ROOT / 'examples/universal/binary_increment.atomos').read_text(encoding='utf-8'), budget=6)
    add('pragmatic_symbol_replace', (ROOT / 'examples/universal/replace_symbol.atomos').read_text(encoding='utf-8'), budget=5)
    add('reject_table_before_allocation', program_text(states=65536, alphabet=65536),
        budget=0, memory_mib=1, resource_refused=True)
    for index, job in enumerate(jobs):
        job.update(rows=9 if index % 3 == 0 else 3, angles=33 if index % 2 else 257,
                   layout='morton8' if index % 2 else 'linear',
                   mode=('provided', 'recurrent', 'shift-xor', 'shift-or')[index % 4],
                   profile=('source', 'directed', 'mixed')[index % 3],
                   fringe=bool(index % 2), seed=(36 + index * 0x10203) & 0xffffffff,
                   tape_tail_fill=0xa5a5a5a5)
    return jobs


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_attempts(job, path):
    if job.get('configuration_error') or job.get('resource_refused'):
        return []
    program = read_program(path)
    state = initial_state(program)
    attempts = []
    for epoch in range(job['epochs']):
        if job.get('growing'):
            origin, count = growing_extent(state, job['budget'])
        else:
            origin, count = job['origin'], job['cells']
        candidate = simulate(program, state, origin=origin, cells=count, budget=job['budget'])
        attempts.append(dict(epoch=epoch, status=candidate['status'], status_name=candidate['status_name'],
                             steps=candidate['steps'], accepted=candidate['accepted']))
        if not candidate['accepted']:
            break
        state = {key: candidate[key] for key in ('control', 'head', 'tape')}
    return attempts


def command_for(exe, job, program, directory):
    command = [str(exe), '--program', str(program), '--out', str(directory),
               '--steps-per-epoch', str(job['budget']), '--epochs', str(job['epochs']),
               '--rows', str(job['rows']), '--angles', str(job['angles']),
               '--layout', job['layout'], '--mode', job['mode'], '--profile', job['profile'],
               '--seed', str(job['seed']), '--tape-tail-fill', str(job['tape_tail_fill']),
               '--fringe', 'on' if job['fringe'] else 'off']
    if not job.get('growing'):
        command.extend(['--origin', str(job['origin']), '--cells', str(job['cells'])])
    for key, option in (('memory_mib', '--memory-mib'), ('reserve_mib', '--reserve-mib')):
        if key in job:
            command.extend([option, str(job[key])])
    return command


def verify_case(directory, job, execution=None, evidence_root=None):
    from universal_reference import verify_export
    if job.get('resource_refused'):
        if Path(directory).exists():
            raise ValueError('resource refusal published a committed output directory')
        if execution is None or evidence_root is None or execution['returncode'] != 3:
            raise ValueError('actual resource-refusal process evidence required')
        stdout = (Path(evidence_root) / execution['stdout']).read_text(encoding='utf-8', errors='replace')
        receipt = json.loads(stdout.strip().splitlines()[-1])
        if receipt.get('status') != 'resource_refused' or receipt.get('failed_attempt_committed') is not False or 'table' not in receipt.get('reason', '').lower():
            raise ValueError('native table-resource-refusal receipt missing')
        return dict(status='passed', resource_rejection_verified=True, failed_attempt_committed=False,
                    u_transitions=0, k1_lane_epochs=0)
    if job.get('configuration_error'):
        if Path(directory).exists():
            raise ValueError('invalid configuration published an output directory')
        return dict(status='passed', configuration_rejection_verified=True,
                    u_transitions=0, k1_lane_epochs=0)
    return verify_export(directory, expected=job)


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def execute(command, out, label, timeout):
    start = time.perf_counter()
    stdout_path, stderr_path = out / (label + '.stdout.log'), out / (label + '.stderr.log')
    timed_out = False
    with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
        try:
            completed = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=timeout)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out, code = True, None
    return dict(command=command, returncode=code, timed_out=timed_out,
                elapsed_seconds=time.perf_counter() - start,
                stdout=stdout_path.name, stderr=stderr_path.name,
                stdout_sha256=sha256(stdout_path), stderr_sha256=sha256(stderr_path))


def audit_sanitizer(path, tool):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    if tool == 'racecheck':
        hits = re.findall(r'RACECHECK SUMMARY:\s*(\d+) hazards displayed\s*\((\d+) errors,\s*(\d+) warnings\)', text)
        if not hits or any(tuple(map(int, values)) != (0, 0, 0) for values in hits):
            raise ValueError('racecheck report missing or nonzero')
    else:
        hits = re.findall(r'ERROR SUMMARY:\s*(\d+) errors?', text)
        if not hits or any(int(value) for value in hits):
            raise ValueError(f'{tool} report missing or nonzero')
    return dict(status='passed', tool=tool, summaries=len(hits))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--case', help='regular expression selecting case names')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--sanitizer-exe', type=Path)
    parser.add_argument('--sanitizer-tools', nargs='+', choices=('memcheck', 'synccheck', 'racecheck'),
                        default=['memcheck', 'synccheck', 'racecheck'])
    args = parser.parse_args()
    jobs = [job for job in cases() if args.case is None or re.search(args.case, job['name'])]
    if args.list:
        print(json.dumps(jobs, indent=2))
        return 0
    if args.out is None:
        parser.error('--out is required')
    out = args.out.resolve()
    if args.verify_only:
        from universal_reference import verify_export, verify_engine_seal
        report = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
        for record in report['cases']:
            if record.get('execution') is None:
                raise ValueError('cannot verify an unexecuted case')
            actual = verify_case(out / record['export'], record['task'], record['execution'], out)
            if actual != record['verification']:
                raise ValueError('retained verification differs: ' + record['task']['name'])
            if not record['task'].get('configuration_error') and not record['task'].get('resource_refused'):
                if verify_engine_seal(out / record['export'], expected=record['task']) != record.get('seal'):
                    raise ValueError('retained seal differs')
            for channel in ('stdout', 'stderr'):
                command = record['execution']
                if sha256(out / command[channel]) != command[channel + '_sha256']:
                    raise ValueError('retained log changed')
        by_name = {record['task']['name']: record['task'] for record in report['cases']}
        for record in report.get('sanitizers', []):
            task = by_name[record['case']]
            label = record['tool'] + '_' + record['case']
            actual = verify_export(out / label, expected=task)
            if actual != record['verification'] or verify_engine_seal(out / label, expected=task) != record['seal']:
                raise ValueError('retained sanitizer export/seal differs')
            command = record['execution']
            for channel in ('stdout', 'stderr'):
                if sha256(out / command[channel]) != command[channel + '_sha256']:
                    raise ValueError('retained sanitizer log changed')
            combined = out / (label + '.sanitizer.log')
            if combined.read_bytes() != (out / command['stderr']).read_bytes() + (out / command['stdout']).read_bytes():
                raise ValueError('combined sanitizer log differs from raw streams')
            if audit_sanitizer(combined, record['tool']) != record['sanitizer']:
                raise ValueError('saved sanitizer audit differs')
        print(json.dumps(dict(status='passed', verified_cases=len(report['cases']),
                              verified_sanitizer_cases=len(report.get('sanitizers', [])))))
        return 0
    if not jobs:
        parser.error('case selection is empty')
    if not args.prepare_only and (args.exe is None or not args.exe.is_file()):
        parser.error('--exe must identify an existing CUDA executable')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'programs').mkdir()
    report = dict(schema='atomOS-universal-validation-v1', status='not_run',
                  started_utc=datetime.now(timezone.utc).isoformat(),
                  executable=str(args.exe.resolve()) if args.exe else None,
                  executable_sha256=sha256(args.exe) if args.exe else None,
                  source_hashes_before={name: sha256(ROOT / name) for name in AUDIT_SOURCES},
                  cases=[], sanitizers=[])
    for job in jobs:
        program = out / 'programs' / (job['name'] + '.atomos')
        program.write_text(job['program'], encoding='utf-8')
        export = 'run_' + job['name']
        record = dict(task=job, program=str(program.relative_to(out)), program_sha256=sha256(program),
                      export=export, expected=expected_attempts(job, program))
        report['cases'].append(record)
        if not args.prepare_only:
            from universal_reference import verify_export
            command = command_for(args.exe.resolve(), job, program, out / export)
            record['execution'] = execute(command, out, job['name'], args.timeout)
            try:
                expected_code = 3 if job.get('resource_refused') else 1 if job.get('configuration_error') else 0 if record['expected'][-1]['accepted'] else 2
                if record['execution']['returncode'] != expected_code:
                    raise ValueError(f'exit code {record["execution"]["returncode"]}; expected {expected_code}')
                record['verification'] = verify_case(out / export, job, record['execution'], out)
                if not job.get('configuration_error') and not job.get('resource_refused'):
                    from universal_reference import seal_engine
                    record['seal'] = seal_engine(out / export, expected=job)
            except Exception as error:
                record['verification'] = dict(status='failed', error=str(error))
            print(job['name'] + ': ' + record['verification']['status'], flush=True)
        save_json(out / 'summary.json', report)
    if args.sanitizer_exe and not args.prepare_only:
        selected = [job for job in jobs if job['name'] in
                    ('unary_increment_across_epochs', 'alphabet_33_packed_writes', 'walker_later_epoch_rejection')]
        for tool in args.sanitizer_tools:
            for job in selected:
                label = tool + '_' + job['name']
                program = out / 'programs' / (job['name'] + '.atomos')
                command = [str(args.sanitizer_exe.resolve()), '--tool', tool, '--error-exitcode', '86',
                           *command_for(args.exe.resolve(), job, program, out / label)]
                record = dict(tool=tool, case=job['name'], execution=execute(command, out, label, args.timeout))
                try:
                    attempts = expected_attempts(job, program)
                    if record['execution']['returncode'] != (0 if attempts[-1]['accepted'] else 2):
                        raise ValueError('sanitizer application exit differs')
                    record['verification'] = verify_export(out / label, expected=job)
                    from universal_reference import seal_engine
                    record['seal'] = seal_engine(out / label, expected=job)
                    log = out / record['execution']['stderr']
                    # Compute Sanitizer installations may use either output stream.
                    combined = out / (label + '.sanitizer.log')
                    combined.write_bytes(log.read_bytes() + (out / record['execution']['stdout']).read_bytes())
                    record['sanitizer'] = audit_sanitizer(combined, tool)
                except Exception as error:
                    record['verification'] = dict(status='failed', error=str(error))
                report['sanitizers'].append(record)
                save_json(out / 'summary.json', report)
    if not args.prepare_only:
        report['source_hashes_after'] = {name: sha256(ROOT / name) for name in AUDIT_SOURCES}
        report['executable_sha256_after'] = sha256(args.exe)
        report['source_and_executable_unchanged'] = (report['source_hashes_before'] == report['source_hashes_after']
            and report['executable_sha256'] == report['executable_sha256_after'])
        passed = all(row['verification']['status'] == 'passed' for row in report['cases'] + report['sanitizers'])
        passed = passed and report['source_and_executable_unchanged']
        report.update(status='passed' if passed else 'failed',
                      executed_cases=len(report['cases']), sanitizer_cases=len(report['sanitizers']))
        good = [r['verification'] for r in report['cases'] if r['verification']['status'] == 'passed']
        report.update(verified_u_transitions=sum(r['u_transitions'] for r in good),
                      verified_k1_lane_epochs=sum(r['k1_lane_epochs'] for r in good))
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    save_json(out / 'summary.json', report)
    print(json.dumps(dict(status=report['status'], summary=str(out / 'summary.json'))))
    return 0 if report['status'] == 'passed' else 3 if report['status'] == 'not_run' else 1


if __name__ == '__main__':
    raise SystemExit(main())
