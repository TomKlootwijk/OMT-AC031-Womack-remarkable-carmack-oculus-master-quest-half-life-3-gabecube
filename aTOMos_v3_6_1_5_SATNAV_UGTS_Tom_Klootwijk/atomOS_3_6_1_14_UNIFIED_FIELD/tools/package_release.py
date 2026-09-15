#!/usr/bin/env python3
"""Publish the reviewed PDF and package source artifacts; no kernel is executed."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'aTOMos_v3_6_1_14_Unified_Field_Formalization_Tom_Klootwijk'
PDF = ROOT / 'output/pdf' / (NAME + '.pdf')
MANIFEST = ROOT / 'source/release_manifest.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    review = json.loads((ROOT / 'review/document_review.json').read_text(encoding='utf-8'))
    if review['sha256'] != digest(PDF) or review['visual_review']['status'] != 'complete':
        raise ValueError('Final PDF does not have completed review for its current bytes')
    binding = json.loads((ROOT / 'source/SOURCE_BINDING.json').read_text(encoding='utf-8'))
    for item in binding['inspected_or_adapted_sources']:
        source = ROOT.parent / item['path']
        if source.stat().st_size != item['bytes'] or digest(source) != item['sha256']:
            raise ValueError('An inherited source differs: ' + item['path'])
    for parent in binding['parents']:
        for item in parent['pdfs']:
            source = ROOT.parent / parent['directory'] / item['path']
            if source.stat().st_size != item['bytes'] or digest(source) != item['sha256']:
                raise ValueError('A preserved parent PDF differs: ' + str(source))

    repo = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'],
                                       cwd=ROOT, text=True).strip()).resolve()
    if repo != ROOT.parents[1].resolve():
        raise ValueError('Unexpected main repository location')
    main_pdf = repo / PDF.name
    shutil.copy2(PDF, main_pdf)
    if main_pdf.read_bytes() != PDF.read_bytes():
        raise ValueError('Main-repository PDF differs from reviewed release')
    (ROOT / 'source/MAIN_REPOSITORY_PDF.json').write_text(json.dumps({
        'repository_relative_path': main_pdf.name,
        'sha256': digest(main_pdf),
        'bytes': main_pdf.stat().st_size,
        'identical_to_reviewed_release_pdf': True,
        'preserved_parent_pdfs': len(binding['parents']),
        'preserved_source_files': len(binding['inspected_or_adapted_sources']),
    }, indent=2) + '\n', encoding='utf-8')

    excluded = {'.build', 'LOCAL_APPDATA_FONTCONFIG_CACHE', '__pycache__', 'renders', 'distribution'}
    files = sorted(p for p in ROOT.rglob('*') if p.is_file() and p != MANIFEST
                   and not excluded.intersection(p.relative_to(ROOT).parts)
                   and p.suffix != '.pyc')
    MANIFEST.write_text(json.dumps({
        'version': '3.6.1.14',
        'purpose': 'Document/source distribution integrity; no proposed kernel execution',
        'excludes': ['this manifest', 'distribution directory', 'temporary build and render files'],
        'files': [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                   'sha256': digest(p)} for p in files],
    }, indent=2) + '\n', encoding='utf-8')
    archive = ROOT / 'output/distribution' / (NAME + '.zip')
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted([*files, MANIFEST]):
            name = (Path(ROOT.name) / path.relative_to(ROOT)).as_posix()
            entry = zipfile.ZipInfo(name, date_time=(2026, 9, 15, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            output.writestr(entry, path.read_bytes())
    with zipfile.ZipFile(archive) as packed:
        for path in [*files, MANIFEST]:
            if packed.read((Path(ROOT.name) / path.relative_to(ROOT)).as_posix()) != path.read_bytes():
                raise ValueError('Packaged artifact differs: ' + path.name)
    archive.with_suffix('.zip.sha256').write_text(digest(archive) + '  ' + archive.name + '\n',
                                                 encoding='utf-8')
    print(json.dumps({'main_repository_pdf': str(main_pdf), 'pdf_sha256': digest(PDF),
                      'archive': str(archive), 'archive_sha256': digest(archive),
                      'packaged_files': len(files) + 1,
                      'all_archive_bytes_match_workspace': True}, indent=2))


if __name__ == '__main__':
    main()
