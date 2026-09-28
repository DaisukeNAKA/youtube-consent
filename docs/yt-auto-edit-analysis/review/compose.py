#!/usr/bin/env python3
"""compose.py out.jpg label1=img1 label2=img2 ...  : 横並び比較シート（各 640px 幅にリサイズ、ラベル付き）"""
import sys
from PIL import Image, ImageDraw, ImageFont
out=sys.argv[1]; items=[a.rsplit('=',1) for a in sys.argv[2:]]
W=640; tiles=[]
font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',22)
for label,path in items:
    im=Image.open(path).convert('RGB'); h=int(im.height*W/im.width); im=im.resize((W,h))
    t=Image.new('RGB',(W,h+34),'black'); t.paste(im,(0,34)); d=ImageDraw.Draw(t); d.text((8,5),label,fill='white',font=font); tiles.append(t)
H=max(t.height for t in tiles); sheet=Image.new('RGB',(W*len(tiles)+8*(len(tiles)-1),H),'black')
x=0
for t in tiles: sheet.paste(t,(x,0)); x+=W+8
sheet.save(out,quality=90); print(out,sheet.size)
