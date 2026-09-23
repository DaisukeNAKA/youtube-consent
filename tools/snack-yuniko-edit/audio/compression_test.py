#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決定的テスト: 話者Aの声は、Aのマイク(近接・大音量)とBのマイク(回り込み・小音量)の両方に入る。
Bのマイクは同じ声を遥かに低いレベルで拾うため、リミッターが作動しない「圧縮されていない基準」になる。
A の短期レベルを B の短期レベルに対してプロットし、傾きが 1 未満に折れ曲がれば A 側が圧縮されている。
"""
import numpy as np, soundfile as sf, json
x, sr = sf.read('raw_f32.wav', dtype='float32', always_2d=True)
W = int(sr * 0.05)                      # 50ms
m = x.shape[0] // W
b = x[:m * W].reshape(m, W, 2).astype(np.float64)
rms = np.sqrt((b ** 2).mean(axis=1))    # (m,2)
db = 20 * np.log10(rms + 1e-12)
res = {}
for talker, other in ((0, 1), (1, 0)):
    # 話者 talker が明確に主で、相手が黙っている区間のみ採用（分離度 >= 8dB）
    sep = db[:, talker] - db[:, other]
    sel = (sep >= 8) & (db[:, other] > -55) & (db[:, talker] > -45)
    a = db[sel, talker]; o = db[sel, other]
    r = {"n_blocks": int(sel.sum())}
    # 回り込みレベル o を説明変数にして、a の平均を帯域別に出す（= 入出力カーブ）
    bins = np.arange(-50, -18, 2.0)
    curve = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        q = (o >= lo) & (o < hi)
        if q.sum() >= 30:
            curve.append({"bleed_db": round(float((lo + hi) / 2), 1), "n": int(q.sum()),
                          "talker_db": round(float(np.median(a[q])), 2)})
    r["io_curve"] = curve
    # 低域側と高域側で傾きを比較（線形なら両方 1.0 付近）
    if len(curve) >= 6:
        cx = np.array([c["bleed_db"] for c in curve]); cy = np.array([c["talker_db"] for c in curve])
        h = len(curve) // 2
        r["slope_low_half"] = round(float(np.polyfit(cx[:h + 1], cy[:h + 1], 1)[0]), 3)
        r["slope_high_half"] = round(float(np.polyfit(cx[h:], cy[h:], 1)[0]), 3)
        r["slope_overall"] = round(float(np.polyfit(cx, cy, 1)[0]), 3)
    res[f"talker_ch{talker}"] = r
print(json.dumps(res, ensure_ascii=False, indent=1, default=float))
