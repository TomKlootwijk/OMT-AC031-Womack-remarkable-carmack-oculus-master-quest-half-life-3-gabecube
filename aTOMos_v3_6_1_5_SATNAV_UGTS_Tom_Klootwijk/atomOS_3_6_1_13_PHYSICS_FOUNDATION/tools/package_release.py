#!/usr/bin/env python3
"""Package the focused physics document; inspect only artifact bytes, not algorithms."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'source/release_manifest.json'
ARCHIVE = ROOT / 'output/distribution/aTOMos_v3_6_1_13_Physics_Foundation_Tom_Klootwijk.zip'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_files():
    excluded = {'.build', 'LOCAL_APPDATA_FONTCONFIG_CACHE', '__pycache__', 'renders', 'distribution'}
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
                  and not excluded.intersection(p.relative_to(ROOT).parts)
                  and p != MANIFEST and p.suffix != '.pyc')


def main():
    binding = json.loads((ROOT / 'source/PARENT_BINDING.json').read_text(encoding='utf-8'))
    parent = ROOT.parent / binding['parent_directory']
    if digest(parent / binding['parent_pdf']) != binding['parent_pdf_sha256']:
        raise ValueError('Preserved parent PDF differs from its bound digest')
    parent_manifest = json.loads((parent / 'source/release_manifest.json').read_text(encoding='utf-8'))
    for record in parent_manifest['files']:
        path = parent / record['path']
        if path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            raise ValueError(f"Parent release file differs: {record['path']}")
    (ROOT / 'source/parent_preservation.json').write_text(json.dumps({
        'purpose': 'Parent artifact byte integrity only; no source programs executed',
        'parent_commit': binding['parent_commit'],
        'parent_pdf_sha256': binding['parent_pdf_sha256'],
        'parent_release_manifest_sha256': digest(parent / 'source/release_manifest.json'),
        'parent_files_matching_manifest': len(parent_manifest['files']),
        'parent_corpus_copied_into_supplement': False,
    }, indent=2) + '\n', encoding='utf-8')
    files = selected_files()
    records = [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                'sha256': digest(p)} for p in files]
    MANIFEST.write_text(json.dumps({
        'version': '3.6.1.13',
        'purpose': 'Distribution integrity; no formalized kernel is executed',
        'dependency': 'Preserved R12 corpus identified by source/PARENT_BINDING.json',
        'excludes': ['this manifest', 'distribution directory', 'temporary build and render files'],
        'files': records,
    }, indent=2) + '\n', encoding='utf-8')
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted([*files, MANIFEST]):
            record = zipfile.ZipInfo((Path(ROOT.name) / path.relative_to(ROOT)).as_posix(),
                                     date_time=(2026, 9, 15, 0, 0, 0))
            record.compress_type = zipfile.ZIP_DEFLATED
            record.external_attr = 0o100644 << 16
            output.writestr(record, path.read_bytes())
    with zipfile.ZipFile(ARCHIVE) as packaged:
        for path in [*files, MANIFEST]:
            if packaged.read((Path(ROOT.name) / path.relative_to(ROOT)).as_posix()) != path.read_bytes():
                raise ValueError(f'Archive differs from artifact: {path.name}')
    checksum = digest(ARCHIVE)
    ARCHIVE.with_suffix('.zip.sha256').write_text(checksum + '  ' + ARCHIVE.name + '\n', encoding='utf-8')
    print(json.dumps({'archive': str(ARCHIVE), 'bytes': ARCHIVE.stat().st_size,
                      'sha256': checksum, 'packaged_files': len(files) + 1,
                      'all_archive_bytes_match_workspace': True}, indent=2))


if __name__ == '__main__':
    main()
