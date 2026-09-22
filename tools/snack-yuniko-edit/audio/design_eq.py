#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""実測の LTASS 乖離から補正カーブを作る。ブーストは帯域ごとの S/N で頭打ちにする。"""
import numpy as np, soundfile as sf, json, sys, evaluate as E

x, sr = sf.read('test_src.wav', dtype='float32', always_2d=True)
s = x.mean(axis=1).astype(np.float64)
blk = E.block_levels(s, sr)
speech_mask = blk >= np.percentile(blk, 60)
quiet_mask = blk <= np.percentile(blk, 10)
sp = E.third_oct_spectrum(s, sr, speech_mask)
nz = E.third_oct_spectrum(s, sr, quiet_mask)

score = [f for f in E.BANDS if E.SCORE_LO <= f <= E.SCORE_HI]
ref_m = np.mean([E.LTASS[f] for f in score])
cur_m = np.mean([sp[f] for f in score])
dev = {f: sp[f] - cur_m - (E.LTASS[f] - ref_m) for f in E.BANDS}
snr = {f: sp[f] - nz[f] for f in E.BANDS}

MAX_CUT, MAX_BOOST = 8.0, 9.0
SNR_FLOOR = 22.0            # 補正後にこの S/N を下回る帯域はブーストしない

rows = []
for f in E.BANDS:
    want = -dev[f]
    g = float(np.clip(want, -MAX_CUT, MAX_BOOST))
    if g > 0:
        # S/N が低い帯域はブーストしても粗さが出るだけなので抑える
        head = max(0.0, snr[f] - SNR_FLOOR)
        g = min(g, head)
    rows.append((f, sp[f], nz[f], snr[f], dev[f], g))

print(f"{'Hz':>6} {'speech':>7} {'noise':>7} {'S/N':>6} {'dev':>7} {'gain':>6}")
for f, s_, n_, r_, d_, g_ in rows:
    print(f"{f:6} {s_:7.1f} {n_:7.1f} {r_:6.1f} {d_:7.2f} {g_:6.2f}")

curve = {f: g for f, _, _, _, _, g in rows}
json.dump(curve, open('eq_curve.json', 'w'))
