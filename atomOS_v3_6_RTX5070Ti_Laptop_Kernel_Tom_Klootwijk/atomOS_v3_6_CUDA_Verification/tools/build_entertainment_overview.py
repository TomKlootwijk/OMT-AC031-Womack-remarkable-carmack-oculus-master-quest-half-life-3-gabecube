"""Render the editable entertainment possibility-space record as a paged PDF."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import Font
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/ENTERTAINMENT_POSSIBILITY_SPACES.md"
OUTPUT = ROOT / "output/pdf/Tom_Klootwijk_atomOS_Entertainment_Possibility_Spaces.pdf"
QA = ROOT / "tmp/pdfs/entertainment_overview"

for name, base in [("Overview", "Helvetica"), ("OverviewBold", "Helvetica-Bold"),
                   ("OverviewItalic", "Helvetica-Oblique")]:
    pdfmetrics.registerFont(Font(name, base, "WinAnsiEncoding"))
pdfmetrics.registerFontFamily("Overview", normal="Overview", bold="OverviewBold",
                              italic="OverviewItalic", boldItalic="OverviewBold")

INK = colors.HexColor("#18212B")
MUTED = colors.HexColor("#53606D")
BLACK = colors.black
WIDTH, HEIGHT = letter
MARGIN = 49
CONTENT_W = WIDTH - MARGIN * 2

styles = {
    "title": ParagraphStyle("Title", fontName="OverviewBold", fontSize=25, leading=30,
                            textColor=BLACK, spaceAfter=12, keepWithNext=True),
    "h2": ParagraphStyle("Heading 1", fontName="OverviewBold", fontSize=17, leading=21,
                         textColor=BLACK, spaceBefore=5, spaceAfter=11, keepWithNext=True),
    "h3": ParagraphStyle("Heading 2", fontName="OverviewBold", fontSize=11.7, leading=15,
                         textColor=BLACK, spaceBefore=8, spaceAfter=6, keepWithNext=True),
    "body": ParagraphStyle("Body", fontName="Overview", fontSize=10.7, leading=14.5,
                           textColor=INK, spaceAfter=8, allowWidows=0, allowOrphans=0),
    "quote": ParagraphStyle("Conversation", fontName="Overview", fontSize=10.4, leading=13.5,
                            textColor=INK, leftIndent=12, spaceAfter=7,
                            allowWidows=0, allowOrphans=0),
    "cell": ParagraphStyle("Cell", fontName="Overview", fontSize=9.3, leading=12.1,
                           textColor=INK, alignment=TA_LEFT),
    "thead": ParagraphStyle("Table Header", fontName="OverviewBold", fontSize=9.3,
                            leading=12.1, textColor=colors.white, alignment=TA_LEFT),
    "subtitle": ParagraphStyle("Subtitle", fontName="Overview", fontSize=12.3, leading=17,
                               textColor=BLACK, spaceAfter=13, keepWithNext=True),
}


def inline(value: str) -> str:
    value = value.replace("\u2014", " - ").replace("\u2013", "-")
    value = value.replace("\u2011", "-").replace("\u2019", "'").replace("\u2018", "'")
    value = value.replace("\u201c", '"').replace("\u201d", '"')
    value = html.escape(value)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
                   r'<link href="\2" color="#245B83"><u>\1</u></link>', value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    return value


class OverviewDocument(BaseDocTemplate):
    def __init__(self, path: Path):
        super().__init__(str(path), pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=43, bottomMargin=45,
                         title="atomOS Entertainment Possibility Spaces",
                         author="Tom Klootwijk; AI-assisted entertainment concept development",
                         subject="Klein log-polar packed LUT games, XR and hypothetical sensory interfaces")
        frame = Frame(MARGIN, 45, CONTENT_W, HEIGHT - 43 - 45, leftPadding=0,
                      rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(PageTemplate(id="Overview", frames=[frame], onPage=self.decorate))
        self.entries = []

    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(MUTED)
        canvas.setFont("Overview", 8)
        canvas.drawString(MARGIN, 23, "Tom Klootwijk  |  atomOS entertainment possibilities  |  0.1")
        canvas.drawRightString(WIDTH - MARGIN, 23, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "outline_key", None):
            title = flowable.getPlainText()
            self.canv.bookmarkPage(flowable.outline_key)
            self.canv.addOutlineEntry(title, flowable.outline_key, level=0, closed=False)
            self.entries.append({"title": title, "page": self.page})


def render_table(lines: list[str]):
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in lines if not re.match(r"^\|\s*:?-{3}", line)]
    ncol = len(rows[0])
    fractions = {2: [0.25, 0.75], 3: [0.26, 0.30, 0.44], 4: [0.07, 0.21, 0.44, 0.28]}[ncol]
    if ncol == 3 and rows[0][0] == "ID":
        fractions = [0.07, 0.24, 0.69]
    if ncol == 3 and rows[0][0] == "Step":
        fractions = [0.08, 0.54, 0.38]
    widths = [CONTENT_W * x for x in fractions]
    data = [[Paragraph(inline(cell), styles["thead" if i == 0 else "cell"])
             for cell in row] for i, row in enumerate(rows)]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263D50")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F7")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9D9D9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    table.spaceAfter = 10
    return table


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    source = SOURCE.read_text(encoding="utf-8")
    lines = source.splitlines()
    story = []
    i = 0
    section = 0
    on_cover = True
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line == "<!-- page -->":
            story.append(PageBreak())
            on_cover = False
            i += 1
            continue
        if line.startswith("#"):
            depth = len(line) - len(line.lstrip("#"))
            text = line[depth:].strip()
            style = "title" if depth == 1 else ("h2" if depth == 2 else "h3")
            if on_cover and depth == 2:
                style = "subtitle"
            para = Paragraph(inline(text), styles[style])
            if depth <= 2 and style != "subtitle":
                section += 1
                para.outline_key = f"section-{section}"
            story.append(para)
            i += 1
            continue
        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            story.append(render_table(table_lines))
            continue
        quote = line.startswith(">")
        chunks = []
        while i < len(lines):
            current = lines[i].strip()
            if not current or current.startswith(("#", "|", "<!--")):
                break
            if quote:
                if not current.startswith(">") or current == ">":
                    break
                chunks.append(current[1:].strip())
            else:
                if current.startswith(">"):
                    break
                chunks.append(current)
            i += 1
        if chunks:
            story.append(Paragraph(inline(" ".join(chunks)), styles["quote" if quote else "body"]))
        else:
            i += 1
    doc = OverviewDocument(OUTPUT)
    doc.build(story)

    from pypdf import PdfReader
    reader = PdfReader(OUTPUT)
    pages = [{"page": i + 1, "characters": len(p.extract_text()),
              "opening": p.extract_text().splitlines()[1:4]} for i, p in enumerate(reader.pages)]
    result = {
        "source": str(SOURCE), "pdf": str(OUTPUT), "page_count": len(reader.pages),
        "planned_pages": source.count("<!-- page -->") + 1,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "pdf_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "pages": pages, "outline": doc.entries,
        "visual_review": "pending",
    }
    (QA / "build.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
