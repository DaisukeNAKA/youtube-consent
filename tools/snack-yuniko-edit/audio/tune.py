#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#18 を目標に、EQ を当てはめ→適用→残差で詰める、を繰り返す。

帯域ごとの「雑音余裕」を事前制約にするやり方は、サンプルの取り方で推定が
大きくぶれたため採用しない。上限を固定で置き、ヒスの増加は最後に
noise_hf_tilt とミュージカルノイズの実測で確認する。
"""
import numpy as np, soundfile as sf, subprocess, json, sys
from scipy.optimize import minimize
from scipy.ndimage import median_filter
from scipy.signal import butter, sosfilt
import evaluate as E, deess

SR = 48000
A = (315, 400, 500, 630, 800, 1000)
BANDS = [b for b in E.BANDS if 100 <= b <= 16000]
FS = np.array(BANDS, dtype=float)
Wt = np.array([0.5 if b < 125 or b > 12500 else 1.0 for b in BANDS])
MAX_BOOST, MAX_CUT = 13.0, 10.0
HP = "highpass=f=75:poles=2,bandreject=f=100:w=6"
NR = "afftdn=nr=16:nf=-50"
COMP = "acompressor=threshold=-20dB:ratio=2.2:attack=10:release=150:makeup=1:knee=6"
MONO = "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1"
SPEC = [('low', 180, 120, 280), ('peak', 700, 400, 900), ('peak', 1400, 900, 1800),
        ('peak', 2500, 1800, 3200), ('high', 4000, 3200, 6000), ('peak', 10000, 7000, 14000)]


def spec(p, mask='speech'):
    x, sr = sf.read(p, dtype='float32', always_2d=True)
    s = x.mean(axis=1).astype(np.float64)
    b = E.block_levels(s, sr)
    m = b >= np.percentile(b, 60) if mask == 'speech' else b <= np.percentile(b, 10)
    d = E.third_oct_spectrum(s, sr, m)
    a = np.mean([d[k] for k in A]) if mask == 'speech' else 0.0
    if mask != 'speech':
        d2 = E.third_oct_spectrum(s, sr, b >= np.percentile(b, 60))
        a = np.mean([d2[k] for k in A])
    return np.array([d[k] - a for k in BANDS])


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


def fit(TG, start=None):
    lo = [v for sp_ in SPEC for v in (np.log(sp_[2]), np.log(0.5), -MAX_CUT - 2)]
    hi = [v for sp_ in SPEC for v in (np.log(sp_[3]), np.log(2.5), MAX_BOOST + 1)]
    x0 = start if start is not None else np.concatenate(
        [[np.log(sp_[1]), np.log(1.0), 0.0] for sp_ in SPEC])

    def cost(p):
        r = resp(p) - TG
        g = np.array([p[3*i+2] for i in range(len(SPEC))])
        return float((Wt * r**2).sum() + 0.02 * (g**2).sum())

    best, bc = None, 1e18
    for seed in range(60):
        rng = np.random.default_rng(seed)
        p0 = np.clip(x0 + rng.normal(0, 0.2, len(x0)), lo, hi)
        r = minimize(cost, p0, bounds=list(zip(lo, hi)), method='L-BFGS-B',
                     options={'maxiter': 6000, 'ftol': 1e-12})
        if r.fun < bc: bc, best = r.fun, r.x
    return best


def eq_str(bands):
    out = []
    for b in bands:
        f, q, g = b['f'], b['Q'], b['gain_db']
        if b['type'] == 'lowshelf': out.append(f"bass=f={f}:width_type=q:width={q}:g={g}")
        elif b['type'] == 'highshelf': out.append(f"treble=f={f}:width_type=q:width={q}:g={g}")
        else: out.append(f"equalizer=f={f}:t=q:w={q}:g={g}")
    return ",".join(out)


def to_bands(p):
    out = []
    for i, sp_ in enumerate(SPEC):
        nm = {'low': 'lowshelf', 'high': 'highshelf', 'peak': 'peak'}[sp_[0]]
        out.append({'type': nm, 'f': round(float(np.exp(p[3*i])), 1),
                    'Q': round(float(np.exp(p[3*i+1])), 2), 'gain_db': round(float(p[3*i+2]), 2)})
    return out


def apply_chain(bands, deess_thresh, tag):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', 'test_src.wav', '-af',
                    f"{HP},{eq_str(bands)},{NR}", '-c:a', 'pcm_f32le', f'tu_{tag}.wav'], check=True)
    x, sr = sf.read(f'tu_{tag}.wav', dtype='float32', always_2d=True)
    if deess_thresh is None:
        y = x.astype(np.float64); duty = 0.0
    else:
        ys, grs = [], []
        for c in range(2):
            yy, gr = deess.deess_ratio(x[:, c].astype(np.float64), sr, 5200, deess_thresh, 5.0, max_gr_db=10)
            ys.append(yy); grs.append(gr)
        y = np.stack(ys, axis=1); g = np.concatenate(grs); duty = float((g > 0.5).mean() * 100)
    sf.write(f'tud_{tag}.wav', y.astype(np.float32), sr)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f'tud_{tag}.wav', '-af',
                    f"{COMP},{MONO},loudnorm=I=-13:TP=-1.0:LRA=9", '-ar', '48000',
                    '-c:a', 'pcm_f32le', f'TU_{tag}_n.wav'], check=True)
    return f'TU_{tag}_n.wav', duty


def report(path, ref, label, duty=None):
    g = spec(path)
    dv = g - ref
    keep = np.array([125 <= b <= 10000 for b in BANDS])
    d2 = dv[keep] - dv[keep].mean()
    x, sr = sf.read(path, dtype='float32', always_2d=True); s = x.mean(axis=1).astype(np.float64)
    sos = butter(4, [5000, 9000], btype='band', fs=sr, output='sos'); h = sosfilt(sos, s)
    W = int(sr*0.02); n = len(s)//W
    hd = 20*np.log10(np.sqrt((h[:n*W].reshape(n, W)**2).mean(axis=1))+1e-12)
    td = 20*np.log10(np.sqrt((s[:n*W].reshape(n, W)**2).mean(axis=1))+1e-12)
    act = td > np.percentile(td, 60)
    ev = E.evaluate(path, label)
    print(f"{label:14} 乖離RMS {np.sqrt((d2**2).mean()):5.2f} 最大 {np.abs(d2).max():4.1f} | "
          f"sibP99 {np.percentile(hd[act],99):6.1f} p99.9 {np.percentile(hd[act],99.9):6.1f} | "
          f"nzHF {ev['noise_hf_tilt_db']:6.1f}" + (f" | 作動 {duty:4.1f}%" if duty is not None else ""))
    return dv
