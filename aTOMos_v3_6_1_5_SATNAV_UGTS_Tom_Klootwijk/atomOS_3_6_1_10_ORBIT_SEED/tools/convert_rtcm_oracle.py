"""Convert recorded RTCM with the unmodified independent RTKLIB executable.

Only optional GPSA/B header lines are copied from --iono-nav. Orbital records
are always decoded from RTCM1019, so the source of live ephemerides is testable.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rtcm', type=Path, required=True)
    p.add_argument('--reference-gpst', required=True, help='Approximate GPS time: YYYY/MM/DD HH:MM:SS')
    p.add_argument('--iono-nav', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--binary', type=Path, default=root / 'source/live_data/rtklib/convbin.exe')
    p.add_argument('--work-parent', type=Path, default=Path('C:/tmp') if __import__('os').name == 'nt' else Path('/tmp'))
    args = p.parse_args()
    ref = datetime.strptime(args.reference_gpst, '%Y/%m/%d %H:%M:%S')
    args.out.mkdir(parents=True, exist_ok=False)
    args.work_parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='atomos_convbin_', dir=args.work_parent))
    shutil.copyfile(args.binary, scratch / 'convbin.exe')
    shutil.copyfile(args.rtcm, scratch / 'receiver.rtcm3')
    command = [str(scratch / 'convbin.exe'), '-r', 'rtcm3', '-tr', ref.strftime('%Y/%m/%d'),
               ref.strftime('%H:%M:%S'), '-v', '3.03', '-f', '1']
    for system in ['R', 'E', 'J', 'S', 'C']:
        command.extend(['-y', system])
    # All names must be explicit in the official old binary: omitted names can
    # read uninitialized memory and cause unrelated output-open failures.
    for switch, name in [('-o', 'receiver.obs'), ('-n', 'receiver.nav'), ('-g', 'receiver.gnav'),
                         ('-h', 'receiver.hnav'), ('-q', 'receiver.qnav'), ('-l', 'receiver.lnav'),
                         ('-s', 'receiver.sbs')]:
        command.extend([switch, name])
    command.extend(['-trace', '2', 'receiver.rtcm3'])
    result = subprocess.run(command, cwd=scratch, capture_output=True, timeout=180)
    for name in ['receiver.obs', 'receiver.nav', 'convbin.trace']:
        if (scratch / name).exists():
            shutil.copyfile(scratch / name, args.out / name)
    (args.out / 'stdout.txt').write_bytes(result.stdout)
    (args.out / 'stderr.txt').write_bytes(result.stderr)
    ionolines = []
    if args.iono_nav is not None:
        raw = args.iono_nav.read_bytes()
        if args.iono_nav.suffix == '.gz':
            raw = gzip.decompress(raw)
        ionolines = [line for line in raw.decode('ascii').splitlines()
                     if line.startswith(('GPSA', 'GPSB')) and 'IONOSPHERIC CORR' in line]
        if len(ionolines) != 2 or {line[:4] for line in ionolines} != {'GPSA', 'GPSB'}:
            raise ValueError('iono source must provide exactly one GPSA and one GPSB header line')
        nav = (args.out / 'receiver.nav').read_text().splitlines()
        end = next(i for i, line in enumerate(nav) if 'END OF HEADER' in line)
        nav[end:end] = ionolines
        (args.out / 'receiver_with_iono.nav').write_text('\n'.join(nav) + '\n')
    observations = (args.out / 'receiver.obs').read_text().splitlines() if (args.out / 'receiver.obs').exists() else []
    ephemerides = (args.out / 'receiver.nav').read_text().splitlines() if (args.out / 'receiver.nav').exists() else []
    obs_count = sum(line.startswith('>') for line in observations)
    nav_count = sum(line.startswith('G') for line in ephemerides)
    inputs = {'rtcm': args.rtcm, 'convbin': args.binary}
    if args.iono_nav is not None:
        inputs['iono_only_source'] = args.iono_nav
    summary = {'kind': 'independent_rtklib_rtcm_to_rinex', 'executed_utc': datetime.now(timezone.utc).isoformat(),
               'command': command, 'working_directory': str(scratch), 'return_code': result.returncode,
               'reference_gpst': args.reference_gpst, 'epochs': obs_count, 'gps_ephemerides': nav_count,
               'iono_header_only_inserted_lines': ionolines,
               'inputs': {key: {'path': str(path.resolve()), 'sha256': sha(path)} for key, path in inputs.items()},
               'output_hashes': {f.name: sha(f) for f in args.out.iterdir() if f.is_file()},
               'status': 'converted' if result.returncode == 0 and obs_count and nav_count else 'failed'}
    (args.out / 'conversion.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if summary['status'] == 'converted' else 1


if __name__ == '__main__':
    raise SystemExit(main())
