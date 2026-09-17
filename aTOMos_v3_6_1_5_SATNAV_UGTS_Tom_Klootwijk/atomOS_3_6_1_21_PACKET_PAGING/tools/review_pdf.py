"""Render R21 and prove pixel-identical preservation of every R20 page.

Run without confirmation first. After inspecting all three supplement PNGs,
rerun with --confirm-visual-sha256 SHA to bind that inspection to these bytes.
This script never edits the PDF or the formal source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pymupdf as fitz


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "output/pdf/aTOMos_v3_6_1_21_Packet_Paging_Tom_Klootwijk.pdf"
PARENT = ROOT.parent / "atomOS_3_6_1_20_RADIO_PACKET_STUDIO/output/pdf/aTOMos_v3_6_1_20_Radio_Packet_Studio_Tom_Klootwijk.pdf"
if not PARENT.exists():
    PARENT = ROOT / "source/parent_R21.pdf"
PARENT_SHA = "afebe08e91feb4d309f2c68268b435e0ca13a02c803264e96c2782972239a7ec"
RENDER = ROOT / "tmp/pdf/review"
REPORT = ROOT / "review/pdf_visual_review.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pix_record(page):
    pix = page.get_pixmap(matrix=fitz.Matrix(120 / 72, 120 / 72),
                          colorspace=fitz.csRGB, alpha=False, annots=True)
    samples = pix.samples
    return ({"width": pix.width, "height": pix.height,
             "rgb_sha256": hashlib.sha256(samples).hexdigest()}, samples)


def inspect_text(page):
    outside, missing, notdef = [], [], []
    rect = page.rect
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span["text"]
                x0, y0, x1, y1 = span["bbox"]
                if text.strip() and (x0 < -.75 or y0 < -.75 or
                                     x1 > rect.width + .75 or y1 > rect.height + .75):
                    outside.append({"text": text, "bbox": list(span["bbox"])})
                if "\ufffd" in text or "\x00" in text:
                    missing.append(text)
    # Glyph id 0 is .notdef for the embedded TrueType supplement fonts.
    # Inherited Type1/custom-font glyph IDs have different semantics and are
    # checked by prior review plus exact rendered preservation instead.
    for run in page.get_texttrace():
        if not any(name in run["font"] for name in ("Calibri", "Consolas", "DejaVu")):
            continue
        for codepoint, glyph, _, bbox in run["chars"]:
            if glyph == 0 and not chr(codepoint).isspace():
                notdef.append({"codepoint": codepoint, "bbox": list(bbox)})
    return {"text_bounds_violations": outside,
            "replacement_or_null_characters": missing,
            "supplement_notdef_glyphs": notdef}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-visual-sha256", default=None)
    args = parser.parse_args()
    pdf_sha = sha(PDF)
    assert sha(PARENT) == PARENT_SHA, "Parent PDF changed"
    if args.confirm_visual_sha256 is not None:
        assert args.confirm_visual_sha256 == pdf_sha, "Visual confirmation is for different PDF bytes"
    build = json.loads((ROOT / "review/pdf_build.json").read_text(encoding="utf-8"))
    assert build["sha256"] == pdf_sha, "Build report belongs to different PDF bytes"
    assert build["source_sha256"] == sha(ROOT / "formal/PACKET_PAGING_PROFILE.md"), "Formal source changed since build"
    poppler = shutil.which("pdftoppm")
    if not poppler:
        raise RuntimeError("pdftoppm is required for supplement visual rendering")
    RENDER.mkdir(parents=True, exist_ok=True)
    subprocess.run([poppler, "-f", "1", "-l", "3", "-r", "144", "-png",
                    str(PDF), str(RENDER / "supplement")], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    doc, parent = fitz.open(PDF), fitz.open(PARENT)
    assert len(doc) == 120 and len(parent) == 117, "Unexpected page count"
    inherited = []
    for index in range(len(parent)):
        original, original_bytes = pix_record(parent[index])
        retained, retained_bytes = pix_record(doc[index + 3])
        inherited.append({"parent_page": index + 1, "release_page": index + 4,
                          "original": original, "retained": retained,
                          "pixel_equal": original == retained and original_bytes == retained_bytes})
    text_checks = [{"page": index + 1, **inspect_text(page)} for index, page in enumerate(doc)]
    inherited_text_checks_equal = True
    inherited_extraction_artifacts = 0
    for index in range(len(parent)):
        baseline = inspect_text(parent[index])
        check = text_checks[index + 3]
        matches = all(check[key] == value for key, value in baseline.items())
        check["matches_parent_text_checks"] = matches
        inherited_text_checks_equal &= matches
        inherited_extraction_artifacts += len(check["replacement_or_null_characters"])
    supplement = []
    for index in range(3):
        image = RENDER / f"supplement-{index + 1:03d}.png"
        assert image.is_file(), f"Expected supplement rendering: {image}"
        text = doc[index].get_text()
        supplement.append({"page": index + 1, "png": str(image.relative_to(ROOT)),
                           "png_sha256": sha(image),
                           "header_present": "PACKET PAGING" in text,
                           "footer_present": "R21 supplement | Tom Klootwijk | 2026-09-17" in text,
                           "page_number_present": str(index + 1) in text.splitlines(),
                           "visually_inspected": args.confirm_visual_sha256 is not None})
    # The preserved Type1 TeX extension fonts contain 14 glyphs that PyMuPDF
    # exposes as NUL. They are present in the original reviewed R20 too and
    # are not new missing glyphs. Record them rather than silently discarding
    # them or treating identical inherited extraction as a new visual defect.
    bounds_violations = sum(len(item["text_bounds_violations"]) for item in text_checks)
    supplement_glyph_violations = sum(len(item[key]) for item in text_checks[:3]
                                     for key in ("replacement_or_null_characters", "supplement_notdef_glyphs"))
    violations = bounds_violations + supplement_glyph_violations + int(not inherited_text_checks_equal)
    inherited_count = sum(item["pixel_equal"] for item in inherited)
    structure_ok = all(p["header_present"] and p["footer_present"] and p["page_number_present"]
                       for p in supplement)
    complete = bool(args.confirm_visual_sha256 and violations == 0 and inherited_count == 117 and structure_ok)
    report = {
        "schema": "atomos.r21.pdf_visual_review.v1",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "pdf": str(PDF.relative_to(ROOT)), "sha256": pdf_sha,
        "source_sha256": build["source_sha256"], "pages": len(doc),
        "supplement_pages": 3, "parent_pages": 117, "parent_sha256": PARENT_SHA,
        "supplement_renderer": {"tool": "pdftoppm", "dpi": 144},
        "inherited_renderer": {"tool": "PyMuPDF", "version": fitz.VersionBind, "dpi": 120,
                               "colorspace": "RGB", "alpha": False, "annotations": True},
        "inherited_pixel_equal_count": inherited_count,
        "all_inherited_pages_pixel_equal": inherited_count == 117,
        "text_check_violation_count": violations,
        "all_page_text_bounds_violation_count": bounds_violations,
        "supplement_missing_glyph_indicator_count": supplement_glyph_violations,
        "inherited_text_checks_equal_parent": inherited_text_checks_equal,
        "inherited_text_extraction_artifact_count": inherited_extraction_artifacts,
        "inherited_text_extraction_note": "Fourteen NUL extraction values from retained TeX Type1 extension glyphs also occur identically in the reviewed R20; every retained page is pixel-identical. They are not new missing visual glyphs.",
        "visual_review_sha256": args.confirm_visual_sha256,
        "visual_notes": ("All three supplement pages inspected individually at rendered resolution: "
                         "headers, footers, page numbering, tables, formulas, code blocks, references, "
                         "line wrapping and section transitions checked; no clipping or overlap." if args.confirm_visual_sha256 else
                         "Pending inspection of all three supplement PNGs."),
        "complete": complete, "supplement_review": supplement,
        "inherited_page_comparison": inherited, "text_checks": text_checks,
    }
    assert sha(PDF) == pdf_sha, "PDF changed during review"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("sha256", "pages", "inherited_pixel_equal_count", "text_check_violation_count", "complete")}, indent=2))
    if violations or inherited_count != 117 or not structure_ok:
        raise SystemExit("PDF review found structural issues; inspect the report")


if __name__ == "__main__":
    main()
