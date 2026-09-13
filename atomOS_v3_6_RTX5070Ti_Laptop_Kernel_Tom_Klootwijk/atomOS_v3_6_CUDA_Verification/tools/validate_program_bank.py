"""Native packed skill conformance, sanitizer, cold-cache and VRAM admission study."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from program_bank_reference import decode_bank, evaluate, verify_trace
from profile_cache import METRICS, parse_metrics, read_log, resolve_ncu
from validate import find_compute_sanitizer


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_injected_rejection(folder, exit_code, *, bank_path, atlas_path,
                              initial_slot, input_value, injection, mode='chain'):
    """A process failure alone is not evidence of transactional fault rejection."""
    folder = Path(folder)
    if exit_code != 2:
        raise ValueError('injection run did not return verified-rejection exit code 2')
    if not (folder/'REJECTED').is_file() or (folder/'COMMITTED').exists():
        raise ValueError('injection run lacks an exclusive REJECTED marker')
    try:
        receipt = json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('injection run lacks a readable rejection receipt') from error
    if (receipt.get('schema') != 'atomOS-program-bank-runtime-v1' or
            receipt.get('status') != 'rejected_verification' or
            receipt.get('accepted') is not False or receipt.get('committed') is not False or
            receipt.get('injection') != injection or receipt.get('execution_mode') != mode):
        raise ValueError('injection receipt does not establish the requested rejection')
    for field, expected in (('initial_slot', initial_slot), ('input_initial', input_value),
                            ('committed_program_id', initial_slot), ('committed_input', input_value)):
        if type(receipt.get(field)) is not int or receipt[field] != expected:
            raise ValueError('rejected proposal changed or misreported initial committed state: '+field)
    for actual, expected in ((folder/'bank.bin', bank_path), (folder/'operators.atlas', atlas_path)):
        if not actual.is_file() or file_hash(actual) != file_hash(expected):
            raise ValueError('rejection immutable input binding failed')
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('exe', 'bank', 'atlas', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--sanitizer', action='store_true')
    p.add_argument('--profile', action='store_true')
    p.add_argument('--capacity-fraction', type=float, default=0)
    p.add_argument('--smoke', action='store_true', help='Short integration check; not exhaustive evidence')
    p.add_argument('--domain-only', action='store_true', help='Additional shape audit: exhaustive native domains and optional domain memcheck')
    a = p.parse_args()
    if not 0 <= a.capacity_fraction <= .90:
        p.error('capacity fraction must be 0..0.90')
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    exe, path, atlas = a.exe.resolve(), a.bank.resolve(), a.atlas.resolve()
    bank = decode_bank(path, path.parent/'manifest.json')
    # Bind finite teacher labels independently of native and compiler evaluators.
    teacher_path = path.parent/'teacher_examples.json'
    teacher_checks = 0
    if teacher_path.exists():
        teacher = json.loads(teacher_path.read_text(encoding='utf-8'))
        manifest = json.loads((path.parent/'manifest.json').read_text(encoding='utf-8'))
        by_name = {s['name']: s for s in teacher['skills']}
        for cap, descriptor in zip(bank['capsules'], manifest['capsules']):
            for row in by_name[descriptor['name']].get('full_domain', []):
                if evaluate(cap, row['input']) != row['output']:
                    raise ValueError('independent teacher function mismatch')
                teacher_checks += 1
    source_paths = ['experiments/program_bank.cu', 'include/atomos/program_bank.hpp',
                    'include/atomos/sdf_nor.hpp', 'python/program_bank.py',
                    'python/program_bank_reference.py', 'tools/validate_program_bank.py',
                    'include/atomos/publication.hpp', 'include/atomos/klein.hpp',
                    'include/atomos/host.hpp', 'include/atomos/core.hpp',
                    'include/atomos/universal.hpp', 'include/atomos/packed_atlas.hpp', 'cuda/kernel.cu']
    report = dict(schema='atomos-program-bank-study-v1', status='running',
                  scope='finite skill and bounded chain execution; no language-model replacement claim',
                  executable=str(exe), executable_sha256=file_hash(exe),
                  bank=str(path), bank_file_sha256=file_hash(path), atlas=str(atlas),
                  atlas_sha256=file_hash(atlas), independent_teacher_cases=teacher_checks,
                  source_hashes={f:file_hash(ROOT/f) for f in source_paths}, runs=[])
    def save():
        (out/'study.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    save()
    ncu = resolve_ncu(None) if a.profile else None
    sanitizer = find_compute_sanitizer() if a.sanitizer else None
    if (a.profile and ncu is None) or (a.sanitizer and sanitizer is None):
        report.update(status='not_run', reason='requested native analysis tool unavailable'); save(); return 3
    def run(label, *, layout='linear', value=7, hops=12, first=0, extra=(),
            injection='none', prefix=(), kind='ordinary', mode='chain'):
        folder = out/label
        command = [str(exe), '--bank', str(path), '--atlas', str(atlas), '--layout', layout,
                   '--input', str(value), '--hops', str(hops), '--initial-slot', str(first),
                   '--reserve-mib', '1536', '--mode', mode, '--inject', injection, '--out', str(folder), *map(str, extra)]
        raw = out/(label+'.counters.log')
        if kind == 'cold':
            command = [str(ncu), '--replay-mode', 'kernel', '--cache-control', 'all',
                       '--clock-control', 'none', '--kernel-name', 'regex:atomos_program_bank',
                       '--launch-count', '1', '--check-exit-code', '1', '--metrics', ','.join(METRICS),
                       '--csv', '--page', 'raw', '--print-units', 'base', '--log-file', str(raw), *command]
        command = [*map(str, prefix), *command]
        started = time.perf_counter()
        with (out/(label+'.log')).open('w', encoding='utf-8') as log:
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        record = dict(label=label, kind=kind, command=command, exit_code=completed.returncode,
                      wall_seconds=time.perf_counter()-started)
        report['runs'].append(record); save()
        if injection != 'none':
            record['receipt'] = verify_injected_rejection(folder, completed.returncode,
                bank_path=path, atlas_path=atlas, initial_slot=first, input_value=value,
                injection=injection, mode=mode)
            record['expected_rejection'] = True
            save(); return record
        if completed.returncode:
            raise RuntimeError('native run failed: '+label)
        receipt = json.loads((folder/'summary.json').read_text(encoding='utf-8'))
        if not receipt['accepted'] or not (folder/'COMMITTED').is_file():
            raise ValueError('native result lacks verified commit')
        for actual, expected in ((folder/'bank.bin', path), (folder/'operators.atlas', atlas)):
            if file_hash(actual) != file_hash(expected):
                raise ValueError('exported immutable input differs')
        if receipt['execution_mode'] != mode:
            raise ValueError('native execution mode mismatch')
        record['verification'] = verify_trace(folder/'trace.csv', bank, value, hops, first, mode)
        record['receipt'] = receipt
        if kind == 'cold':
            metrics = parse_metrics(read_log(raw), METRICS)
            if any(m.get('status') != 'collected' for m in metrics.values()):
                raise ValueError('required counter unavailable')
            trace = list(csv.DictReader((folder/'trace.csv').open(encoding='utf-8', newline='')))
            visited = len({int(r['physical_slot']) for r in trace})
            program_bytes = (receipt['pool_bytes'] if receipt['texture_sweep']=='full_pool'
                             else visited*receipt['program_page_bytes'])
            floor = (receipt['operator_texture_bytes'] + program_bytes)//32
            sectors, hits, misses = [metrics[METRICS[i]]['value'] for i in (1,2,3)]
            if hits+misses != sectors or misses < floor:
                raise ValueError('TEX conservation/unique-footprint floor failed')
            record.update(metrics=metrics, unique_visited_pages=visited,
                          compulsory_miss_floor=floor, extra_misses=misses-floor,
                          at_compulsory_floor=misses==floor)
        (folder/'PYTHON_VERIFIED.json').write_text(json.dumps(record['verification'], indent=2)+'\n')
        save(); return record
    try:
        for layout in ('linear', 'morton8'):
            for first, capsule in enumerate(bank['capsules']):
                if a.smoke:
                    for value in (0,7,63):
                        run(f'domain_{layout}_{first}_{value}', layout=layout, value=value, hops=1, first=first)
                else:
                    run(f'domain_{layout}_{first}', layout=layout, value=0,
                        hops=1 << capsule['input_bits'], first=first, mode='domain')
            if a.domain_only:
                if sanitizer:
                    first=len(bank['capsules'])-1
                    run(f'memcheck_domain_{layout}', layout=layout, value=0,
                        hops=1 << bank['capsules'][first]['input_bits'], first=first, mode='domain',
                        prefix=(sanitizer,'--tool','memcheck','--error-exitcode','2'), kind='memcheck')
                continue
            for value in (0,1,7,63):
                run(f'chain_{layout}_{value}', layout=layout, value=value, hops=24)
            for fault in ('program','output'):
                run(f'reject_{layout}_{fault}', layout=layout, injection=fault)
            if sanitizer:
                for tool in ('memcheck','racecheck','synccheck'):
                    run(f'{tool}_{layout}', layout=layout, hops=24,
                        prefix=(sanitizer,'--tool',tool,'--error-exitcode','2'), kind=tool)
            if ncu:
                for trial in range(2):
                    run(f'cold_{layout}_{trial}', layout=layout, hops=24, kind='cold')
        if a.capacity_fraction:
            capacity = ('--fill-free-fraction',a.capacity_fraction,'--replica-stride',104729)
            run('capacity', layout='morton8', hops=32, extra=capacity)
            if ncu:
                run('capacity_cold', layout='morton8', hops=32, extra=capacity, kind='cold')
        if file_hash(exe) != report['executable_sha256'] or any(file_hash(ROOT/f)!=v for f,v in report['source_hashes'].items()):
            raise ValueError('source/binary changed during study')
        report.update(status='passed', native_runs=len(report['runs']), smoke_only=a.smoke, domain_only=a.domain_only)
    except Exception as error:
        report.update(status='failed', reason=str(error)); save(); raise
    save(); print(json.dumps(dict(status=report['status'], native_runs=len(report['runs']), study=str(out/'study.json'))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
