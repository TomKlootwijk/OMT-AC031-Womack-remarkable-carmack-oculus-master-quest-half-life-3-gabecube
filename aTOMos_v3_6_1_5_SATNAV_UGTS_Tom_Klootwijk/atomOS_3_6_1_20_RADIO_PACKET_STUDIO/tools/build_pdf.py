"""Build the editable R20 supplement and retain the exact reviewed R19 pages."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Preformatted, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent / 'atomOS_3_6_1_19_RADIO_OBSERVATORY'
PARENT_PDF = PARENT / 'output/pdf/aTOMos_v3_6_1_19_Radio_Observatory_Tom_Klootwijk.pdf'
if not PARENT_PDF.exists():
    PARENT_PDF = ROOT / 'source/parent_R19.pdf'
PARENT_SHA256 = '0f95ef9fd27e4804a106d67e8a4d1b84325d25afd5e9be41b3e7e5d1701fa4ad'
NAME = 'aTOMos_v3_6_1_20_Radio_Packet_Studio_Tom_Klootwijk.pdf'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fonts():
    candidates = [
        (Path('C:/Windows/Fonts'), 'calibri.ttf', 'calibrib.ttf', 'consola.ttf'),
        (Path('/usr/share/fonts/truetype/dejavu'), 'DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSansMono.ttf'),
    ]
    for base, normal, bold, mono in candidates:
        if all((base / f).exists() for f in (normal, bold, mono)):
            for name, filename in [('Body', normal), ('Bold', bold), ('Mono', mono)]:
                pdfmetrics.registerFont(TTFont(name, str(base / filename)))
            return
    raise RuntimeError('Install Calibri/Consolas or DejaVu fonts before building.')


def inline(text):
    return re.sub(r'https://[^\s]+', lambda m: '<link href="' + m[0] + '">' + m[0] + '</link>', escape(text))


def main():
    if sha(PARENT_PDF) != PARENT_SHA256:
        raise ValueError('R19 parent PDF hash mismatch')
    fonts()
    source = ROOT / 'formal/RADIO_PACKET_PROFILE.md'
    input_hash = sha(source)
    out = ROOT / 'output/pdf'
    scratch = ROOT / 'tmp/pdf'
    out.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    supplement = scratch / 'r20_supplement.pdf'
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('Text19', fontName='Body', fontSize=10.3, leading=14.5, spaceAfter=8, textColor=colors.HexColor('#243447')))
    styles.add(ParagraphStyle('Title19', fontName='Bold', fontSize=24, leading=29, spaceAfter=16, textColor=colors.HexColor('#123E55')))
    styles.add(ParagraphStyle('Head19', fontName='Bold', fontSize=13, leading=17, spaceBefore=8, spaceAfter=8, textColor=colors.HexColor('#127C80')))
    styles.add(ParagraphStyle('Code19', fontName='Mono', fontSize=8, leading=11, spaceBefore=4, spaceAfter=10, backColor=colors.HexColor('#EEF4F5'), borderPadding=8))
    styles.add(ParagraphStyle('Cell19', parent=styles['Text19'], fontSize=8.6, leading=11, spaceAfter=0))
    body = []
    paragraphs = []
    table_rows = []
    code = None

    def flush_paragraph():
        if paragraphs:
            body.append(Paragraph(inline(' '.join(paragraphs)), styles['Text19']))
            paragraphs.clear()

    def flush_table():
        if not table_rows:
            return
        rows = [[Paragraph(inline(c), styles['Cell19']) for c in row] for row in table_rows]
        t = Table(rows, colWidths=[165, 334], hAlign='LEFT', repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DDECEE')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F6F9FA')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, 0), .6, colors.HexColor('#6C9DAB')),
        ]))
        body.extend([t, Spacer(1, 10)])
        table_rows.clear()

    for line in source.read_text(encoding='utf-8').splitlines():
        if line.startswith('```'):
            flush_paragraph()
            flush_table()
            if code is None:
                code = []
            else:
                body.append(Preformatted('\n'.join(code), styles['Code19']))
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        if line.startswith('|'):
            flush_paragraph()
            cells = [c.strip() for c in line.strip('|').split('|')]
            if not all(set(c) <= {'-', ':', ' '} for c in cells):
                table_rows.append(cells)
            continue
        flush_table()
        if not line.strip():
            flush_paragraph()
        elif line == '<!-- page -->':
            flush_paragraph()
            body.append(PageBreak())
        elif line.startswith('# '):
            flush_paragraph()
            body.append(Paragraph(inline(line[2:]), styles['Title19']))
        elif line.startswith('## '):
            flush_paragraph()
            body.append(Paragraph(inline(line[3:]), styles['Head19']))
        else:
            paragraphs.append(line.strip())
    flush_paragraph()
    flush_table()

    def page_frame(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#C9DCE1'))
        canvas.line(48, 799, 547, 799)
        canvas.setFont('Bold', 8)
        canvas.setFillColor(colors.HexColor('#547985'))
        canvas.drawString(48, 809, 'aTOMos  /  RADIO PACKET STUDIO  /  3.6.1.20')
        canvas.setFont('Body', 8)
        canvas.drawString(48, 27, 'R20 supplement | Tom Klootwijk | 2026-09-17')
        canvas.drawRightString(547, 27, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(str(supplement), pagesize=A4, leftMargin=48, rightMargin=48,
                            topMargin=61, bottomMargin=47, title='aTOMos R20 Radio Packet Studio', author='Tom Klootwijk')
    doc.build(body, onFirstPage=page_frame, onLaterPages=page_frame)
    intro = PdfReader(supplement)
    parent = PdfReader(PARENT_PDF)
    if len(intro.pages) != 7 or len(parent.pages) != 110:
        raise ValueError(f'Unexpected pagination: supplement={len(intro.pages)}, parent={len(parent.pages)}')
    writer = PdfWriter()
    writer.append(intro, import_outline=False)
    writer.append(parent, import_outline=False)
    writer.add_outline_item('R20 radio observation profile', 0)
    writer.add_outline_item('Retained R19 mathematical foundation (original pagination)', len(intro.pages))
    writer.add_metadata({'/Title': 'aTOMos 3.6.1.20 - Radio Packet Studio and Retained R19 Foundation', '/Author': 'Tom Klootwijk'})
    target = out / NAME
    with target.open('wb') as f:
        writer.write(f)
    final = PdfReader(target)
    for i, original in enumerate(parent.pages):
        retained = final.pages[len(intro.pages) + i]
        if original.extract_text() != retained.extract_text():
            raise ValueError(f'Parent text changed on page {i+1}')
        if original.get_contents().get_data() != retained.get_contents().get_data():
            raise ValueError(f'Parent page content changed on page {i+1}')
    if sha(source) != input_hash:
        raise ValueError('Authored source changed during build')
    report = {'pdf': str(target.relative_to(ROOT)), 'sha256': sha(target), 'pages': len(final.pages),
              'new_pages': len(intro.pages), 'retained_pages': len(parent.pages),
              'parent_sha256': PARENT_SHA256, 'parent_page_text_and_streams_equal': True,
              'source_sha256': input_hash, 'visual_review_report': 'review/pdf_visual_review.json'}
    review = ROOT / 'review'
    review.mkdir(exist_ok=True)
    (review / 'pdf_build.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
