#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目標カーブにパラメトリック EQ（RBJ biquad）を最小二乗で当てはめる。
Premiere / Audition でそのまま入力できる数値にするのが目的。"""
import numpy as np, json
from scipy.optimize import minimize
import evaluate as E

SR = 48000
# 実測の乖離（nr=16 / nf=-50 のあと）を、物理的に妥当な形に均した目標。
#  ・低域は S/N と衣擦れを考えて +6 dB で頭打ち
#  ・胸元共鳴（630-2000 Hz）の抑制が本体
#  ・高域は「山」ではなくシェルフ。+7 dB 上限（これ以上はヒスが立つ）
TARGET = {100: 3.0, 125: 5.0, 160: 6.0, 200: 6.0, 250: 3.0, 315: -2.0, 400: -1.0,
          500: -2.5, 630: -7.0, 800: -8.0, 1000: -8.5, 1250: -8.0, 1600: -8.5,
          2000: -8.0, 2500: -5.5, 3150: -6.5, 4000: -3.5, 5000: 1.0, 6300: 4.5,
          8000: 7.0, 10000: 7.0, 12500: 7.0}
FS = np.array(sorted(TARGET), dtype=float)
TG = np.array([TARGET[int(f)] for f in FS])
Wt = np.array([0.4 if f < 125 or f > 10000 else 1.0 for f in FS])


def biquad_db(kind, f0, Q, gdb, f):
    A = 10 ** (gdb / 40)
    w0 = 2 * np.pi * f0 / SR
    cw, sw = np.cos(w0), np.sin(w0)
    al = sw / (2 * Q)
    if kind == 'peak':
        b = [1 + al * A, -2 * cw, 1 - al * A]; a = [1 + al / A, -2 * cw, 1 - al / A]
    elif kind == 'low':
        s = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) - (A - 1) * cw + s), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - s)]
        a = [(A + 1) + (A - 1) * cw + s, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - s]
    else:   # high shelf
        s = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) + (A - 1) * cw + s), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - s)]
        a = [(A + 1) - (A - 1) * cw + s, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - s]
    z = np.exp(-1j * 2 * np.pi * f / SR)
    H = (b[0] + b[1] * z + b[2] * z ** 2) / (a[0] + a[1] * z + a[2] * z ** 2)
    return 20 * np.log10(np.abs(H) + 1e-12)


# 低シェルフ1 + ピーク3 + 高シェルフ1（Premiere / Audition にそのまま入る5バンド）
SPEC = [('low', 180), ('peak', 800), ('peak', 1600), ('peak', 3000), ('high', 5500)]
x0, lo, hi = [], [], []
for kind, f0 in SPEC:
    x0 += [np.log(f0), np.log(1.0), 0.0]
    lo += [np.log(f0 / 1.8), np.log(0.4), -10.0]
    hi += [np.log(f0 * 1.8), np.log(2.2), 10.0]


def resp(p):
    out = np.zeros_like(FS)
    for i, (kind, _) in enumerate(SPEC):
        f0, Q, g = np.exp(p[3 * i]), np.exp(p[3 * i + 1]), p[3 * i + 2]
        out += biquad_db(kind, f0, Q, g, FS)
    return out


def cost(p):
    r = resp(p) - TG
    return float((Wt * r ** 2).sum())


best, bc = None, 1e18
for seed in range(40):
    rng = np.random.default_rng(seed)
    p0 = np.array(x0) + rng.normal(0, 0.15, len(x0))
    r = minimize(cost, p0, bounds=list(zip(lo, hi)), method='L-BFGS-B',
                 options={'maxiter': 4000, 'ftol': 1e-12})
    if r.fun < bc:
        bc, best = r.fun, r.x

fit = resp(best)
print(f"残差二乗和 {bc:.3f}   RMS誤差 {np.sqrt(((fit-TG)**2).mean()):.2f} dB\n")
print(f"{'Hz':>6} {'目標':>7} {'適合':>7} {'差':>6}")
for f, t, v in zip(FS, TG, fit):
    print(f"{int(f):6} {t:7.2f} {v:7.2f} {v-t:6.2f}")
print()
bands = []
for i, (kind, _) in enumerate(SPEC):
    f0, Q, g = np.exp(best[3 * i]), np.exp(best[3 * i + 1]), best[3 * i + 2]
    bands.append({'type': kind, 'f': round(float(f0), 1), 'Q': round(float(Q), 2), 'gain_db': round(float(g), 2)})
    print(f"{kind:5} f={f0:8.1f} Hz  Q={Q:4.2f}  gain={g:+6.2f} dB")
json.dump(bands, open('eq_bands.json', 'w'), indent=1)
