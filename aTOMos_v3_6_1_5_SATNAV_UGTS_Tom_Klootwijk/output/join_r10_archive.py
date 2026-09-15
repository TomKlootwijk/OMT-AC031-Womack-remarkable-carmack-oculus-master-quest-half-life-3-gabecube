#!/usr/bin/env python3
"""Reassemble the exact R10 audit ZIP from its three regular-Git parts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'aTOMos_v3_6_1_10_Archive_Parts.json').read_text(encoding='utf-8'))
    target = args.out or ROOT / manifest['archive_name']
    parts = []
    for part in manifest['parts']:
        path = ROOT / part['name']
        if path.parent.resolve() != ROOT or path.stat().st_size != part['bytes'] or digest(path) != part['sha256']:
            raise ValueError('Missing or changed archive part: ' + part['name'])
        parts.append(path)
    if not target.exists():
        with target.open('xb') as output:
            for path in parts:
                with path.open('rb') as source:
                    shutil.copyfileobj(source, output)
    if target.stat().st_size != manifest['archive_bytes'] or digest(target) != manifest['archive_sha256']:
        raise ValueError('Reassembled ZIP checksum mismatch')
    print('MATCH:', manifest['archive_sha256'], target.resolve())


if __name__ == '__main__':
    main()
