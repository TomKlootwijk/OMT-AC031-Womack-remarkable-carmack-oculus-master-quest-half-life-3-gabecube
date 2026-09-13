#!/usr/bin/env python3
"""Run and retain an independently verified SDF/NOR GPU study.

Only an explicitly supplied CUDA executable is run. --prepare-only marks every
case not_run; unit tests and prepared commands are never reported as GPU evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from sdf_atlas import verify_atlas
from sdf_nor_reference import sha256, verify_export
from universal_reference import parse_program, initial_state, simulate
from validate_universal import program_text, execute, audit_sanitizer

AUDIT_SOURCES = ('python/sdf_nor_reference.py', 'python/sdf_atlas.py',
    'python/universal_reference.py', 'tools/validate_sdf_nor.py',
    'tools/validate_universal.py', 'include/atomos/sdf_nor.hpp',
    'include/atomos/universal.hpp', 'include/atomos/klein.hpp',
    'include/atomos/packed_atlas.hpp', 'include/atomos/core.hpp',
    'include/atomos/host.hpp', 'cuda/kernel.cu', 'experiments/sdf_universal.cu')


def cases():
    jobs = []

    def add(name, text, *, budget=64, origin=-128, cells=257, injection='none', layouts=('linear', 'morton8')):
        for layout in layouts:
            jobs.append(dict(name=f'{name}_{layout}', program=text, budget=budget,
                origin=origin, cells=cells, injection=injection, layout=layout,
                memory_mib=256, reserve_mib=512))

    for path in sorted((ROOT / 'examples/universal').glob('*.atomos')):
        for budget in (0, 1, 64):
            add(f'{path.stem}_budget{budget}', path.read_text(encoding='utf-8'), budget=budget)
    oscillator = (ROOT / 'examples/universal/bounded_oscillator.atomos').read_text(encoding='utf-8')
    for budget in (2, 16, 256, 4096):
        add(f'bounded_oscillator_budget{budget}', oscillator, budget=budget)
    for injection in ('texture', 'gate'):
        add('injected_' + injection, oscillator, budget=4, injection=injection)
    add('initial_halt_zero_budget', program_text(states=1, halts=(0,)), budget=0)
    add('left_boundary_after_write', program_text(states=1, halts=(),
        rules=((0, 0, 0, 1, 'L'), (0, 1, 0, 0, 'L'))), origin=-1, cells=5, budget=3)
    add('missing_rule_after_write', program_text(states=3, halts=(2,),
        rules=((0, 0, 1, 1, 'R'),)), budget=3)
    add('initial_head_outside_extent', program_text(head=9), origin=-1, cells=5, budget=0)
    for edge, head, origin, direction in (
        ('min', -(1 << 63), -(1 << 63), 'L'),
        ('max', (1 << 63) - 1, (1 << 63) - 3, 'R')):
        add(f'i64_{edge}_destination_rejection', program_text(head=head,
            rules=((0, 0, 1, 1, direction),)), origin=origin, cells=3, budget=1)
    for alphabet in (1, 3, 5, 33):
        add(f'alphabet{alphabet}_crossword_negative_origin', program_text(states=1,
            alphabet=alphabet, head=-3, halts=(),
            cells=((-4, alphabet - 1), (1, alphabet - 1)),
            rules=tuple((0, symbol, 0, alphabet - 1 - symbol, 'R') for symbol in range(alphabet))),
            budget=19, origin=-11, cells=37)
    return jobs


def expected_result(job):
    program = parse_program(job['program'])
    result = simulate(program, initial_state(program), origin=job['origin'],
                      cells=job['cells'], budget=job['budget'])
    return dict(stop=result['status_name'], transitions=result['steps'],
                accepted=result['accepted'] and job['injection'] == 'none',
                exit_code=0 if result['accepted'] and job['injection'] == 'none' else 2)


def command_for(exe, atlas, job, program, out):
    return [str(exe), '--program', str(program), '--atlas', str(atlas), '--out', str(out),
        '--steps', str(job['budget']), '--origin', str(job['origin']), '--cells', str(job['cells']),
        '--layout', job['layout'], '--inject', job['injection'],
        '--memory-mib', str(job['memory_mib']), '--reserve-mib', str(job['reserve_mib'])]


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def verify_record(out, record):
    execution = record.get('execution')
    if not execution or execution['timed_out'] or execution['returncode'] != record['expected']['exit_code']:
        raise ValueError('actual process exit/timeout differs from independently expected result')
    for channel in ('stdout', 'stderr'):
        if sha256(out / execution[channel]) != execution[channel + '_sha256']:
            raise ValueError('retained execution log changed')
    export = out / record['export']
    if sha256(out / record['program']) != record['program_sha256']:
        raise ValueError('study program changed')
    if (export / 'program.atomos').read_bytes() != (out / record['program']).read_bytes():
        raise ValueError('runtime copied a different program')
    # Bind the reported JSON in stdout to the on-disk export, not just exit0.
    stream = (out / execution['stdout']).read_text(encoding='utf-8', errors='replace')
    receipts = []
    for line in stream.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and value.get('schema') == 'atomOS-sdf-nor-universal-v1':
                receipts.append(value)
        except json.JSONDecodeError:
            pass
    exported = json.loads((export / 'summary.json').read_text(encoding='utf-8'))
    if len(receipts) != 1 or receipts[0] != exported:
        raise ValueError('process receipt differs from exported execution metadata')
    return verify_export(export, expected=record['task'])


def reverify(out):
    report = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    if report['status'] != 'passed' or not report.get('source_and_executable_unchanged'):
        raise ValueError('study is incomplete or failed')
    if sha256(report['executable']) != report['executable_sha256']:
        raise ValueError('retained executable changed')
    for name, digest in report['source_hashes_before'].items():
        if sha256(ROOT / name) != digest:
            raise ValueError('validated source changed: ' + name)
    for record in report['cases'] + report['sanitizers']:
        if verify_record(out, record) != record['verification']:
            raise ValueError('independent replay differs from retained verification')
        if 'tool' in record:
            execution = record['execution']
            combined = out / (record['name'] + '.sanitizer.log')
            if combined.read_bytes() != (out / execution['stderr']).read_bytes() + (out / execution['stdout']).read_bytes():
                raise ValueError('sanitizer combined log changed')
            if audit_sanitizer(combined, record['tool']) != record['sanitizer']:
                raise ValueError('sanitizer audit changed')
    return dict(status='passed', independently_reverified_cases=len(report['cases']),
                independently_reverified_sanitizers=len(report['sanitizers']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--atlas', type=Path)
    parser.add_argument('--case', help='regular expression selecting case names')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
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
        print(json.dumps(reverify(out)))
        return 0
    if not jobs:
        parser.error('case selection is empty')
    if args.atlas is None or not args.atlas.is_file():
        parser.error('--atlas must name an existing nor_sites atlas with its .json manifest')
    atlas = args.atlas.resolve()
    validated_atlas = verify_atlas(atlas)
    if validated_atlas['manifest']['profile'] != 'nor_sites':
        parser.error('the study requires the nor_sites scalar geometry construction')
    if not args.prepare_only and (args.exe is None or not args.exe.is_file()):
        parser.error('--exe must identify an existing CUDA executable')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'programs').mkdir()
    report = dict(schema='atomOS-sdf-nor-study-v1', status='not_run',
        started_utc=datetime.now(timezone.utc).isoformat(),
        executable=str(args.exe.resolve()) if args.exe else None,
        executable_sha256=sha256(args.exe) if args.exe else None,
        atlas=str(atlas), atlas_sha256=sha256(atlas),
        atlas_manifest_sha256=sha256(atlas.with_suffix('.json')),
        source_hashes_before={name: sha256(ROOT / name) for name in AUDIT_SOURCES},
        cases=[], sanitizers=[])

    def run(job, name, tool=None):
        program = out / 'programs' / (job['name'] + '.atomos')
        if not program.exists():
            program.write_text(job['program'], encoding='utf-8')
        record = dict(name=name, task=job, program=str(program.relative_to(out)),
            program_sha256=sha256(program), export='run_' + name, expected=expected_result(job))
        if tool:
            record['tool'] = tool
        if not args.prepare_only:
            command = command_for(args.exe.resolve(), atlas, job, program, out / record['export'])
            if tool:
                command = [str(args.sanitizer_exe.resolve()), '--tool', tool, '--error-exitcode', '86', *command]
            record['execution'] = execute(command, out, name, args.timeout)
            try:
                record['verification'] = verify_record(out, record)
                if tool:
                    execution = record['execution']
                    combined = out / (name + '.sanitizer.log')
                    combined.write_bytes((out / execution['stderr']).read_bytes() + (out / execution['stdout']).read_bytes())
                    record['sanitizer'] = audit_sanitizer(combined, tool)
            except Exception as error:
                record['verification'] = dict(status='failed', error=str(error))
            print(name + ': ' + record['verification']['status'], flush=True)
        return record

    for job in jobs:
        job['atlas_sha256'] = report['atlas_sha256']
        report['cases'].append(run(job, job['name']))
        save(out / 'summary.json', report)
    if args.sanitizer_exe and not args.prepare_only:
        preferred = ('bounded_oscillator_budget64_morton8', 'alphabet33_crossword_negative_origin_linear',
                     'left_boundary_after_write_morton8')
        selected = [job for job in jobs if job['name'] in preferred]
        if not selected:
            selected = [jobs[0]]
        for tool in args.sanitizer_tools:
            for job in selected:
                report['sanitizers'].append(run(job, tool + '_' + job['name'], tool))
                save(out / 'summary.json', report)
    if not args.prepare_only:
        report['source_hashes_after'] = {name: sha256(ROOT / name) for name in AUDIT_SOURCES}
        report['executable_sha256_after'] = sha256(args.exe)
        report['source_and_executable_unchanged'] = (
            report['source_hashes_before'] == report['source_hashes_after'] and
            report['executable_sha256'] == report['executable_sha256_after'] and
            report['atlas_sha256'] == sha256(atlas) and
            report['atlas_manifest_sha256'] == sha256(atlas.with_suffix('.json')))
        good = [record['verification'] for record in report['cases'] + report['sanitizers']]
        passed = all(value['status'] == 'passed' for value in good) and report['source_and_executable_unchanged']
        report.update(status='passed' if passed else 'failed', executed_cases=len(report['cases']),
            sanitizer_cases=len(report['sanitizers']))
        report['verified_counts'] = {key: sum(value[key] for value in good if value['status'] == 'passed')
            for key in ('compiler_truth_rows', 'controller_evaluations', 'gate_evaluations',
                        'tm_transitions', 'actual_transitions', 'packed_tape_words_verified')}
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    save(out / 'summary.json', report)
    print(json.dumps(dict(status=report['status'], summary=str(out / 'summary.json'))))
    return 0 if report['status'] == 'passed' else 3 if report['status'] == 'not_run' else 1


if __name__ == '__main__':
    raise SystemExit(main())
