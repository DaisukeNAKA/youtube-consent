#!/usr/bin/env python3
"""素材の再生成（公開リポジトリには肖像写真・ロゴ・フォントを置かないため、手元の原本から作り直す）

入力（private/ に置く。private/ は .gitignore 済み）:
  private/unico_photo.jpg   … 2ショット写真（Drive「ユニコ.JPG」, iPhone撮影 3434x2576）
  private/logo.jpg          … ロゴ 目あり（Drive 01_ロゴ素材/目あり.jpg, 1280x1280）
  private/logo_noeyes.jpg   … ロゴ 目なし（Drive 01_ロゴ素材/目なし.jpg）
出力（assets/ も .gitignore 済み）:
  assets/nakatsuka.png  assets/nakatsuka_solo.png  assets/ricchan.png  assets/logo.png  assets/logo_noeyes.png

手順: BiRefNet-portrait（rembg, ローカル実行・外部API不使用）で背景除去 → 手でトレースした境界＋色判定で
2人を分離 → 中塚さん単独用に、リッチャン☆の手と袖で隠れていた胴体をスーツ柄のクローンで補完。
EXIF（撮影位置のGPSを含む）は出力PNGに引き継がない。
依存: pip install "rembg[cpu]" opencv-python-headless pillow numpy
"""
import os
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
LUM = np.array([.299, .587, .114])

# 元写真を幅1100に縮めた座標系で手トレースした境界（中塚さん側＝左）
BOUNDARY = [(610, 0), (610, 330), (622, 360), (628, 380), (631, 400), (638, 425), (643, 441), (643, 478), (628, 478), (624, 452), (618, 440),
            (608, 440), (601, 447), (600, 505), (575, 512), (556, 520), (553, 553), (558, 580), (563, 592), (569, 605), (556, 615), (548, 620),
            (543, 632), (533, 684), (523, 750), (513, 816), (511, 826)]
TORSO = [(596, 436), (646, 440), (652, 520), (655, 700), (660, 826), (500, 826), (505, 700), (528, 640), (536, 600), (540, 520), (585, 470)]
OUT_H = 1800 / 2352   # 書き出し縮尺（中塚さんレイヤー高さ2352px→1800px）


def cutout(src_path):
    from rembg import remove, new_session
    im = Image.open(src_path).convert('RGB')
    return np.array(remove(im, session=new_session('birefnet-portrait'), post_process_mask=False).convert('RGBA'))


def poly(W, H, pts, k):
    m = Image.new('L', (W, H), 0); ImageDraw.Draw(m).polygon([(x * k, y * k) for x, y in pts], fill=255); return np.array(m)


