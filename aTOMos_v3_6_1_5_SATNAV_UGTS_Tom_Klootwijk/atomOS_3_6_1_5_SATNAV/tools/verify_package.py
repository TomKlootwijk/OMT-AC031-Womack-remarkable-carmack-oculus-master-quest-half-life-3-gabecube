#!/usr/bin/env python3
from pathlib import Path
import hashlib
root=Path(__file__).resolve().parents[1];count=0
try:
    for line in (root/'SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ',1);p=(root/name).resolve()
        if not p.is_relative_to(root)or not p.is_file():raise ValueError('invalid/missing path '+name)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('changed bytes '+name)
        count+=1
except (OSError,ValueError)as exc:print('DIFFERENCE:',exc);raise SystemExit(1)
print('MATCH:',count,'delivered file hashes')
