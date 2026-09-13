#!/usr/bin/env python3
"""Check the delivered unsigned file manifest, without trusting paths outside root."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]
try:
    count=0
    for line in (ROOT/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        expected,name=line.split('  ',1);p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or len(expected)!=64:raise ValueError('invalid path: '+name)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('changed file: '+name)
        count+=1
    print(f'PASS: {count} package file hashes match')
except (OSError,ValueError) as exc:
    print('FAIL:',exc);raise SystemExit(1)
