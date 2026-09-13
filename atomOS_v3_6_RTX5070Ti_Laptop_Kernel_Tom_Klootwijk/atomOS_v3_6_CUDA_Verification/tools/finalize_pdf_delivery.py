"""Record completed visual PDF QA and final unsigned delivery hashes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
from pypdf import PdfReader
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / 'results/residency_followup'
PDF = ROOT / 'output/pdf/atomOS_v3_6_Kernel_Validation_Texture_Cache.pdf'
RENDERS = ROOT / 'tmp/pdfs/final_residency'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p, d): p.write_text(json.dumps(d, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def main():
    summary = read(E/'summary.json')
    assert summary['status'] == 'execution_validated_residency_observed'
    reader = PdfReader(PDF)
    assert len(reader.pages) == 8
    pages = []
    for i, page in enumerate(reader.pages, 1):
        raster = RENDERS/f'page-{i}.png'
        assert raster.is_file()
        text = page.extract_text()
        assert text and '\ufffd' not in text and '\u25a0' not in text
        pages.append(dict(page=i, rendered_png_sha256=sha(raster), text_characters=len(text),
                          visual_review='passed', observed_layout_defects=[]))
    all_text = '\n'.join(p.extract_text() for p in reader.pages)
    assert all(s in all_text for s in ('24/24', '18/18', '626,288', '134,521', '131,072'))
    with pdfplumber.open(PDF) as document:
        for page in document.pages:
            assert all(c['x0'] >= -0.1 and c['x1'] <= page.width+0.1 and c['top'] >= -0.1 and c['bottom'] <= page.height+0.1 for c in page.chars)
    uris = []
    for page in reader.pages:
        for ref in page.get('/Annots', []):
            action = ref.get_object().get('/A', {})
            if action.get('/URI'): uris.append(str(action['/URI']))
    assert len(uris) == 4 and all(u.startswith('https://docs.nvidia.com/') for u in uris)
    qa = dict(schema='atomOS-final-residency-pdf-qa', status='passed',
              created_at_utc=datetime.now(timezone.utc).isoformat(), pdf=str(PDF), pdf_sha256=sha(PDF),
              pages=pages, page_count=len(reader.pages), renderer='Poppler pdftoppm -r 90 -png',
              visual_review_scope='All eight final page PNGs inspected for clipping, overlap, glyph corruption, table fit and footer placement.',
              renderer_warnings=["No display font for 'Symbol'", "No display font for 'ArialUnicode'"],
              warning_assessment='No affected glyphs or visual defects observed in any final page.',
              out_of_page_text='none', reference_link_uris=uris)
    write(E/'pdf_qa.json', qa)
    status_path = ROOT/'results/validation_status.json'
    status = read(status_path)
    status['current_pdf'] = dict(path=PDF.relative_to(ROOT).as_posix(), sha256=sha(PDF), pages=8,
                                 qa='results/residency_followup/pdf_qa.json')
    write(status_path, status)
    manifest = read(E/'source_sha256.json')
    manifest['files'][Path(__file__).resolve().relative_to(ROOT).as_posix()] = sha(Path(__file__))
    for name in manifest['files']: manifest['files'][name] = sha(ROOT/name)
    write(E/'source_sha256.json', manifest)
    paths = [PDF, ROOT/'output/bin/atomos_cache_bulk.exe', ROOT/'output/bin/atomos_cuda.exe',
             ROOT/'output/bin/atomos_cpu.exe', ROOT/'output/bin/atomos_cuda_historical_c2e551de.exe',
             E/'summary.json', E/'source_sha256.json', E/'final_evidence_sha256.json', E/'pdf_qa.json', status_path]
    write(ROOT/'output/DELIVERY_SHA256.json', dict(schema='atomOS-final-delivery-sha256',
          scope='Unsigned integrity record; historical binary is labelled explicitly. This manifest excludes itself.',
          files={p.relative_to(ROOT).as_posix(): sha(p) for p in paths}))
    print(json.dumps(dict(pdf=str(PDF), sha256=sha(PDF), pages=8, qa='passed'), indent=2))

if __name__ == '__main__': main()
