from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
folder=Path(__file__).resolve().parent/'pdfs'
pages=sorted(folder.glob('review-*.png'))
for group in range(0,len(pages),6):
    canvas=Image.new('RGB',(1440,2100),'#dce1e5')
    draw=ImageDraw.Draw(canvas)
    for index,path in enumerate(pages[group:group+6]):
        im=Image.open(path).convert('RGB');im.thumbnail((700,660))
        x=(index%2)*720+(720-im.width)//2;y=(index//2)*700+28
        canvas.paste(im,(x,y));draw.text((index%2*720+12,y-20),path.stem,fill='black')
    canvas.save(folder/f'contact-{group//6+1}.png')
print(len(pages),'pages')
