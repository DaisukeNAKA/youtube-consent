#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""クリップ／リミッター／AGC／帯域 を切り分ける"""
import numpy as np, soundfile as sf, json, sys
f = sys.argv[1] if len(sys.argv) > 1 else 'raw_f32.wav'
x, sr = sf.read(f, dtype='float32', always_2d=True)
n, nch = x.shape
R = {"file": f, "sr": sr, "dur_min": round(n / sr / 60, 1)}

for c in range(nch):
    s = x[:, c].astype(np.float64); a = np.abs(s); d = {}
    # --- 1. 真のフラットトップ（連続サンプルの差分が微小かつ高振幅）
    dif = np.abs(np.diff(s))
    hi = a[:-1] > 0.7
    flat = hi & (dif < 1e-4)
    if flat.any():
        dd = np.diff(flat.astype(np.int8)); st = np.where(dd == 1)[0] + 1; en = np.where(dd == -1)[0] + 1
        if flat[0]: st = np.r_[0, st]
        if flat[-1]: en = np.r_[en, len(flat)]
        runs = en - st
        d["true_flattop_runs"] = int(len(runs)); d["flattop_ge3"] = int((runs >= 3).sum()); d["flattop_max"] = int(runs.max())
        i = np.argsort(runs)[-5:][::-1]
        d["flattop_worst"] = [{"t": round(float(st[k] / sr), 2), "len": int(runs[k]), "lvl_db": round(float(20*np.log10(a[st[k]])), 2)} for k in i]
    else:
        d["true_flattop_runs"] = 0
    # --- 2. 50ms ピークの分布: リミッターの天井があるか
    W = int(sr * 0.05); m = n // W
    pk = np.abs(s[:m * W].reshape(m, W)).max(axis=1)
    rms = np.sqrt((s[:m * W].reshape(m, W) ** 2).mean(axis=1))
    act = rms > 10 ** (-40 / 20)                       # 発話とみなす区間
    pkd = 20 * np.log10(pk[act] + 1e-12)
    d["pk50ms_pcts"] = {p: round(float(np.percentile(pkd, p)), 2) for p in (50, 75, 90, 95, 99, 99.5, 99.9, 100)}
    hist, edges = np.histogram(pkd[pkd > -20], bins=np.arange(-20, 2.5, 0.5))
    top = np.argsort(hist)[-4:][::-1]
    d["pk50ms_mode_bins"] = [{"db": round(float(edges[k]), 1), "n": int(hist[k])} for k in top]
    # 天井への張り付き度: -1dB 以内に入る 50ms ブロックの割合
    d["pk50ms_within1dB_of_0_pct"] = round(float((pkd > -1).mean() * 100), 3)
    d["pk50ms_within3dB_of_0_pct"] = round(float((pkd > -3).mean() * 100), 3)
    # --- 3. 入出力カーブ: 短期RMS(400ms) と そのブロック内ピークの関係（圧縮の兆候）
    W2 = int(sr * 0.4); m2 = n // W2
    blk = s[:m2 * W2].reshape(m2, W2)
    r2 = 20 * np.log10(np.sqrt((blk ** 2).mean(axis=1)) + 1e-12)
    p2 = 20 * np.log10(np.abs(blk).max(axis=1) + 1e-12)
    sel = r2 > -40
    d["crest_vs_level"] = {}
    for lo, hi_ in ((-40, -30), (-30, -25), (-25, -20), (-20, -15), (-15, -10)):
        q = sel & (r2 >= lo) & (r2 < hi_)
        if q.sum() > 20:
            d["crest_vs_level"][f"{lo}..{hi_}"] = {"n": int(q.sum()), "crest_db": round(float(np.median(p2[q] - r2[q])), 2)}
    # --- 4. 帯域: 平均スペクトル（発話区間）と HF カットオフ
    idx = np.where(act)[0]
    take = idx[np.argsort(rms[act])[-400:]]            # 大きめの 400 ブロック
    sp = np.zeros(W // 2 + 1)
    for k in take:
        seg = s[k * W:(k + 1) * W] * np.hanning(W)
        sp += np.abs(np.fft.rfft(seg)) ** 2
    sp /= len(take); fr = np.fft.rfftfreq(W, 1 / sr)
    spd = 10 * np.log10(sp + 1e-20); ref = spd[(fr > 300) & (fr < 1000)].mean()
    d["spectrum_rel_db"] = {f"{int(f0)}Hz": round(float(spd[(fr >= f0) & (fr < f1)].mean() - ref), 1)
                            for f0, f1 in ((50,100),(100,200),(200,400),(400,800),(800,1600),(1600,3200),(3200,6400),(6400,10000),(10000,14000),(14000,16000),(16000,18000),(18000,20000),(20000,23000))}
    for cut in (14000, 15000, 16000, 17000, 18000, 19000, 20000):
        d.setdefault("hf_rolloff_db", {})[f"{cut}"] = round(float(spd[(fr >= cut) & (fr < cut + 500)].mean() - ref), 1)
    # --- 5. ノイズフロア（最も静かな 2% ブロック）のスペクトル傾向
    quiet = np.argsort(rms)[:max(10, int(m * 0.02))]
    qs = np.zeros(W // 2 + 1)
    for k in quiet:
        qs += np.abs(np.fft.rfft(s[k * W:(k + 1) * W] * np.hanning(W))) ** 2
    qs /= len(quiet); qsd = 10 * np.log10(qs + 1e-20)
    d["noise_floor_dbfs_rms"] = round(float(20 * np.log10(np.sqrt((rms[quiet] ** 2).mean()) + 1e-12)), 1)
    d["noise_spectrum_rel_db"] = {f"{int(f0)}Hz": round(float(qsd[(fr >= f0) & (fr < f1)].mean() - ref), 1)
                                  for f0, f1 in ((50,200),(200,1000),(1000,4000),(4000,8000),(8000,16000))}
    R[f"ch{c}"] = d
print(json.dumps(R, ensure_ascii=False, indent=1, default=float))
