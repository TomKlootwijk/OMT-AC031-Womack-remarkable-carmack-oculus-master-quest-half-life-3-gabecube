"""Run the independently published RTKLIB oracle using short temporary paths.

Old official Windows RTKLIB binaries silently miss observations under very long
directory paths. A fresh short working directory avoids that issue, and all
inputs, commands, binary hashes, outputs and return codes remain inspectable.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--obs', type=Path, required=True)
    p.add_argument('--nav', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--config', type=Path, default=root / 'source/live_data/rtklib/gps_single.conf')
    p.add_argument('--binary', type=Path, default=root / 'source/live_data/rtklib/rnx2rtkp.exe')
    p.add_argument('--work-parent', type=Path, default=Path('C:/tmp') if __import__('os').name == 'nt' else Path('/tmp'))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    args.work_parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='atomos_oracle_', dir=args.work_parent))
    inputs = {'receiver.obs': args.obs, 'broadcast.nav': args.nav,
              'gps_single.conf': args.config, 'rnx2rtkp.exe': args.binary}
    for name, path in inputs.items():
        shutil.copyfile(path, scratch / name)
    command = [str(scratch / 'rnx2rtkp.exe'), '-k', 'gps_single.conf', '-o', 'solution.pos',
               '-y', '2', 'receiver.obs', 'broadcast.nav']
    result = subprocess.run(command, cwd=scratch, capture_output=True, timeout=180)
    for name in ['solution.pos', 'solution.pos.stat']:
        if (scratch / name).exists():
            shutil.copyfile(scratch / name, args.out / name)
    (args.out / 'stdout.txt').write_bytes(result.stdout)
    (args.out / 'stderr.txt').write_bytes(result.stderr)
    lines = (args.out / 'solution.pos').read_text().splitlines() if (args.out / 'solution.pos').exists() else []
    rows = [line.split() for line in lines if line and not line.startswith('%')]
    summary = {'kind': 'independent_rtklib_single_point_oracle', 'executed_utc': datetime.now(timezone.utc).isoformat(),
               'command': command, 'working_directory': str(scratch), 'return_code': result.returncode,
               'inputs': {name: {'source_path': str(path.resolve()), 'sha256': sha(path)} for name, path in inputs.items()},
               'epochs': len(rows), 'first_epoch': ' '.join(rows[0][:2]) if rows else None,
               'last_epoch': ' '.join(rows[-1][:2]) if rows else None,
               'quality_codes': sorted(set(row[5] for row in rows)),
               'output_hashes': {f.name: sha(f) for f in args.out.iterdir() if f.is_file()},
               'status': 'executed' if result.returncode == 0 and rows else 'failed'}
    (args.out / 'oracle.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if summary['status'] == 'executed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
