#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nr × nf の格子探索。LTASS 残差だけでなく、ミュージカルノイズの指標も見る。"""
import numpy as np, soundfile as sf, subprocess, json, evaluate as E
from nr_sweep import analyse, best_eq, HP


def musical_noise(path):
    """静かな区間で、log スペクトルがフレーム間でどれだけ暴れるか（2-8kHz）。
    スペクトル減算のかけ過ぎで出る「ピロピロ」を捉える。"""
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    s = x.mean(axis=1).astype(np.float64)
    W = 1024
    blk = E.block_levels(s, sr, W)
    q = np.where(blk <= np.percentile(blk, 10))[0]
    fr = np.fft.rfftfreq(W, 1 / sr)
    band = (fr >= 2000) & (fr < 8000)
    win = np.hanning(W)
    S = []
    for k in q:
        seg = s[k * W:(k + 1) * W]
        if len(seg) < W:
            continue
        S.append(10 * np.log10(np.abs(np.fft.rfft(seg * win)) ** 2 + 1e-20)[band])
    S = np.array(S)
    return float(np.median(S.std(axis=0)))          # ビンごとの時間方向のばらつき


rows = []
for nr in (0, 12, 16, 20, 24, 30):
    for nf in (-50, -45, -40):
        if nr == 0 and nf != -45:
            continue
        out = f'g_{nr}_{abs(nf)}.wav'
        af = HP if nr == 0 else f"{HP},afftdn=nr={nr}:nf={nf}"
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', 'test_src.wav', '-af',
                        f"pan=mono|c0=0.5*c0+0.5*c1,{af}", '-c:a', 'pcm_f32le', out], check=True)
        sp, nz, dev, snr = analyse(out)
        gain, resid, rms = best_eq(dev, snr)
        rows.append({'nr': nr, 'nf': nf, 'resid': round(rms, 2), 'mus': round(musical_noise(out), 2),
                     'sp8k': round(sp[8000], 1), 'snr8k': round(snr[8000], 1),
                     'gain': {f: round(g, 2) for f, g in gain.items()}})

print(f"{'nr':>3} {'nf':>4} {'residRMS':>9} {'musical':>8} {'sp8k':>6} {'S/N8k':>6}")
for r in rows:
    print(f"{r['nr']:3} {r['nf']:4} {r['resid']:9.2f} {r['mus']:8.2f} {r['sp8k']:6.1f} {r['snr8k']:6.1f}")
json.dump(rows, open('nr_grid.json', 'w'))
