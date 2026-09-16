#!/usr/bin/env python3
"""スナックゆに子 #28 のサムネイル様式（写真＋極太文字＋黄色アクセント＋左上タグ）を踏襲して 1280x720 を生成"""
import sys, math
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
S = '/tmp/claude-0/-home-user-youtube-consent/75fb4748-18f5-575e-b185-0e9bb1183b06/scratchpad'
src, out, top_text, bottom_parts = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
# bottom_parts: "相方だけ|呼ばれず。" → 前半黄色、後半白
crop = tuple(int(v) for v in (sys.argv[5].split(',') if len(sys.argv) > 5 else "120,60,1400,780".split(',')))
BIG = f'{S}/fonts/Dela_Gothic_One.ttf'; TAG = f'{S}/fonts/Yusei_Magic.ttf'
YELLOW = (255, 214, 0); BLACK = (20, 20, 20); WHITE = (255, 255, 255)

img = Image.open(src).convert('RGB').crop(crop).resize((1280, 720), Image.LANCZOS)
img = ImageEnhance.Contrast(img).enhance(1.08); img = ImageEnhance.Color(img).enhance(1.12)
d = ImageDraw.Draw(img)

def text_w(font, s): return int(font.getlength(s))
def draw_outlined(x, y, s, font, fill, outline, sw):
    d.text((x, y), s, font=font, fill=fill, stroke_width=sw, stroke_fill=outline, anchor='la')

# 上段: 黒文字＋白縁（さらに外側に薄い黒縁で締める）
f_top = ImageFont.truetype(BIG, 118)
w = text_w(f_top, top_text); x = (1280 - w) // 2; y = 26
d.text((x, y), top_text, font=f_top, fill=BLACK, stroke_width=14, stroke_fill=BLACK, anchor='la')
d.text((x, y), top_text, font=f_top, fill=BLACK, stroke_width=9, stroke_fill=WHITE, anchor='la')
# 下段: 前半黄色＋黒縁、後半白＋黒縁
f_bot = ImageFont.truetype(BIG, 132)
p1, p2 = bottom_parts.split('|')
w1, w2 = text_w(f_bot, p1), text_w(f_bot, p2)
x = (1280 - (w1 + w2)) // 2; y = 528
draw_outlined(x, y, p1, f_bot, YELLOW, BLACK, 12)
draw_outlined(x + w1, y, p2, f_bot, WHITE, BLACK, 12)
# 左上タグ「スナックゆに子」: 黄色の箱に黒文字、少し傾ける
f_tag = ImageFont.truetype(TAG, 44)
tag = 'スナックゆに子'; tw = text_w(f_tag, tag)
tag_img = Image.new('RGBA', (tw + 44, 74), (0, 0, 0, 0)); td = ImageDraw.Draw(tag_img)
td.rounded_rectangle([0, 0, tw + 43, 73], radius=10, fill=YELLOW + (255,), outline=BLACK + (255,), width=4)
td.text((22, 12), tag, font=f_tag, fill=BLACK + (255,), anchor='la')
tag_img = tag_img.rotate(4, expand=True, resample=Image.BICUBIC)
img.paste(tag_img, (18, 16), tag_img)
# 黄色の「キラッ」線（#28 と同様のアクセント）
d = ImageDraw.Draw(img)
def spark(cx, cy, r=26, n=3, ang0=-60, spread=35, wdt=10):
    for k in range(n):
        a = math.radians(ang0 + k * spread)
        x1, y1 = cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55
        x2, y2 = cx + math.cos(a) * r * 1.6, cy + math.sin(a) * r * 1.6
        d.line([(x1, y1), (x2, y2)], fill=BLACK, width=wdt + 6)
        d.line([(x1, y1), (x2, y2)], fill=YELLOW, width=wdt)
spark(1180, 150, ang0=-150, spread=40); spark(120, 250, ang0=-40, spread=-40); spark(1200, 470, ang0=170, spread=40)
img.save(out, quality=92)
print('saved', out, img.size)
