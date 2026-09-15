#!/usr/bin/env python3
"""Regenerate the delivered-byte manifest and create a verified subversion ZIP."""
from pathlib import Path
import argparse, hashlib, os, zipfile

ROOT = Path(__file__).resolve().parents[1]

def delivered_files():
    for directory, names, files in os.walk(ROOT):
        relative = Path(directory).relative_to(ROOT)
        pdf_review = len(relative.parts) >= 2 and relative.parts[0] == 'results' and relative.parts[1] in {'orbit_pdf_qa', 'orbit_pdf_r2_qa'}
        names[:] = sorted(name for name in names if not (
            name.startswith('build') or name in {'.build', '__pycache__', '.git', 'tmp'} or
            (pdf_review and name in {'low', 'full'})))
        for name in sorted(files):
            path = Path(directory)/name
            if path == ROOT/'SHA256SUMS.txt' or path.suffix.lower() in {'.pyc','.zip'}:
                continue
            yield path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True,help='New ZIP path')
    args=parser.parse_args()
    if args.out.exists():parser.error('Output archive exists; choose a new path')
    files=sorted(delivered_files())
    manifest=ROOT/'SHA256SUMS.txt'
    lines=[hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(ROOT).as_posix() for path in files]
    manifest.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in [*files,manifest]:
            archive.write(path,ROOT.name+'/'+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(args.out) as archive:
        if archive.testzip() is not None:raise RuntimeError('Archive CRC verification failed')
        for line in lines:
            expected,name=line.split('  ',1)
            actual=hashlib.sha256(archive.read(ROOT.name+'/'+name)).hexdigest()
            if actual!=expected:raise RuntimeError('Archive hash mismatch: '+name)
    print(f'Verified {len(files)} delivered file hashes and {len(files)+1} ZIP members')
    print(args.out.resolve())

if __name__=='__main__':main()
