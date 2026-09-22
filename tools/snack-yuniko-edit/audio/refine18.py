#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""実際に掛けた結果と #18 の残差を使って、EQ を1回だけ閉ループで詰める。"""
import numpy as np, soundfile as sf, json, subprocess
from scipy.optimize import minimize
from scipy.ndimage import median_filter
import evaluate as E

SR = 48000
A = (315, 400, 500, 630, 800, 1000)
BANDS = [b for b in E.BANDS if 100 <= b <= 16000]
FS = np.array(BANDS, dtype=float)
Wt = np.array([0.5 if b < 125 or b > 12500 else 1.0 for b in BANDS])


def spec(p):
    x, sr = sf.read(p, dtype='float32', always_2d=True)
    s = x.mean(axis=1).astype(np.float64)
    b = E.block_levels(s, sr)
    d = E.third_oct_spectrum(s, sr, b >= np.percentile(b, 60))
    a = np.mean([d[k] for k in A])
    return np.array([d[k] - a for k in BANDS])


ref = spec('ref18_src_n.wav')
got = spec('Y18_-8_n.wav')
resid = got - ref
resid -= np.average(resid, weights=Wt)          # 全体の音量差は loudnorm が吸収する
resid = median_filter(resid, size=3, mode='nearest')

prev = json.load(open('eq_bands18.json'))
SPEC = [('low', 180, 120, 280), ('peak', 700, 400, 900), ('peak', 1400, 900, 1800),
        ('peak', 2500, 1800, 3200), ('high', 4000, 3200, 6000), ('peak', 10000, 7000, 14000)]


def biquad_db(kind, f0, Q, gdb, f):
    Ag = 10 ** (gdb / 40); w0 = 2 * np.pi * f0 / SR
    cw, sw = np.cos(w0), np.sin(w0); al = sw / (2 * Q)
    if kind == 'peak':
        b = [1 + al * Ag, -2 * cw, 1 - al * Ag]; a = [1 + al / Ag, -2 * cw, 1 - al / Ag]
    elif kind == 'low':
        sq = 2 * np.sqrt(Ag) * al
        b = [Ag*((Ag+1)-(Ag-1)*cw+sq), 2*Ag*((Ag-1)-(Ag+1)*cw), Ag*((Ag+1)-(Ag-1)*cw-sq)]
        a = [(Ag+1)+(Ag-1)*cw+sq, -2*((Ag-1)+(Ag+1)*cw), (Ag+1)+(Ag-1)*cw-sq]
    else:
        sq = 2 * np.sqrt(Ag) * al
        b = [Ag*((Ag+1)+(Ag-1)*cw+sq), -2*Ag*((Ag-1)+(Ag+1)*cw), Ag*((Ag+1)+(Ag-1)*cw-sq)]
        a = [(Ag+1)-(Ag-1)*cw+sq, 2*((Ag-1)-(Ag+1)*cw), (Ag+1)-(Ag-1)*cw-sq]
    z = np.exp(-1j * 2 * np.pi * f / SR)
    H = (b[0] + b[1]*z + b[2]*z**2) / (a[0] + a[1]*z + a[2]*z**2)
    return 20 * np.log10(np.abs(H) + 1e-12)


def resp(p):
    out = np.zeros_like(FS)
    for i, sp_ in enumerate(SPEC):
        out += biquad_db(sp_[0], np.exp(p[3*i]), np.exp(p[3*i+1]), p[3*i+2], FS)
    return out


cur = np.concatenate([[np.log(b['f']), np.log(b['Q']), b['gain_db']] for b in prev])
TG = resp(cur) - resid                            # いま出ている特性から残差を引いたものが新目標
TG = np.clip(TG, -12, 14)
print(f"{'Hz':>6} {'現在':>7} {'残差':>7} {'新目標':>7}")
for b, c, r, t in zip(BANDS, resp(cur), resid, TG):
    print(f"{b:6} {c:7.1f} {r:7.1f} {t:7.1f}")

lo = [v for sp_ in SPEC for v in (np.log(sp_[2]), np.log(0.5), -12.0)]
hi = [v for sp_ in SPEC for v in (np.log(sp_[3]), np.log(2.5), 14.0)]


def cost(p):
    r = resp(p) - TG
    g = np.array([p[3*i+2] for i in range(len(SPEC))])
    return float((Wt * r**2).sum() + 0.02 * (g**2).sum())


best, bc = None, 1e18
for seed in range(60):
    rng = np.random.default_rng(seed)
    p0 = cur + rng.normal(0, 0.15, len(cur))
    p0 = np.clip(p0, lo, hi)
    r = minimize(cost, p0, bounds=list(zip(lo, hi)), method='L-BFGS-B', options={'maxiter': 6000, 'ftol': 1e-12})
    if r.fun < bc: bc, best = r.fun, r.x

fit = resp(best)
print(f"\n当てはめ誤差 RMS {np.sqrt(((fit-TG)**2).mean()):.2f} dB\n")
out = []
for i, sp_ in enumerate(SPEC):
    f0, Q, g = np.exp(best[3*i]), np.exp(best[3*i+1]), best[3*i+2]
    nm = {'low': 'lowshelf', 'high': 'highshelf', 'peak': 'peak'}[sp_[0]]
    out.append({'type': nm, 'f': round(float(f0), 1), 'Q': round(float(Q), 2), 'gain_db': round(float(g), 2)})
    print(f"{nm:9} f={f0:8.1f} Hz  Q={Q:4.2f}  gain={g:+6.2f} dB")
json.dump(out, open('eq_bands18b.json', 'w'), indent=1)
