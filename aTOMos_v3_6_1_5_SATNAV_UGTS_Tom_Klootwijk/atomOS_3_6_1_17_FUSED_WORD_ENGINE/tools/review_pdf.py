#!/usr/bin/env python3
"""Render the R17 PDF and check retained/new chapter structure; no kernel runs."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import unicodedata

from PIL import Image, ImageDraw
from pypdf import PdfReader
import pdfplumber
from prepare_document import NAME, digest, document_records, required_headings

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'output/pdf' / (NAME + '.pdf')


def searchable(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    return re.sub(r'[^a-z0-9]', '', text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renderer', default='pdftoppm')
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    inputs = document_records()
    build_binding = json.loads((ROOT / 'docs/.build/source_inputs.json').read_text(encoding='utf-8'))
    if build_binding['pdf_sha256'] != digest(PDF) or build_binding['tex_inputs'] != inputs:
        raise ValueError('The PDF build does not match the current authored TeX inputs')
    folder = ROOT / 'review/renders'
    folder.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(PDF)
    texts = [p.extract_text() or '' for p in reader.pages]
    searchable_pages = [searchable(text) for text in texts]
    heading_checks = []
    for item in required_headings():
        needle = searchable(item['heading'])
        pages = [i for i, text in enumerate(searchable_pages, 1) if needle in text]
        heading_checks.append({**item, 'pages': pages, 'present': bool(pages)})
    log = (ROOT / 'docs/.build/unified.log').read_text(encoding='utf-8', errors='replace')
    warnings = [line for line in log.splitlines()
                if re.search(r'Overfull|Underfull|Missing character|undefined', line)]
    outside = []
    with pdfplumber.open(PDF) as document:
        for number, page in enumerate(document.pages, 1):
            for char in page.chars:
                if char['text'].strip() and (char['x0'] < -0.1 or char['x1'] > page.width + .1
                                             or char['top'] < -.1 or char['bottom'] > page.height + .1):
                    outside.append({'page': number, 'text': char['text']})
    report = {
        'purpose': 'Document rendering and structural inspection, not algorithm validation',
        'pdf': str(PDF.relative_to(ROOT)).replace('\\', '/'),
        'sha256': hashlib.sha256(PDF.read_bytes()).hexdigest(),
        'pages': len(texts),
        'extractable_text_all_pages': all(texts),
        'tex_layout_glyph_reference_warnings': warnings,
        'page_boundary_violations': outside,
        'tex_inputs': inputs,
        'required_section_headings': heading_checks,
        'required_headings_present': all(item['present'] for item in heading_checks),
        'visual_review': 'Pending visual inspection of this exact PDF revision',
    }
    (folder / 'extracted_pages.json').write_text(json.dumps(texts, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'review/document_review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if args.render:
        subprocess.run([args.renderer, '-r', '100', '-png', str(PDF), str(folder / 'page')], check=True)
        digits = len(str(len(texts)))
        pages = [folder / f'page-{i:0{digits}d}.png' for i in range(1, len(texts) + 1)]
        if not all(path.is_file() for path in pages):
            raise ValueError('Renderer did not produce every expected page image')
        for start in range(0, len(pages), 6):
            sheet = Image.new('RGB', (1600, 2260), '#e1e5e9')
            draw = ImageDraw.Draw(sheet)
            for offset, path in enumerate(pages[start:start + 6]):
                with Image.open(path) as raw:
                    page = raw.convert('RGB')
                page.thumbnail((760, 706))
                column, row = offset % 2, offset // 2
                x = 800 * column + (800 - page.width) // 2
                y = 750 * row + 32
                sheet.paste(page, (x, y))
                draw.text((800 * column + 18, 750 * row + 12), path.stem, fill='black')
            sheet.save(folder / f'contact-{start // 6 + 1:02d}.png')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
