#!/usr/bin/env python3
"""Collect targeted Nsight Compute cache counters with explicit cold/warm replay.

Example: python tools/profile_cache.py --exe build/atomos_cuda --out cache_review
  --config texture,morton8,256,default --config texture-packed,linear,128,max-l1

This is profiling evidence, not a cache-pinning or complete-residency guarantee.
The profiled application checks candidates internally. Its event timings are
perturbed by profiling and are not used as ordinary kernel benchmark timings.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import itertools
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time

METRICS = (
    'l1tex__t_requests_pipe_tex_mem_texture_op_ld.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_hit.sum',
    'l1tex__t_sectors_pipe_tex_mem_texture_op_ld_lookup_miss.sum',
    'gpu__time_duration.sum',
)
CONDITIONS = {'cold': ('kernel', 'all'), 'warm': ('application', 'none')}


def configuration(raw: str) -> dict:
    parts = raw.split(',')
    if len(parts) != 4:
        raise argparse.ArgumentTypeError('config must be READ,LAYOUT,BLOCK,CACHE')
    read, layout, block, cache = parts
    if read not in ('texture', 'texture-packed', 'global') or layout not in ('linear', 'morton8'):
        raise argparse.ArgumentTypeError('invalid read path or layout')
    if block not in ('64', '128', '256') or cache not in ('default', 'max-l1'):
        raise argparse.ArgumentTypeError('block must be 64/128/256; cache must be default/max-l1')
    return dict(read=read, layout=layout, block_size=int(block), cache=cache)


def resolve_ncu(requested: Path | None) -> Path | None:
    found = str(requested) if requested else shutil.which('ncu')
    if not found:
        return None
    path = Path(found).resolve()
    if path.suffix.lower() in ('.bat', '.cmd'):
        # NVIDIA's Windows launcher forwards to this native executable. Do not
        # introduce a command shell just to execute the convenience wrapper.
        native = path.parent / 'target/windows-desktop-win7-x64/ncu.exe'
        return native if native.is_file() else None
    return path if path.is_file() else None


def parse_metrics(raw: str, names: tuple[str, ...] = METRICS) -> dict:
    """Parse wide or long CSV, retaining absent/unavailable counters as null.

    Requested sums in base units are integral counts or nanoseconds. Nsight uses
    the OS locale: Dutch 2.048 and English 2,048 both represent integer 2048.
    Preserve the original text alongside normalized values for review.
    """
    collected = {name: [] for name in names}

    def collect(name, value, unit):
        record = dict(raw_value=value, unit=unit, value=None)
        try:
            cleaned = value.replace('\u00a0', '').replace(' ', '')
            if re.fullmatch(r'\d{1,3}(?:[.]\d{3})+', cleaned) or re.fullmatch(r'\d{1,3}(?:[,]\d{3})+', cleaned):
                cleaned = cleaned.replace('.', '').replace(',', '')
            elif ',' in cleaned:
                cleaned = cleaned.replace(',', '.')
            number = Decimal(cleaned)
            if not number.is_finite() or number != number.to_integral_value() or number < 0:
                raise InvalidOperation
            record.update(status='collected', value=int(number))
        except (InvalidOperation, ValueError, OverflowError):
            record.update(status='not_run', reason='counter unavailable or not a nonnegative integer in base units')
        collected[name].append(record)

    columns = None
    wide = None
    units = None
    for row in csv.reader(io.StringIO(raw)):
        row = [field.lstrip('\ufeff').strip() for field in row]
        if {'Metric Name', 'Metric Value', 'Metric Unit'}.issubset(row):
            columns = {name: row.index(name) for name in ('Metric Name', 'Metric Value', 'Metric Unit')}
            wide = None
            continue
        if 'ID' in row and any(name in row for name in names):
            wide = {name: row.index(name) for name in names if name in row}
            columns = None
            units = None
            continue
        if columns is not None and len(row) > max(columns.values()):
            name = row[columns['Metric Name']]
            if name in collected:
                collect(name, row[columns['Metric Value']], row[columns['Metric Unit']])
        elif wide is not None and len(row) > max(wide.values()):
            if units is None and row[0] == '':
                units = row
                continue
            if row[0].isdigit():
                for name, index in wide.items():
                    collect(name, row[index], units[index] if units else '')
    result = {}
    for name, records in collected.items():
        if not records:
            result[name] = dict(status='not_run', value=None, unit=None, reason='metric absent from profiler CSV')
        elif len(records) != 1:
            result[name] = dict(status='failed', value=None, unit=None, reason='expected one profiled launch per metric', records=records)
        else:
            result[name] = records[0]
    return result


def read_log(path: Path) -> str:
    if not path.is_file():
        return ''
    raw = path.read_bytes()
    encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    return raw.decode(encoding, errors='replace')


def aggregate(runs: list[dict]) -> list[dict]:
    summaries = []
    key = lambda r: (json.dumps(r['config'], sort_keys=True), r['condition'])
    for _, group in itertools.groupby(sorted(runs, key=key), key=key):
        samples = list(group)
        summary = dict(config=samples[0]['config'], condition=samples[0]['condition'], samples=len(samples), metrics={})
        for name in METRICS:
            measured = [run['metrics'][name] for run in samples if run['metrics'][name]['status'] == 'collected']
            units = {sample['unit'] for sample in measured}
            if len(measured) == len(samples) and len(units) == 1:
                values = [sample['value'] for sample in measured]
                summary['metrics'][name] = dict(status='collected', unit=measured[0]['unit'], min=min(values), median=statistics.median(values), max=max(values))
            else:
                summary['metrics'][name] = dict(status='not_run', value=None, collected_samples=len(measured), reason='complete comparable repetitions unavailable')
        summaries.append(summary)
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New evidence directory; never replaced')
    parser.add_argument('--ncu', type=Path, help='Native Nsight Compute executable or supported NVIDIA Windows wrapper')
    parser.add_argument('--config', type=configuration, action='append', help='Repeat READ,LAYOUT,BLOCK,CACHE for each desired configuration')
    parser.add_argument('--condition', choices=tuple(CONDITIONS), action='append', help='Defaults to both cold and warm')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--rows', type=int, default=128)
    parser.add_argument('--angles', type=int, default=1024)
    parser.add_argument('--epochs', type=int, default=1)
    parser.add_argument('--device', type=int, default=0)
    parser.add_argument('--mode', choices=('provided', 'recurrent', 'shift-xor', 'shift-or'), default='recurrent')
    parser.add_argument('--fringe', choices=('off', 'on'), default='off')
    parser.add_argument('--query-metrics', action='store_true', help='Also retain the complete exact-name metrics query for this device')
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 100 or not 1 <= args.epochs <= 16 or not 0 <= args.device <= 1024:
        parser.error('repetitions/epochs/device out of range')
    if not 1 <= args.rows <= 65536 or not 1 <= args.angles <= 65536:
        parser.error('dimensions must be 1..65536')
    words = (args.angles + 31) // 32
    if ((args.rows + 7) // 8 * 8) * ((words + 7) // 8 * 8) > 2**18 or args.rows * words * args.epochs > 2**20:
        parser.error('dimensions exceed the kernel atlas or lane-epoch cap')
    exe, out = args.exe.resolve(), args.out.resolve()
    if not exe.is_file():
        parser.error('kernel executable does not exist')
    if out.exists():
        parser.error('output directory must not already exist')
    out.mkdir(parents=True)
    configs = args.config or [configuration('texture,morton8,256,default')]
    conditions = list(dict.fromkeys(args.condition or CONDITIONS))
    ncu = resolve_ncu(args.ncu)
    report = dict(schema='atomOS-K1-targeted-cache-profile', created_at_utc=datetime.now(timezone.utc).isoformat(),
                  status='running', executable=str(exe), executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
                  profiler_executable=str(ncu) if ncu else None, requested_metrics=list(METRICS), configs=configs,
                  repetitions=args.repetitions, rows=args.rows, angles=args.angles, epochs=args.epochs, device=args.device,
                  mode=args.mode, fringe=args.fringe, commands=[], runs=[],
                  conditions={condition: dict(replay_mode=CONDITIONS[condition][0], cache_control=CONDITIONS[condition][1]) for condition in conditions},
                  launch_skip=1, launch_count=1, clock_control='none',
                  timing_scope='gpu__time_duration.sum is profiler GPU duration; application compute_ms in stdout is profiling-perturbed and excluded from benchmark summaries.',
                  evidence_scope='Cache counters describe the selected launch under the recorded replay conditions; they do not prove permanent or complete texture-cache residency. Application candidate verification remains enabled; no run directory is exported during application replay.')

    def save():
        report['aggregates'] = aggregate(report['runs'])
        (out / 'profile_summary.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')

    def invoke(command: list[str], label: str) -> dict:
        stdout, stderr = out / (label + '.stdout.log'), out / (label + '.stderr.log')
        record = dict(command=command, stdout=stdout.name, stderr=stderr.name)
        print('+', subprocess.list2cmdline(command), flush=True)
        start = time.perf_counter()
        try:
            with stdout.open('w', encoding='utf-8') as stream, stderr.open('w', encoding='utf-8') as errors:
                result = subprocess.run(command, cwd=out, stdout=stream, stderr=errors)
            record.update(exit_code=result.returncode, status='completed')
        except OSError as exc:
            record.update(exit_code=None, status='not_run', reason=str(exc))
        record['wall_seconds'] = time.perf_counter() - start
        report['commands'].append(record)
        save()
        return record

    if ncu is None:
        report.update(status='not_run', reason='Native Nsight Compute executable unavailable; supply --ncu with an installed native executable')
        save()
        print('NOT RUN:', report['reason'])
        return 3
    invoke([str(ncu), '--version'], 'profiler_version')
    if args.query_metrics:
        query = out / 'available_metrics.csv.log'
        record = invoke([str(ncu), '--query-metrics', '--query-metrics-mode', 'all', '--devices', str(args.device), '--csv', '--log-file', str(query)], 'available_metrics')
        raw = read_log(query)
        queried = record['exit_code'] == 0 and bool(raw)
        report['metric_availability_query'] = dict(status='queried' if queried else 'not_run', exit_code=record['exit_code'], log=query.name,
            exact_names_observed={name: name in raw if queried else None for name in METRICS},
            note='Query presence is discovery evidence only; collected values are determined from each profiling run.')
    for config_index, config in enumerate(configs):
        for condition in conditions:
            replay, cache_control = CONDITIONS[condition]
            for repetition in range(1, args.repetitions + 1):
                label = f'config{config_index:02d}_{condition}_{repetition:02d}'
                csv_path = out / (label + '.csv.log')
                command = [str(ncu), '--devices', str(args.device), '--metrics', ','.join(METRICS),
                           '--replay-mode', replay, '--cache-control', cache_control, '--clock-control', 'none',
                           '--launch-skip', '1', '--launch-count', '1', '--check-exit-code', '1',
                           '--csv', '--page', 'raw', '--print-units', 'base', '--log-file', str(csv_path),
                           str(exe), '--rows', str(args.rows), '--angles', str(args.angles), '--epochs', str(args.epochs),
                           '--read', config['read'], '--layout', config['layout'], '--block-size', str(config['block_size']),
                           '--cache', config['cache'], '--device', str(args.device), '--mode', args.mode, '--fringe', args.fringe]
                execution = invoke(command, label)
                raw = read_log(csv_path)
                metrics = parse_metrics(raw)
                metric_states = {metric['status'] for metric in metrics.values()}
                if execution['exit_code'] == 0 and metric_states == {'collected'}:
                    status = 'collected'
                elif execution['exit_code'] is not None and execution['exit_code'] != 0 and 'collected' in metric_states:
                    status = 'failed'
                else:
                    status = 'failed' if 'failed' in metric_states else 'not_run'
                if execution['exit_code'] != 0:
                    for metric in metrics.values():
                        if metric['status'] == 'collected':
                            metric.update(status='failed', reason='profiler/application returned a nonzero or unavailable exit code')
                report['runs'].append(dict(config=config, condition=condition, repetition=repetition, status=status,
                                           csv_log=csv_path.name, command_index=len(report['commands']) - 1, metrics=metrics,
                                           diagnostics=parse_metrics(raw, ('launch__shared_mem_config_size',))))
                save()
    states = {run['status'] for run in report['runs']}
    report['status'] = 'collected' if states == {'collected'} else 'failed' if 'failed' in states else 'not_run'
    save()
    print(f"{report['status'].upper()}: {out / 'profile_summary.json'}")
    return 0 if report['status'] == 'collected' else 1 if report['status'] == 'failed' else 3


if __name__ == '__main__':
    raise SystemExit(main())
