#!/usr/bin/env python3
"""Verify file SHA-256s relative to this extracted package."""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
manifest=root/"SHA256SUMS.txt"
count=0
for line in manifest.read_text().splitlines():
    digest,rel=line.split("  ",1)
    path=(root/rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise SystemExit(f"Missing or unsafe manifest path: {rel}")
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise SystemExit(f"Checksum mismatch: {rel}")
    count+=1
print(f"Verified {count} packaged files. Checksums are not author signatures.")
