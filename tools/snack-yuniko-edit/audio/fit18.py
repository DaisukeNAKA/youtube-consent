#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#18 を目標にした補正カーブを、パラメトリック EQ に当てはめる。"""
import numpy as np, json
from scipy.optimize import minimize
from scipy.ndimage import median_filter
import evaluate as E

SR = 48000
MAX_BOOST = 13.0
MAX_CUT = 10.0
d = json.load(open('target18.json'))
t = {int(k): v for k, v in d['target'].items()}
s = {int(k): v for k, v in d['src'].items()}
tn = {int(k): v for k, v in d['target_noise'].items()}
sn = {int(k): v for k, v in d['src_noise'].items()}

BANDS = [b for b in E.BANDS if 100 <= b <= 16000]
want = np.array([t[b] - s[b] for b in BANDS])
head_raw = np.array([(tn[b] + 6.0) - sn[b] for b in BANDS])
head = median_filter(head_raw, size=3, mode='nearest')      # 雑音余裕の推定ばらつきを均す
want_s = median_filter(want, size=3, mode='nearest')        # 目標側も1バンドの外れ値を均す

TG = np.clip(want_s, -MAX_CUT, MAX_BOOST)
TG = np.where(TG > 0, np.minimum(TG, np.maximum(0.0, head)), TG)
TG = median_filter(TG, size=3, mode='nearest')              # 制約でギザついた分をもう一度均す
Wt = np.array([0.5 if b < 125 or b > 12500 else 1.0 for b in BANDS])
FS = np.array(BANDS, dtype=float)

print(f"{'Hz':>6} {'欲しい':>7} {'均し':>6} {'余裕':>6} {'目標':>6}")
for b, w, ws, h, g in zip(BANDS, want, want_s, head, TG):
    print(f"{b:6} {w:7.1f} {ws:6.1f} {h:6.1f} {g:6.1f}")


def biquad_db(kind, f0, Q, gdb, f):
    A = 10 ** (gdb / 40); w0 = 2 * np.pi * f0 / SR
    cw, sw = np.cos(w0), np.sin(w0); al = sw / (2 * Q)
    if kind == 'peak':
        b = [1 + al * A, -2 * cw, 1 - al * A]; a = [1 + al / A, -2 * cw, 1 - al / A]
    elif kind == 'low':
        sq = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) - (A - 1) * cw + sq), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sq)]
        a = [(A + 1) + (A - 1) * cw + sq, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sq]
    else:
        sq = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) + (A - 1) * cw + sq), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sq)]
        a = [(A + 1) - (A - 1) * cw + sq, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sq]
    z = np.exp(-1j * 2 * np.pi * f / SR)
    H = (b[0] + b[1] * z + b[2] * z ** 2) / (a[0] + a[1] * z + a[2] * z ** 2)
    return 20 * np.log10(np.abs(H) + 1e-12)


# 各バンドの周波数帯を重ならないように区切る。
# 重なりを許すと「-12 dB と +10 dB がほぼ同じ周波数で打ち消し合う」解に落ちて、
# 当てはめ誤差は小さくても Premiere / Audition で再現する意味が無くなるため。
SPEC = [('low', 180, 120, 280), ('peak', 700, 400, 900), ('peak', 1400, 900, 1800),
        ('peak', 2500, 1800, 3200), ('high', 4000, 3200, 6000), ('peak', 10000, 7000, 14000)]
x0, lo, hi = [], [], []
for kind, f0, fa, fb in SPEC:
    x0 += [np.log(f0), np.log(1.0), 0.0]
    lo += [np.log(fa), np.log(0.5), -12.0]
    hi += [np.log(fb), np.log(2.5), 14.0]


def resp(p):
    out = np.zeros_like(FS)
    for i, sp in enumerate(SPEC):
        out += biquad_db(sp[0], np.exp(p[3*i]), np.exp(p[3*i+1]), p[3*i+2], FS)
    return out


def cost(p):
    r = resp(p) - TG
    gains = np.array([p[3*i+2] for i in range(len(SPEC))])
    # 打ち消し合う大ゲインの組を避けるため、ゲインの二乗にごく軽い罰則を付ける
    return float((Wt * r ** 2).sum() + 0.02 * (gains ** 2).sum())


best, bc = None, 1e18
for seed in range(60):
    rng = np.random.default_rng(seed)
    p0 = np.array(x0) + rng.normal(0, 0.2, len(x0))
    r = minimize(cost, p0, bounds=list(zip(lo, hi)), method='L-BFGS-B', options={'maxiter': 6000, 'ftol': 1e-12})
    if r.fun < bc: bc, best = r.fun, r.x

fit = resp(best)
print(f"\n当てはめ誤差 RMS {np.sqrt(((fit-TG)**2).mean()):.2f} dB")
print(f"{'Hz':>6} {'目標':>7} {'適合':>7} {'差':>6}")
for b, tg, v in zip(BANDS, TG, fit):
    print(f"{b:6} {tg:7.1f} {v:7.1f} {v-tg:6.1f}")
bands = []
print()
for i, sp in enumerate(SPEC):
    f0, Q, g = np.exp(best[3*i]), np.exp(best[3*i+1]), best[3*i+2]
    nm = {'low': 'lowshelf', 'high': 'highshelf', 'peak': 'peak'}[sp[0]]
    bands.append({'type': nm, 'f': round(float(f0), 1), 'Q': round(float(Q), 2), 'gain_db': round(float(g), 2)})
    print(f"{nm:9} f={f0:8.1f} Hz  Q={Q:4.2f}  gain={g:+6.2f} dB")
json.dump(bands, open('eq_bands18.json', 'w'), indent=1)
