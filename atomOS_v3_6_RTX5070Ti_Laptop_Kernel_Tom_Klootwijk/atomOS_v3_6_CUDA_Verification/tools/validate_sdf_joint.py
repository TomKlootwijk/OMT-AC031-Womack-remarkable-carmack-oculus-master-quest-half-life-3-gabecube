#!/usr/bin/env python3
"""Retain real GPU joint executions and independently replay their causal chain.

The source-word rules and the newly declared geometric/NOR coupling are distinct
profiles. This finite study makes no claim that all source operators are SDFs.
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
from sdf_joint_reference import simulate_joint
from sdf_nor_reference import sha256
from universal_reference import parse_program
from validate_universal import execute, audit_sanitizer, program_text

AUDIT_SOURCES = ('python/sdf_joint_reference.py', 'python/sdf_nor_reference.py',
    'python/sdf_lineage_reference.py', 'python/sdf_atlas.py', 'python/reference.py',
    'python/universal_reference.py', 'tools/validate_sdf_joint.py', 'tools/validate_universal.py',
    'include/atomos/sdf_nor.hpp', 'include/atomos/sdf_lineage.hpp',
    'include/atomos/klein.hpp', 'include/atomos/universal.hpp',
    'include/atomos/core.hpp', 'include/atomos/host.hpp',
    'include/atomos/packed_atlas.hpp', 'cuda/kernel.cu', 'experiments/sdf_universal.cu',
    'experiments/sdf_joint.cu')


def cases(angles=64):
    jobs = []
    examples = {name: (ROOT / 'examples/universal' / (name + '.atomos')).read_text(encoding='utf-8')
                for name in ('binary_increment', 'bounded_oscillator')}

    def add(name, program, **options):
        for layout in ('linear', 'morton8'):
            job = dict(name=name + '_' + layout, program=program, layout=layout,
                budget=6, origin=-11, cells=37, phi_base=angles, max_frontier=128,
                seed_id=1, seed_live=1, seed_row=0, seed_angle=0,
                q_initial=0, j=1, k=1, interval=1.0, diagnostic_profile='source',
                injection='none', memory_mib=256, reserve_mib=512)
            job.update(options)
            jobs.append(job)

    for name, program in examples.items():
        for phi in (0, 1, angles, angles + 1, 2 * angles):
            add(name + '_phi' + str(phi), program, phi_base=phi)
        add(name + '_zero_budget', program, budget=0)
    oscillator = examples['bounded_oscillator']
    add('oscillator_extinct_but_U64', oscillator, phi_base=1, budget=64, max_frontier=2)
    add('empty_frontier_U64', oscillator, budget=64, max_frontier=1, seed_live=0)
    add('frontier_refusal_after_prefix', oscillator, budget=6, max_frontier=2)
    add('frontier_refusal_first_step', oscillator, max_frontier=1)
    add('lineage_id_overflow', oscillator, seed_id=1 << 63)
    add('tape_range_after_prefix', examples['binary_increment'], origin=0, cells=5, budget=8)
    add('missing_rule_after_prefix', program_text(states=3, halts=(2,),
        rules=((0, 0, 1, 1, 'S'),)))
    add('hinge_product_overflow', program_text(states=1, halts=(),
        rules=((0, 0, 0, 1, 'S'),)), phi_base=(1 << 32) - 1)
    add('negative_lifted_seed', oscillator, seed_row=-1, seed_angle=-1, phi_base=1)
    for injection in ('gate', 'word'):
        add('injected_' + injection, examples['binary_increment'], injection=injection)
    for j, k, label in ((0, 0, 'hold'), (1, 0, 'set'), (0, 1, 'reset')):
        add('JK_' + label + '_directed', oscillator, j=j, k=k, q_initial=1,
            diagnostic_profile='directed', interval=.125, budget=3)
    return jobs


def expected_result(job, atlas):
    result = simulate_joint(parse_program(job['program']), atlas,
        **{key: job[key] for key in ('budget', 'origin', 'cells', 'phi_base', 'max_frontier',
             'j', 'k', 'diagnostic_profile', 'seed_id', 'seed_live', 'seed_row', 'seed_angle', 'q_initial')})
    return dict(stop=result['stop'], applied_steps=len(result['steps']),
                controller_evaluations=len(result['evaluations']),
                exit_code=2 if job['injection'] != 'none' else 0 if result['stop'] in ('running', 'halted')
                else 3 if result['stop'] in ('frontier_cap', 'lineage_overflow', 'hinge_overflow') else 2)


def command_for(exe, atlas, job, program, out):
    command = [str(exe), '--atlas', str(atlas), '--program', str(program), '--out', str(out)]
    for key, option in (('budget', '--steps'), ('origin', '--origin'), ('cells', '--cells'),
        ('phi_base', '--base-phi-steps'), ('max_frontier', '--max-frontier'),
        ('seed_id', '--seed-id'), ('seed_live', '--seed-live'), ('seed_row', '--seed-row'),
        ('seed_angle', '--seed-angle'), ('q_initial', '--q'), ('j', '--j'), ('k', '--k'),
        ('interval', '--interval'), ('diagnostic_profile', '--diagnostic-profile'),
        ('layout', '--layout'), ('injection', '--inject'),
        ('memory_mib', '--memory-mib'), ('reserve_mib', '--reserve-mib')):
        command.extend([option, str(job[key])])
    return command


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def verify_record(out, record):
    from sdf_joint_reference import verify_export
    execution = record.get('execution')
    if not execution or execution['timed_out'] or execution['returncode'] != record['expected']['exit_code']:
        raise ValueError('joint process exit/timeout disagrees with expected execution')
    for channel in ('stdout', 'stderr'):
        if sha256(out / execution[channel]) != execution[channel + '_sha256']:
            raise ValueError('execution log changed')
    path = out / record['export']
    if sha256(out / record['program']) != record['program_sha256']:
        raise ValueError('study program changed')
    if (out / record['program']).read_bytes() != (path / 'program.atomos').read_bytes():
        raise ValueError('runtime program copy differs')
    receipts = []
    for line in (out / execution['stdout']).read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            receipt = json.loads(line)
            if isinstance(receipt, dict) and receipt.get('schema') == 'atomOS-sdf-joint-v1':
                receipts.append(receipt)
        except json.JSONDecodeError:
            pass
    if receipts != [json.loads((path / 'summary.json').read_text(encoding='utf-8'))]:
        raise ValueError('actual process receipt differs from exported summary')
    return verify_export(path, expected=record['task'])


def reverify(out):
    report = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    if report['status'] != 'passed' or not report['source_and_executable_unchanged']:
        raise ValueError('study has not completed successfully')
    if sha256(report['executable']) != report['executable_sha256']:
        raise ValueError('validated executable changed')
    if (sha256(report['atlas']) != report['atlas_sha256'] or
        sha256(Path(report['atlas']).with_suffix('.json')) != report['atlas_manifest_sha256']):
        raise ValueError('validated atlas or manifest changed')
    for name, digest in report['source_hashes_before'].items():
        if sha256(ROOT / name) != digest:
            raise ValueError('validated source changed: ' + name)
    for record in report['cases'] + report['sanitizers']:
        if verify_record(out, record) != record['verification']:
            raise ValueError('joint replay differs from retained result')
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
    parser.add_argument('--atlas', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--case')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--sanitizer-exe', type=Path)
    parser.add_argument('--sanitizer-tools', nargs='+', choices=('memcheck', 'synccheck', 'racecheck'),
                        default=['memcheck', 'synccheck', 'racecheck'])
    args = parser.parse_args()
    if args.verify_only:
        if args.out is None:
            parser.error('--out required')
        print(json.dumps(reverify(args.out.resolve())))
        return 0
    if args.list and args.atlas is None:
        print(json.dumps(cases(), indent=2))
        return 0
    if args.atlas is None or not args.atlas.is_file():
        parser.error('--atlas requires an existing nor_sites atlas and .json manifest')
    atlas_path = args.atlas.resolve()
    atlas = verify_atlas(atlas_path)
    if atlas['manifest']['profile'] != 'nor_sites':
        parser.error('joint study requires explicitly constructed nor_sites geometry')
    jobs = [job for job in cases(atlas['angles']) if not args.case or re.search(args.case, job['name'])]
    if args.list:
        print(json.dumps(jobs, indent=2))
        return 0
    if args.out is None or not jobs:
        parser.error('--out and a nonempty case selection required')
    if not args.prepare_only and (args.exe is None or not args.exe.is_file()):
        parser.error('--exe must name an actual CUDA executable')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'programs').mkdir()
    report = dict(schema='atomOS-sdf-joint-study-v1', status='not_run',
        started_utc=datetime.now(timezone.utc).isoformat(),
        executable=str(args.exe.resolve()) if args.exe else None,
        executable_sha256=sha256(args.exe) if args.exe else None,
        atlas=str(atlas_path), atlas_sha256=sha256(atlas_path),
        atlas_manifest_sha256=sha256(atlas_path.with_suffix('.json')),
        source_hashes_before={name: sha256(ROOT / name) for name in AUDIT_SOURCES}, cases=[], sanitizers=[])

    def run(job, name, tool=None):
        program = out / 'programs' / (job['name'] + '.atomos')
        if not program.exists():
            program.write_text(job['program'], encoding='utf-8')
        record = dict(name=name, task=job, program=str(program.relative_to(out)),
            program_sha256=sha256(program), export='run_' + name, expected=expected_result(job, atlas))
        if tool:
            record['tool'] = tool
        if not args.prepare_only:
            command = command_for(args.exe.resolve(), atlas_path, job, program, out / record['export'])
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
        job['atlas_manifest_sha256'] = report['atlas_manifest_sha256']
        report['cases'].append(run(job, job['name']))
        save(out / 'summary.json', report)
    if args.sanitizer_exe and not args.prepare_only:
        preferred = (f'binary_increment_phi{atlas["angles"]}_linear',
                     'bounded_oscillator_phi1_morton8', 'frontier_refusal_after_prefix_morton8')
        selected = [job for job in jobs if job['name'] in preferred] or [jobs[0]]
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
            report['atlas_sha256'] == sha256(atlas_path) and
            report['atlas_manifest_sha256'] == sha256(atlas_path.with_suffix('.json')))
        checked = [record['verification'] for record in report['cases'] + report['sanitizers']]
        report['status'] = 'passed' if all(value['status'] == 'passed' for value in checked) and report['source_and_executable_unchanged'] else 'failed'
        report.update(executed_cases=len(report['cases']), sanitizer_cases=len(report['sanitizers']))
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    save(out / 'summary.json', report)
    print(json.dumps(dict(status=report['status'], summary=str(out / 'summary.json'))))
    return 0 if report['status'] == 'passed' else 3 if report['status'] == 'not_run' else 1


if __name__ == '__main__':
    raise SystemExit(main())
