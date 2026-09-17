"""Package the radio extension, with byte hashes and explicit evidence scope."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'source/release_manifest.json'
ZIP = ROOT / 'output/aTOMos_3_6_1_20_Radio_Packet_Studio.zip'
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
    formal = ROOT / 'formal/RADIO_PACKET_PROFILE.md'
    if not qa['complete'] or qa['sha256'] != digest(pdf.read_bytes()):
        raise ValueError('PDF bytes have no matching complete visual review')
    if qa['source_sha256'] != digest(formal.read_bytes()):
        raise ValueError('PDF formal source changed since review')
    if not qa['all_inherited_pages_pixel_equal'] or qa['inherited_pixel_equal_count'] != 110:
        raise ValueError('Retained R19 page verification is incomplete')


def check_validation():
    version = json.loads((ROOT / 'VERSION.json').read_text(encoding='utf-8'))
    android = json.loads((ROOT / 'review/android/validation.json').read_text(encoding='utf-8'))
    host = json.loads((ROOT / 'review/host_validation.json').read_text(encoding='utf-8'))
    decoder = json.loads((ROOT / 'review/decoder_validation.json').read_text(encoding='utf-8'))
    apk_sha = digest((ROOT / version['android']['apk']).read_bytes())
    if version['status'] != 'validated_development_release':
        raise ValueError('Release is not marked validated')
    if apk_sha != version['android']['sha256'] or apk_sha != android['apk_sha256']:
        raise ValueError('APK bytes differ from validated build')
    if android['instrumentation_passed'] != version['android']['instrumentation_tests_passed']:
        raise ValueError('Android test counts disagree')
    if android['lint_errors'] != 0 or host['status'] != 'passed' or not decoder['complete']:
        raise ValueError('Required validation has not passed')
    for pin in host['source_pins']:
        if digest((ROOT / pin['path']).read_bytes()) != pin['sha256']:
            raise ValueError('Host source changed since validation: ' + pin['path'])
    for path, expected in decoder['source_sha256'].items():
        if digest((ROOT / path).read_bytes()) != expected:
            raise ValueError('Decoder source changed since validation: ' + path)
    if digest((ROOT / 'examples/packets/fixture_manifest.json').read_bytes()) != decoder['fixture_manifest_sha256']:
        raise ValueError('Packet fixtures changed since decoder validation')


def verify():
    check_pdf()
    check_validation()
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
        check_validation()
        if not (ROOT / 'output/android/aTOMos-Radio-3.6.1.20-debug.apk').exists():
            raise ValueError('Installable APK missing')
        version = json.loads((ROOT / 'VERSION.json').read_text(encoding='utf-8'))
        paths = list(selected())
        manifest = {'version': version['version'], 'profile': version['profile'],
                    'parent_commit': 'fc4027c574082711b78c1ef1d43d6c50adcf8c96',
                    'scope': 'R20 phone acquisition and study extension; unchanged R19 manuscript included. No physical POCO capture bundled.',
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
