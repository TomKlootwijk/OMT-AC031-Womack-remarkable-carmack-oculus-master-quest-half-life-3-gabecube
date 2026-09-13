#!/usr/bin/env python3
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]
count=0;failed=[]
for line in (ROOT/'SHA256SUMS.txt').read_text().splitlines():
    digest,name=line.split('  ',1)
    p=(ROOT/name).resolve()
    if not p.is_relative_to(ROOT) or not p.is_file():failed.append(name);continue
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    count+=1
    if h.hexdigest()!=digest:failed.append(name)
print(f'PASS: {count} files match the package manifest' if not failed else 'FAIL: '+', '.join(failed))
raise SystemExit(bool(failed))