def save_layer(arr, alpha, name):
    out = arr.copy(); out[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    o = Image.fromarray(out, 'RGBA'); bb = o.getbbox(); o = o.crop(bb)
    o = o.resize((round(o.width * OUT_H), round(o.height * OUT_H)), Image.LANCZOS)
    o.save(P('assets', name), optimize=True); print(name, 'bbox', bb, '->', o.size)
    return bb


def main():
    os.makedirs(P('assets'), exist_ok=True)
    src = np.array(Image.open(P('private', 'unico_photo.jpg')).convert('RGB')).astype(np.float32)
    cut = cutout(P('private', 'unico_photo.jpg'))
    H, W = cut.shape[:2]; k = W / 1100
    a = cut[..., 3].astype(np.float32)
    # 1) 境界ポリゴン＋サムズアップ周辺の紺色画素は中塚さん側へ
    m = poly(W, H, [(0, 0)] + BOUNDARY + [(0, 1100)], k).astype(np.float32) / 255
    rgb = cut[..., :3].astype(np.float32); l = rgb @ LUM
    suit = (rgb[..., 2] >= rgb[..., 0] - 8) & (l < 120)
    zone = np.zeros((H, W), bool); zone[int(410 * k):int(640 * k), int(540 * k):int(650 * k)] = True
    sz = cv2.morphologyEx((suit & zone).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    sz = cv2.morphologyEx(sz, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)).astype(np.float32)
    hm = cv2.GaussianBlur(np.maximum(m, sz), (0, 0), 2.0)
    layout = {'photo': [W, H]}
    layout['nakatsuka'] = save_layer(cut, a * hm, 'nakatsuka.png')
    # リッチャン☆: 最大連結成分のみ
    ra = a * np.clip(1 - hm, 0, 1)
    n, lab, st, _ = cv2.connectedComponentsWithStats((ra > 40).astype(np.uint8), 8)
    keep = (lab == (np.argmax(st[1:, cv2.CC_STAT_AREA]) + 1)).astype(np.uint8)
    layout['ricchan'] = save_layer(cut, ra * cv2.GaussianBlur(cv2.dilate(keep, np.ones((3, 3), np.uint8)).astype(np.float32), (0, 0), 1), 'ricchan.png')
    # 2) 中塚さん単独版: 隠れていた胴体をスーツ柄のクローンで補完
    na = cut.astype(np.float32).copy(); na[..., 3] = a * hm
    Y, X = np.mgrid[0:H, 0:W]
    r, g, b = na[..., 0], na[..., 1], na[..., 2]
    na[(X > 590 * k) & (Y < 445 * k) & (r > 120) & (r > b + 25) & (g > 90), 3] = 0      # 金髪の残り
    na[(X > 500 * k) & (r > b + 35) & (r > g + 35) & (X > 545 * k), 3] = 0                # ピンクの袖の残り
    body = poly(W, H, TORSO, k) > 127
    hole = body & ((na[..., 3] < 200) | ((X > 548 * k) & (Y > 425 * k) & (Y < 545 * k)))
    ys, xs = np.where(hole)
    fill = np.zeros((len(xs), 3)); done = np.zeros(len(xs), bool)
    for dxu, dyu in [(-125, 40), (-125, 230), (-90, 260), (-160, 300), (-200, 120)]:
        sx = np.clip(xs + int(dxu * k), 0, W - 1); sy = np.clip(ys + int(dyu * k), 0, H - 1); p = src[sy, sx]
        ok = ((p @ LUM) < 105) & (p[:, 2] >= p[:, 0] - 12); use = ok & ~done; fill[use] = p[use]; done |= use
    if (~done).any(): fill[~done] = fill[done].mean(0)
    na[ys, xs, :3] = fill * (1 - np.clip((xs / k - 560) / 100, 0, 1) * .22)[:, None]; na[ys, xs, 3] = 255
    bl = cv2.GaussianBlur(na[..., :3], (0, 0), 2.0); mm = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 3)[..., None]
    na[..., :3] = na[..., :3] * (1 - mm * .55) + bl * (mm * .55)
    aa = cv2.GaussianBlur(na[..., 3], (0, 0), 1.5); na[..., 3] = np.maximum(a * hm * (na[..., 3] > 0), aa * (body | (na[..., 3] > 0)))
    layout['nakatsukaSolo'] = save_layer(na.clip(0, 255).astype(np.uint8), na[..., 3], 'nakatsuka_solo.png')
    import json
    json.dump({k: list(v) for k, v in layout.items()}, open(P('assets', 'layout.json'), 'w'))
    # 3) ロゴ: 円形に切り抜き（JPEGの白い四隅を透明に）
    for s, d in [('logo.jpg', 'logo.png'), ('logo_noeyes.jpg', 'logo_noeyes.png')]:
        im = Image.open(P('private', s)).convert('RGB'); arr = np.array(im).astype(int)
        ys_, xs_ = np.where(arr.sum(2) < 735); cx = (xs_.min() + xs_.max()) / 2; cy = (ys_.min() + ys_.max()) / 2
        rr = min(xs_.max() - xs_.min(), ys_.max() - ys_.min()) / 2; ss = 4
        mk = Image.new('L', (im.width * ss, im.height * ss), 0)
        ImageDraw.Draw(mk).ellipse([(cx - rr + 1) * ss, (cy - rr + 1) * ss, (cx + rr - 1) * ss, (cy + rr - 1) * ss], fill=255)
        o = im.convert('RGBA'); o.putalpha(mk.resize(im.size, Image.LANCZOS))
        o = o.crop((int(cx - rr), int(cy - rr), int(cx + rr) + 1, int(cy + rr) + 1)).resize((1024, 1024), Image.LANCZOS)
        o.save(P('assets', d), optimize=True); print(d)
    print('assets/layout.json にレイヤー外接矩形（元写真座標）を書き出しました。顔枠は engine.js の FACE_PHOTO（元写真座標）を参照。')


if __name__ == '__main__':
    main()
