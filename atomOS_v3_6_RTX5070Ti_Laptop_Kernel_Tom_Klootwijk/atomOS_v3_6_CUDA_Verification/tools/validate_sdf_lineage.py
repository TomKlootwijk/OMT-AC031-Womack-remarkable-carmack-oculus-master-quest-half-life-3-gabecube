#!/usr/bin/env python3
"""Bounded native GPU lineage study with independent replay and retained logs."""
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
from sdf_lineage_reference import U64, canonical, proposals, emission, filter_words, verify_export
from sdf_nor_reference import sha256
from validate_universal import execute, audit_sanitizer

SOURCES = ('include/atomos/sdf_lineage.hpp', 'experiments/sdf_lineage.cu',
    'include/atomos/klein.hpp', 'include/atomos/packed_atlas.hpp',
    'include/atomos/core.hpp', 'include/atomos/host.hpp', 'cuda/kernel.cu',
    'python/sdf_lineage_reference.py', 'python/sdf_atlas.py', 'python/reference.py',
    'python/sdf_nor_reference.py', 'tools/validate_sdf_lineage.py',
    'tools/validate_universal.py')


def cases(atlas_dir):
    jobs = []
    def add(name, atlas='transparent_3_32', **patch):
        defaults = dict(atlas=str((atlas_dir / (atlas + '.atlas')).resolve()),
            generations_requested=6, max_frontier=4096, seed_id=1, seed_live=1,
            seed_row=0, seed_angle=0, phi_steps=1, diagnostic_profile='source',
            q_initial=0, j=0, k=0, memory_mib=256, reserve_mib=512)
        defaults.update(patch)
        for layout in ('linear', 'morton8'):
            jobs.append(dict(defaults, name=name + '_' + layout, layout=layout))
    add('transparent_growth')
    for phi in (0, 32, 33, 64, 65536):
        add('hinge_' + str(phi), phi_steps=phi, generations_requested=5, q_initial=1, j=1, k=1)
    for j, k in ((0, 0), (0, 1), (1, 0), (1, 1)):
        add(f'directed_j{j}k{k}', j=j, k=k, q_initial=1, diagnostic_profile='directed', generations_requested=4)
    add('directed_zero_hinge', phi_steps=0, diagnostic_profile='directed', generations_requested=3)
    add('frontier_cap_prefix', max_frontier=16, generations_requested=20, q_initial=1, j=1, k=1)
    add('frontier_cap_initial', max_frontier=1, generations_requested=3, q_initial=1, j=1, k=1)
    add('id_overflow_prefix', seed_id=U64 // 2, generations_requested=3, q_initial=1, j=1, k=1)
    add('id_overflow_initial', seed_id=U64 // 2 + 1, generations_requested=3, q_initial=1, j=1, k=1)
    add('empty_seed', seed_live=0, q_initial=1, j=1, k=1)
    add('zero_generation_budget', generations_requested=0, q_initial=1, j=1, k=1)
    add('negative_seed_lift', seed_row=-7, seed_angle=-33, phi_steps=33)
    add('signed_min_seed_lift', seed_row=-(1 << 63), seed_angle=-(1 << 63), generations_requested=3)
    add('signed_max_seed_lift', seed_row=(1 << 63) - 1, seed_angle=(1 << 63) - 1, generations_requested=3)
    for atlas, width in (('geometry_17_257', 257), ('nor_8_64', 64)):
        for phi in (0, 1, width + 1, 2 * width):
            add(f'{atlas}_hinge{phi}', atlas=atlas, phi_steps=phi, seed_angle=0,
                generations_requested=5, diagnostic_profile='directed', q_initial=1, j=1, k=1)
    return jobs


def expected_result(job, atlas):
    height, width = atlas['rows'], atlas['angles']
    row, angle, _ = canonical(job['seed_row'], job['seed_angle'], height, width)
    frontier = [dict(id=job['seed_id'], row=row, angle=angle)] if job['seed_live'] else []
    q = [job['q_initial']] * (height * atlas['words_per_row'])
    committed, status, stop = 0, 'passed', 'generation_budget'
    for _ in range(job['generations_requested']):
        if not frontier:
            stop = 'extinct'
            break
        if any(leaf['id'] > U64 // 2 for leaf in frontier):
            status, stop = 'resource_refused', 'lineage_overflow'
            break
        if 2 * len(frontier) > job['max_frontier']:
            status, stop = 'resource_refused', 'frontier_cap'
            break
        children = proposals(frontier, height, width, job['phi_steps'], job['diagnostic_profile'])
        filtered = filter_words(emission(children, height, width), atlas, job['j'], job['k'], q)
        count = atlas['words_per_row']
        frontier = [{key: child[key] for key in ('id', 'row', 'angle')} for child in children
            if (filtered[child['row'] * count + child['angle'] // 32]['output'] >> (child['angle'] % 32)) & 1]
        q = [word['q_after'] for word in filtered]
        committed += 1
    if not frontier and status == 'passed':
        stop = 'extinct'
    return dict(status=status, stop_reason=stop, generations=committed,
                final_frontier=len(frontier), exit_code=3 if status == 'resource_refused' else 0)


def command_for(exe, job, out):
    command = [str(exe), '--atlas', job['atlas'], '--out', str(out)]
    mapping = dict(generations_requested='generations', max_frontier='max-frontier',
        seed_id='seed-id', seed_live='seed-live', seed_row='seed-row', seed_angle='seed-angle',
        phi_steps='phi-steps', diagnostic_profile='diagnostic-profile', q_initial='q',
        j='j', k='k', memory_mib='memory-mib', reserve_mib='reserve-mib', layout='layout')
    for key, flag in mapping.items():
        command += ['--' + flag, str(job[key])]
    return command


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def export_hashes(directory):
    return {str(path.relative_to(directory)).replace('\\', '/'): sha256(path)
        for path in sorted(directory.rglob('*')) if path.is_file()}


def verify_record(out, record):
    run = record['execution']
    if run['timed_out'] or run['returncode'] != record['expected']['exit_code']:
        raise ValueError('actual process exit/timeout differs from independent expected execution')
    for channel in ('stdout', 'stderr'):
        if sha256(out / run[channel]) != run[channel + '_sha256']:
            raise ValueError('execution log changed')
    directory = out / record['export']
    if 'export_hashes' in record and export_hashes(directory) != record['export_hashes']:
        raise ValueError('retained export file inventory/hash changed')
    receipt = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    stdout = (out / run['stdout']).read_text(encoding='utf-8', errors='replace')
    messages = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and value.get('schema') == 'atomOS-sdf-lineage-v1':
                messages.append(value)
        except json.JSONDecodeError:
            pass
    if messages != [receipt]:
        raise ValueError('process receipt differs from exported metadata')
    verified = verify_export(directory, expected=record['task'])
    for actual, expected in ((verified['execution_status'], record['expected']['status']),
        (verified['stop_reason'], record['expected']['stop_reason']),
        (verified['generations'], record['expected']['generations']),
        (receipt['final_frontier_count'], record['expected']['final_frontier'])):
        if actual != expected:
            raise ValueError('retained native result differs from precomputed Python result')
    return verified


def reverify(out):
    report = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    if report['status'] != 'passed' or not report['source_and_executable_unchanged']:
        raise ValueError('study incomplete or failed')
    if sha256(report['executable']) != report['executable_sha256']:
        raise ValueError('executable changed')
    for source, digest in report['source_hashes_before'].items():
        if sha256(ROOT / source) != digest:
            raise ValueError('validated source changed: ' + source)
    for record in report['cases'] + report['sanitizers']:
        if verify_record(out, record) != record['verification']:
            raise ValueError('independent replay changed')
        if 'tool' in record:
            combined = out / (record['name'] + '.sanitizer.log')
            run = record['execution']
            if combined.read_bytes() != (out / run['stderr']).read_bytes() + (out / run['stdout']).read_bytes():
                raise ValueError('sanitizer log changed')
            if audit_sanitizer(combined, record['tool']) != record['sanitizer']:
                raise ValueError('sanitizer result changed')
    return dict(status='passed', independently_reverified_cases=len(report['cases']),
                independently_reverified_sanitizers=len(report['sanitizers']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--atlas-dir', type=Path, default=ROOT / 'results/sdf_klein_20260913/atlases')
    parser.add_argument('--case')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--sanitizer-exe', type=Path)
    args = parser.parse_args()
    if args.verify_only:
        if not args.out:
            parser.error('--out required')
        print(json.dumps(reverify(args.out.resolve())))
        return 0
    jobs = [job for job in cases(args.atlas_dir) if not args.case or re.search(args.case, job['name'])]
    if args.list:
        print(json.dumps(jobs, indent=2))
        return 0
    if not args.out or not jobs:
        parser.error('--out and at least one selected case required')
    if not args.prepare_only and (not args.exe or not args.exe.is_file()):
        parser.error('--exe must be an existing native CUDA executable')
    atlases = {name: verify_atlas(name) for name in sorted({job['atlas'] for job in jobs})}
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema='atomOS-sdf-lineage-study-v1', status='not_run',
        started_utc=datetime.now(timezone.utc).isoformat(),
        executable=str(args.exe.resolve()) if args.exe else None,
        executable_sha256=sha256(args.exe) if args.exe else None,
        source_hashes_before={source: sha256(ROOT / source) for source in SOURCES},
        atlases={name: dict(binary_sha256=sha256(name), manifest_sha256=sha256(Path(name).with_suffix('.json'))) for name in atlases},
        cases=[], sanitizers=[])
    def run(job, name, tool=None):
        job = dict(job, atlas_sha256=sha256(job['atlas']))
        record = dict(name=name, task=job, export='run_' + name,
                      expected=expected_result(job, atlases[job['atlas']]))
        command = command_for(args.exe.resolve() if args.exe else Path('NOT_RUN.exe'), job, out / record['export'])
        if tool:
            command = [str(args.sanitizer_exe.resolve()), '--tool', tool, '--error-exitcode', '86'] + command
            record['tool'] = tool
        record['command'] = command
        if not args.prepare_only:
            record['execution'] = execute(command, out, name, args.timeout)
            try:
                record['verification'] = verify_record(out, record)
                record['export_hashes'] = export_hashes(out / record['export'])
                if tool:
                    run = record['execution']
                    combined = out / (name + '.sanitizer.log')
                    combined.write_bytes((out / run['stderr']).read_bytes() + (out / run['stdout']).read_bytes())
                    record['sanitizer'] = audit_sanitizer(combined, tool)
            except Exception as error:
                record['verification'] = dict(status='failed', error=str(error))
            print(name + ': ' + record['verification']['status'], flush=True)
        return record
    for job in jobs:
        report['cases'].append(run(job, job['name']))
        save(out / 'summary.json', report)
    if args.sanitizer_exe and not args.prepare_only:
        names = ('transparent_growth_morton8', 'directed_j1k1_linear', 'frontier_cap_prefix_morton8')
        selected = [job for job in jobs if job['name'] in names] or [jobs[0]]
        for tool in ('memcheck', 'synccheck', 'racecheck'):
            for job in selected:
                report['sanitizers'].append(run(job, tool + '_' + job['name'], tool))
                save(out / 'summary.json', report)
    if not args.prepare_only:
        report['source_hashes_after'] = {source: sha256(ROOT / source) for source in SOURCES}
        report['executable_sha256_after'] = sha256(args.exe)
        report['source_and_executable_unchanged'] = report['source_hashes_before'] == report['source_hashes_after'] and report['executable_sha256'] == report['executable_sha256_after'] and all(
            sha256(name) == value['binary_sha256'] and sha256(Path(name).with_suffix('.json')) == value['manifest_sha256'] for name, value in report['atlases'].items())
        results = [record['verification'] for record in report['cases'] + report['sanitizers']]
        report['status'] = 'passed' if report['source_and_executable_unchanged'] and all(result['status'] == 'passed' for result in results) else 'failed'
        report['verified_counts'] = {key: sum(result[key] for result in results if result['status'] == 'passed') for key in ('generations', 'children', 'diagnostics', 'admitted_ids', 'searches', 'words', 'sdf_bits')}
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    save(out / 'summary.json', report)
    print(json.dumps(dict(status=report['status'], summary=str(out / 'summary.json'))))
    return 0 if report['status'] == 'passed' else 3 if report['status'] == 'not_run' else 1


if __name__ == '__main__':
    raise SystemExit(main())
