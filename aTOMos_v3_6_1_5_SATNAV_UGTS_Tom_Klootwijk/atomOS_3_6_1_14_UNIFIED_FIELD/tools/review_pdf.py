#!/usr/bin/env python3
"""Render and inspect document structure; never execute the specified algorithms."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess

from PIL import Image, ImageDraw
from pypdf import PdfReader
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'output/pdf/aTOMos_v3_6_1_14_Unified_Field_Formalization_Tom_Klootwijk.pdf'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renderer', default='pdftoppm')
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    folder = ROOT / 'review/renders'
    folder.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(PDF)
    texts = [p.extract_text() or '' for p in reader.pages]
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
        'visual_review': 'Pending visual inspection of this exact PDF revision',
    }
    (folder / 'extracted_pages.json').write_text(json.dumps(texts, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'review/document_review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if args.render:
        subprocess.run([args.renderer, '-r', '100', '-png', str(PDF), str(folder / 'page')], check=True)
        pages = sorted(folder.glob('page-*.png'))[:len(texts)]
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
