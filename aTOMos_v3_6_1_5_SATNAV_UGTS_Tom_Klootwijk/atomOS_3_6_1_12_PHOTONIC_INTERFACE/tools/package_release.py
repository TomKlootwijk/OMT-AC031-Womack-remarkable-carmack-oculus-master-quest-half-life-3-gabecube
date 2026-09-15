#!/usr/bin/env python3
"""Package the formal document and source provenance; no kernel code is executed."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent / 'atomOS_3_6_1_11_EXACT_OPERATORS'
MANIFEST = ROOT / 'source/release_manifest.json'
ARCHIVE = ROOT / 'output/distribution/aTOMos_v3_6_1_12_Photonic_Interface_Formalization_Tom_Klootwijk.zip'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_files():
    excluded_parts = {'.build', 'LOCAL_APPDATA_FONTCONFIG_CACHE', '__pycache__', 'renders', 'distribution'}
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
                  and not excluded_parts.intersection(p.relative_to(ROOT).parts)
                  and p != MANIFEST and p.suffix != '.pyc')


def main():
    binding = json.loads((ROOT / 'source/SOURCE_BINDING.json').read_text(encoding='utf-8'))
    supplied = ROOT / 'source' / binding['source_pdf']
    if digest(supplied) != binding['source_sha256']:
        raise ValueError('Supplied PDF digest differs from the source binding')
    attachments = json.loads((ROOT / 'source/embedded/extraction_manifest.json').read_text(encoding='utf-8'))
    for record in attachments:
        path = ROOT / 'source/embedded' / record['name']
        if path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            raise ValueError(f"Preserved attachment differs: {record['name']}")
    inherited = []
    for local in sorted((ROOT / 'docs').glob('*.tex')):
        parent = PARENT / 'docs' / local.name
        if local.name in {'satnav.tex', 'preamble.tex'} or not parent.exists():
            continue
        original, copied = digest(parent), digest(local)
        if original != copied:
            raise ValueError(f'Inherited document bytes differ: {local.name}')
        inherited.append({'path': f'docs/{local.name}', 'sha256': copied})
    other_inherited = []
    for folder in ('formal', 'results', 'docs/figures'):
        for parent in sorted((PARENT / folder).rglob('*')):
            if not parent.is_file():
                continue
            rel = parent.relative_to(PARENT)
            local = ROOT / rel
            if not local.exists():
                continue
            if digest(parent) != digest(local):
                raise ValueError(f'Inherited source differs: {rel}')
            other_inherited.append({'path': rel.as_posix(), 'sha256': digest(local)})
    for local in sorted((ROOT / 'formal/inherited_r11').glob('*.md')):
        if digest(local) != digest(PARENT / 'formal' / local.name):
            raise ValueError(f'Grouped inherited Markdown differs: {local.name}')
    (ROOT / 'source/parent_preservation.json').write_text(json.dumps({
        'purpose': 'Document source provenance, not algorithm verification',
        'parent_commit': 'f5c2c9e4ab10d7c2aae08e2128eaf82b1d786d13',
        'inherited_tex_files_byte_identical': inherited,
        'other_inherited_files_byte_identical': other_inherited,
        'original_pdf_and_ten_embedded_attachments_match_source_binding': True,
        'grouped_r11_markdown_matches_parent': True,
        'intentional_new_master_and_preamble': ['docs/satnav.tex', 'docs/preamble.tex'],
    }, indent=2) + '\n', encoding='utf-8')
    files = selected_files()
    records = [{'path': str(p.relative_to(ROOT)).replace('\\', '/'),
                'bytes': p.stat().st_size, 'sha256': digest(p)} for p in files]
    MANIFEST.write_text(json.dumps({
        'version': '3.6.1.12',
        'purpose': 'Distribution file integrity; no proposed arithmetic is executed',
        'excludes': ['this manifest', 'distribution archive', 'temporary document build and render files'],
        'files': records,
    }, indent=2) + '\n', encoding='utf-8')
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted([*files, MANIFEST]):
            arcname = str(Path(ROOT.name) / path.relative_to(ROOT)).replace('\\', '/')
            record = zipfile.ZipInfo(arcname, date_time=(2026, 9, 15, 0, 0, 0))
            record.compress_type = zipfile.ZIP_DEFLATED
            record.external_attr = 0o100644 << 16
            output.writestr(record, path.read_bytes())
    print(json.dumps({'archive': str(ARCHIVE), 'bytes': ARCHIVE.stat().st_size,
                      'sha256': digest(ARCHIVE), 'packaged_files': len(files) + 1}, indent=2))


if __name__ == '__main__':
    main()
