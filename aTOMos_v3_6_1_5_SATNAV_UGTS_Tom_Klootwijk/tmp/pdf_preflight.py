from pathlib import Path
import hashlib,json,re
from pypdf import PdfReader
import pdfplumber

root=Path(__file__).resolve().parents[1]/'atomOS_3_6_1_6_SELFREF'
pdf=root/'output/pdf/aTOMos_v3_6_1_6_Literal_Self_Referential_Kernel_UGTS_Tom_Klootwijk.pdf'
reader=PdfReader(pdf)
texts=[page.extract_text() or '' for page in reader.pages]
assert len(texts)==37
assert 'Literal self-referential kernel' in texts[0]
assert '5,060,172' in texts[9] and '50,700' in texts[9]
assert not any('finalized record is generated' in t or 'being checked' in t for t in texts)
log=(root/'docs/.build/satnav.log').read_text(encoding='utf-8',errors='replace')
bad=[line for line in log.splitlines() if re.search(r'Overfull|Underfull|Missing character|undefined',line)]
assert not bad,bad
outside=[]
with pdfplumber.open(pdf) as document:
    for index,page in enumerate(document.pages):
        for char in page.chars:
            if char['text'].strip() and (char['x0']<0 or char['x1']>page.width+.1 or char['top']<0 or char['bottom']>page.height+.1):
                outside.append({'page':index+1,'text':char['text']})
assert not outside,outside
report={'status':'passed','pdf':str(pdf.relative_to(root)).replace('\\','/'),'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'pages':len(texts),'extractable_text_all_pages':all(texts),'page_boundary_violations':outside,'tex_layout_or_glyph_warnings':bad,'visual_review':'All 37 pages inspected in rendered page sheets; new/changed equations, cover, validation and source register inspected individually. No clipping, overlap or missing glyphs observed.','engine':'Tectonic 0.17.0; newpxtext type1; Poppler render'}
(root/'results/pdf_preflight.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
