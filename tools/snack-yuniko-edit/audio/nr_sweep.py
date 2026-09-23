#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NR の強さごとに「EQ で到達できる LTASS 残差」を計算し、最適な NR 量を決める。"""
import numpy as np, soundfile as sf, subprocess, json, evaluate as E

HP = "highpass=f=75:poles=2,bandreject=f=100:w=6"
MAX_CUT, MAX_BOOST, SNR_FLOOR = 8.0, 9.0, 22.0
score = [f for f in E.BANDS if E.SCORE_LO <= f <= E.SCORE_HI]
ref_m = np.mean([E.LTASS[f] for f in score])


def analyse(path):
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    s = x.mean(axis=1).astype(np.float64)
    blk = E.block_levels(s, sr)
    sp = E.third_oct_spectrum(s, sr, blk >= np.percentile(blk, 60))
    nz = E.third_oct_spectrum(s, sr, blk <= np.percentile(blk, 10))
    cur_m = np.mean([sp[f] for f in score])
    dev = {f: sp[f] - cur_m - (E.LTASS[f] - ref_m) for f in E.BANDS}
    snr = {f: sp[f] - nz[f] for f in E.BANDS}
    return sp, nz, dev, snr


def best_eq(dev, snr):
    gain, resid = {}, {}
    for f in E.BANDS:
        g = float(np.clip(-dev[f], -MAX_CUT, MAX_BOOST))
        if g > 0:
            g = min(g, max(0.0, snr[f] - SNR_FLOOR))
        gain[f] = g
        resid[f] = dev[f] + g
    rr = np.array([resid[f] for f in score])
    rr = rr - rr.mean()                      # 全体の音量差は loudnorm で吸収される
    return gain, resid, float(np.sqrt((rr ** 2).mean()))


rows = []
for nr in (0, 4, 8, 12, 16, 20, 24, 30):
    out = f'nrs_{nr}.wav'
    af = HP if nr == 0 else f"{HP},afftdn=nr={nr}:nf=-45"
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', 'test_src.wav', '-af',
                    f"pan=mono|c0=0.5*c0+0.5*c1,{af}", '-c:a', 'pcm_f32le', out], check=True)
    sp, nz, dev, snr = analyse(out)
    gain, resid, rms = best_eq(dev, snr)
    rows.append({'nr': nr, 'ltass_resid_rms': round(rms, 2),
                 'snr8k': round(snr[8000], 1), 'snr10k': round(snr[10000], 1),
                 'sp8k': round(sp[8000], 1), 'sp10k': round(sp[10000], 1),
                 'gain8k': round(gain[8000], 1), 'gain10k': round(gain[10000], 1),
                 'gain1k': round(gain[1000], 1), 'gain200': round(gain[200], 1),
                 'gain': {f: round(g, 2) for f, g in gain.items()}})

print(f"{'nr':>3} {'residRMS':>9} {'S/N8k':>6} {'S/N10k':>7} {'sp8k':>6} {'sp10k':>6} {'g200':>5} {'g1k':>6} {'g8k':>5} {'g10k':>5}")
for r in rows:
    print(f"{r['nr']:3} {r['ltass_resid_rms']:9.2f} {r['snr8k']:6.1f} {r['snr10k']:7.1f} "
          f"{r['sp8k']:6.1f} {r['sp10k']:6.1f} {r['gain200']:5.1f} {r['gain1k']:6.1f} {r['gain8k']:5.1f} {r['gain10k']:5.1f}")
json.dump(rows, open('nr_sweep.json', 'w'))
