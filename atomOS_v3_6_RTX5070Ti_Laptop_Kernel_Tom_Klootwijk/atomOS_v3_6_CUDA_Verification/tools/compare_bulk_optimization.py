"""Serial, shuffled comparisons of retained bulk-kernel binaries.

All event samples include warm/work/reread. Each executable verifies its own
results before commit; the existing receipt audit checks workload and coverage.
This is a timing comparison, not an independent numerical or residency proof.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics
import subprocess
import time
import study_cache_bulk as bulk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', action='append', required=True, help='label=executable')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--trials', type=int, default=5)
    args = parser.parse_args()
    if args.out.exists() or not 1 <= args.trials <= 20:
        parser.error('new output directory and 1..20 trials required')
    binaries = {}
    for entry in args.exe:
        label, path = entry.split('=', 1)
        if not label.replace('_', '').isalnum() or label in binaries:
            parser.error('unique simple executable labels required')
        exe = Path(path).resolve()
        if not exe.is_file():
            parser.error(f'missing executable: {exe}')
        binaries[label] = dict(path=str(exe), sha256=bulk.digest(exe))
    out = args.out.resolve()
    out.mkdir(parents=True)
    report = dict(status='running', created_at_utc=datetime.now(timezone.utc).isoformat(),
                  binaries=binaries, trials=args.trials, samples=[],
                  scope='Serial shuffled trials; median of three verified epoch event times per trial; includes all warm/work/reread overhead; excludes host transfers and verification. No clock or power changes.')

    def save():
        (out/'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')

    save()
    try:
        for trial in range(args.trials):
            cases = [(label, size, layout) for label in binaries for size in ('default', 'max') for layout in bulk.LAYOUTS]
            random.Random(130003 + trial).shuffle(cases)
            for label, size, layout in cases:
                context = bulk.context(*bulk.SIZES[size], layout)
                task = dict(kind='timing', context=context)
                command = bulk.command_for(task, Path(binaries[label]['path']), None, out)
                stem = f'{trial}_{label}_{size}_{layout}'
                started = time.perf_counter()
                process = subprocess.run(command, cwd=bulk.ROOT, capture_output=True, text=True, timeout=180)
                (out/(stem+'.stdout.log')).write_text(process.stdout, encoding='utf-8')
                (out/(stem+'.stderr.log')).write_text(process.stderr, encoding='utf-8')
                if process.returncode:
                    raise ValueError(f'{stem} failed: {process.stderr}')
                receipts = bulk.application_results(process.stdout, context, False)
                if len(receipts) != 1:
                    raise ValueError('expected one ordinary execution receipt')
                receipt = receipts[0]
                sample = dict(trial=trial, binary=label, size=size, layout=layout,
                              command=command, exit_code=process.returncode,
                              wall_seconds=time.perf_counter()-started,
                              stdout=stem+'.stdout.log', stderr=stem+'.stderr.log',
                              receipt=receipt, median_ms=statistics.median(receipt['compute_ms']))
                report['samples'].append(sample)
                save()
                print(f'{stem}: {sample["median_ms"]*1000:.3f} us', flush=True)
        report['aggregates'] = []
        for label in binaries:
            if bulk.digest(Path(binaries[label]['path'])) != binaries[label]['sha256']:
                raise ValueError('executable changed during comparison')
            for size in ('default', 'max'):
                for layout in bulk.LAYOUTS:
                    values = [s['median_ms'] for s in report['samples'] if (s['binary'],s['size'],s['layout']) == (label,size,layout)]
                    if len(values) != args.trials:
                        raise ValueError('incomplete comparison')
                    report['aggregates'].append(dict(binary=label,size=size,layout=layout,
                        trials=len(values),median_ms=statistics.median(values),min_ms=min(values),max_ms=max(values)))
        report['status'] = 'passed'
        save()
        return 0
    except Exception as exc:
        report.update(status='failed', reason=str(exc))
        save()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
