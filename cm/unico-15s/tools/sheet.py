#!/usr/bin/env python3
"""確認用コンタクトシート（絵コンテ実写版）を作る
usage: python3 tools/sheet.py out/unico_cm15_916.mp4 out/sheet_916.jpg 0.2,1.5,3.0,...
"""
import subprocess, sys, os, io
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
FONT = next((p for p in ['/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf', '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf'] if os.path.exists(p)), None)


def grab(path, t):
    r = subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-ss', f'{t:.3f}', '-i', path, '-frames:v', '1', '-f', 'image2pipe', '-c:v', 'png', '-'], capture_output=True, check=True)
    return Image.open(io.BytesIO(r.stdout)).convert('RGB')


def main(src, dst, times, cols=None, thumb_w=None):
    ims = [grab(src, t) for t in times]
    w0, h0 = ims[0].size
    vertical = h0 > w0
    cols = cols or (6 if vertical else 4)
    tw = thumb_w or (300 if vertical else 440); th = round(tw * h0 / w0)
    rows = (len(ims) + cols - 1) // cols
    pad, lab = 14, 34
    sheet = Image.new('RGB', (cols * (tw + pad) + pad, rows * (th + lab + pad) + pad), '#14101f')
    d = ImageDraw.Draw(sheet); f = ImageFont.truetype(FONT, 22) if FONT else None
    for i, (im, t) in enumerate(zip(ims, times)):
        x = pad + (i % cols) * (tw + pad); y = pad + (i // cols) * (th + lab + pad)
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y + lab))
        d.text((x + 2, y + 4), f'{t:05.2f}s  f{round(t * 30):03d}', fill='#f4f0ff', font=f)
    sheet.save(dst, quality=90)
    print('wrote', dst, sheet.size)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], [float(x) for x in sys.argv[3].split(',')])
