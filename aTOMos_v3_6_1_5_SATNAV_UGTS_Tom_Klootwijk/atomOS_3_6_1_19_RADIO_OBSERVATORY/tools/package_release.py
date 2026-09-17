"""Package the radio extension, with byte hashes and explicit evidence scope."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'source/release_manifest.json'
ZIP = ROOT / 'output/aTOMos_3_6_1_19_Radio_Observatory.zip'
EXCLUDED = {'build', '.gradle', '__pycache__', 'tmp', 'private', 'sessions'}
TOP_DIRS = {'android', 'examples', 'formal', 'output', 'python', 'review', 'schema', 'source', 'tests', 'tools'}
TOP_FILES = {'.gitattributes', '.gitignore', 'AGENTS.md', 'README.md', 'VERSION.json',
             'requirements-study.txt', 'requirements-document.txt'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def selected():
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if (not path.is_file() or path in (MANIFEST, ZIP)
            or EXCLUDED.intersection(rel.parts) or path.name == 'local.properties'
            or path.suffix in {'.pyc', '.keystore', '.jks', '.zip'}):
            continue
        if len(rel.parts) == 1 and path.name not in TOP_FILES:
            continue
        if len(rel.parts) > 1 and rel.parts[0] not in TOP_DIRS:
            continue
        if rel.parts[0] == 'output' and (len(rel.parts) < 3 or rel.parts[1] not in {'pdf', 'android'}):
            continue
        yield path


def check_pdf():
    qa = json.loads((ROOT / 'review/pdf_visual_review.json').read_text(encoding='utf-8'))
    pdf = ROOT / qa['pdf']
    # Reports were written on Windows; accept portable slash normalization.
    if not pdf.exists():
        pdf = ROOT / qa['pdf'].replace('\\', '/')
    formal = ROOT / 'formal/RADIO_OBSERVATION_PROFILE.md'
    if not qa['complete'] or qa['sha256'] != digest(pdf.read_bytes()):
        raise ValueError('PDF bytes have no matching complete visual review')
    if qa['source_sha256'] != digest(formal.read_bytes()):
        raise ValueError('PDF formal source changed since review')
    if not qa['all_inherited_pages_pixel_equal'] or qa['inherited_pixel_equal_count'] != 103:
        raise ValueError('Retained R18 page verification is incomplete')


def verify():
    check_pdf()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    actual_paths = {p.relative_to(ROOT).as_posix() for p in selected()}
    expected_paths = {r['path'] for r in manifest['files']}
    if actual_paths != expected_paths:
        raise ValueError('File inventory changed since packaging')
    with zipfile.ZipFile(ZIP) as archive:
        names = set(archive.namelist())
        expected_names = {ROOT.name + '/' + p for p in expected_paths | {'source/release_manifest.json'}}
        if names != expected_names:
            raise ValueError('ZIP inventory mismatch')
        for record in manifest['files']:
            path = ROOT / record['path']
            data = path.read_bytes()
            if len(data) != record['bytes'] or digest(data) != record['sha256']:
                raise ValueError('File hash mismatch: ' + record['path'])
            if archive.read(ROOT.name + '/' + record['path']) != data:
                raise ValueError('ZIP bytes differ: ' + record['path'])
        if archive.read(ROOT.name + '/source/release_manifest.json') != MANIFEST.read_bytes():
            raise ValueError('ZIP manifest mismatch')
    return {'verified_files': len(manifest['files']), 'zip_bytes': ZIP.stat().st_size,
            'zip_sha256': digest(ZIP.read_bytes()), 'pdf_review_complete': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if not args.verify:
        check_pdf()
        if not (ROOT / 'output/android/aTOMos-Radio-3.6.1.19-debug.apk').exists():
            raise ValueError('Installable APK missing')
        version = json.loads((ROOT / 'VERSION.json').read_text(encoding='utf-8'))
        paths = list(selected())
        manifest = {'version': version['version'], 'profile': version['profile'],
                    'parent_commit': '4bfccc9df3b083122199cf9ea5182d546bfd7bb3',
                    'scope': 'R19 phone acquisition and study extension; unchanged R18 manuscript included. No physical POCO capture bundled.',
                    'files': [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                               'sha256': digest(p.read_bytes())} for p in paths]}
        MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        ZIP.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in paths + [MANIFEST]:
                archive.write(path, ROOT.name + '/' + path.relative_to(ROOT).as_posix())
    print(json.dumps(verify(), indent=2))


if __name__ == '__main__':
    main()
