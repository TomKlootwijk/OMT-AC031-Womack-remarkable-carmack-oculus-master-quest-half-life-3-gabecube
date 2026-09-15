from pathlib import Path
import hashlib,json,subprocess,datetime
from PIL import Image,ImageDraw
import pypdf,pdfplumber
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
PDF=ROOT/'output/pdf/aTOMos_v3_6_1_9_Orbital_Seed_Kernel_UGTS_Tom_Klootwijk.pdf'
OUT.mkdir(exist_ok=True);low=OUT/'low';full=OUT/'full';low.mkdir(exist_ok=True);full.mkdir(exist_ok=True)
pdf_hash=hashlib.sha256(PDF.read_bytes()).hexdigest()
subprocess.run(['pdftoppm','-r','60','-png',str(PDF),str(low/'page')],check=True)
reader=pypdf.PdfReader(PDF);pages=[];alltext=[]
with pdfplumber.open(PDF) as plumber:
 for n,p in enumerate(reader.pages,1):
  text=p.extract_text() or '';alltext.append(text);chars=plumber.pages[n-1].chars
  outside=[c for c in chars if c['x0']<0 or c['x1']>float(p.mediabox.width)+.5 or c['top']<0 or c['bottom']>float(p.mediabox.height)+.5]
  body=[c for c in chars if 55<c['top']<float(p.mediabox.height)-65]
  pages.append({'page':n,'text_characters':len(text),'body_characters':len(body),'first_lines':text.splitlines()[:5],'outside_media_characters':len(outside),'replacement_characters':text.count('\ufffd'),'bbox':[min(c['x0'] for c in chars),min(c['top'] for c in chars),max(c['x1'] for c in chars),max(c['bottom'] for c in chars)] if chars else None})
(OUT/'extracted.txt').write_text('\n\n'.join(f'=== PAGE {i+1} ===\n{t}' for i,t in enumerate(alltext)),encoding='utf-8')
digits=len(str(len(reader.pages)))
images=[low/f'page-{p:0{digits}d}.png' for p in range(1,len(reader.pages)+1)]
for start in range(0,len(images),12):
 sheet=Image.new('RGB',(1530,2930),'#c8c8c8');draw=ImageDraw.Draw(sheet)
 for j,path in enumerate(images[start:start+12]):
  im=Image.open(path).convert('RGB');im.thumbnail((496,704));x=10+(j%3)*510;y=28+(j//3)*730;sheet.paste(im,(x,y));draw.text((x,y-20),f'Page {start+j+1}',fill='black')
 sheet.save(OUT/f'contact_{start+1:02d}_{min(start+12,len(images)):02d}.png')
selected=list(range(1,len(reader.pages)+1))
subprocess.run(['pdftoppm','-r','120','-png',str(PDF),str(full/'page')],check=True,stdout=subprocess.DEVNULL)
fonts={}
for page in reader.pages:
 resources=page.get('/Resources');resources=resources.get_object() if resources else {}
 entries=resources.get('/Font',{});entries=entries.get_object() if hasattr(entries,'get_object') else entries
 for key,ref in entries.items():
  font=ref.get_object();name=str(font.get('/BaseFont',key));base=font
  if '/DescendantFonts' in font:base=font['/DescendantFonts'][0].get_object()
  descriptor=base.get('/FontDescriptor');descriptor=descriptor.get_object() if descriptor else {}
  fonts[name]={'subtype':str(font.get('/Subtype')),'embedded':any(x in descriptor for x in ['/FontFile','/FontFile2','/FontFile3'])}
assert hashlib.sha256(PDF.read_bytes()).hexdigest()==pdf_hash,'PDF changed during rendering'
report={'pdf_sha256':pdf_hash,'pdf_bytes':PDF.stat().st_size,'page_count':len(reader.pages),'metadata':dict(reader.metadata),'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'all_pages_rendered_dpi':60,'detail_pages_rendered_dpi':120,'detail_pages':selected,'pages':pages,'fonts':fonts,'visual_status':'pending inspection'}
(OUT/'qa.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'pages':len(reader.pages),'outside':[p['page'] for p in pages if p['outside_media_characters']],'empty':[p['page'] for p in pages if p['text_characters']<50],'headlines':[(p['page'],p['first_lines']) for p in pages]},indent=2))
