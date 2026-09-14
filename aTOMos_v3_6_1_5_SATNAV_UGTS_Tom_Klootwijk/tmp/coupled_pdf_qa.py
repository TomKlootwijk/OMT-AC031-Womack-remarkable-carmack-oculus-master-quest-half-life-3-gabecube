from pathlib import Path
from PIL import Image, ImageDraw
from pypdf import PdfReader
import pdfplumber, json, re, hashlib, sys
sys.stdout.reconfigure(encoding='utf-8')
workspace=Path(__file__).resolve().parents[1]
root=workspace/'atomOS_3_6_1_7_COUPLED'
pdf=root/'output/pdf/aTOMos_v3_6_1_7_Coupled_Geometry_Physical_Kernel_UGTS_Tom_Klootwijk.pdf'
folder=workspace/'tmp/pdfs/coupled_final'
pages=sorted(folder.glob('review-*.png'))
texts=[p.extract_text() or '' for p in PdfReader(pdf).pages]
assert len(pages)==len(texts) and all(texts)
for group in range(0,len(pages),6):
    sheet=Image.new('RGB',(1440,2100),'#dce1e5')
    draw=ImageDraw.Draw(sheet)
    for i,path in enumerate(pages[group:group+6]):
        page=Image.open(path).convert('RGB'); page.thumbnail((700,660))
        x=(i%2)*720+(720-page.width)//2; y=(i//2)*700+28
        sheet.paste(page,(x,y)); draw.text((i%2*720+12,y-20),path.stem,fill='black')
    sheet.save(folder/f'contact-{group//6+1:02}.png')
log=(root/'docs/.build/satnav.log').read_text(encoding='utf-8',errors='replace')
bad=[line for line in log.splitlines() if re.search(r'Overfull|Underfull|Missing character|undefined',line)]
assert not bad,bad
outside=[]
with pdfplumber.open(pdf) as document:
    for i,page in enumerate(document.pages):
        for char in page.chars:
            if char['text'].strip() and (char['x0']<0 or char['x1']>page.width+.1 or char['top']<0 or char['bottom']>page.height+.1):
                outside.append({'page':i+1,'text':char['text']})
assert not outside,outside
whole='\n'.join(texts)
for expected in ['3.6.1.7','320,876','3,308','24,832','circle-plus','eigenmatrix']:
    assert expected in whole,expected
for i,t in enumerate(texts):
    print(i+1, ' | '.join(t.splitlines()[:4]))
(folder/'extracted_pages.json').write_text(json.dumps(texts,indent=2),encoding='utf-8')
report={'status':'automated_checks_passed_visual_pending','pdf':pdf.relative_to(root).as_posix(),'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'pages':len(texts),'rendered_pages':len(pages),'extractable_text_all_pages':True,'page_boundary_violations':outside,'tex_layout_or_glyph_warnings':bad,'engine':'Tectonic 0.17.0; newpxtext type1; Poppler render'}
(folder/'automated_preflight.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
