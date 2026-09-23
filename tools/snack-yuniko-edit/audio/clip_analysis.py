#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ワイヤレスマイク収録のクリップ／ピーク挙動を実測する"""
import sys, json, numpy as np, soundfile as sf

path = sys.argv[1]
x, sr = sf.read(path, dtype='float32', always_2d=True)
n, ch = x.shape
res = {"file": path, "sr": sr, "ch": ch, "dur_s": round(n / sr, 1)}

for c in range(ch):
    s = x[:, c]
    a = np.abs(s)
    peak = float(a.max())
    res[f"ch{c}"] = {
        "peak_dbfs": round(20 * np.log10(peak + 1e-12), 3),
        "rms_dbfs": round(20 * np.log10(np.sqrt(np.mean(s ** 2)) + 1e-12), 2),
    }
    # サンプル値のヒストグラム上端: 0dBFS 近傍にどれだけ張り付いているか
    for thr_db in (-0.1, -0.3, -0.5, -1.0, -2.0, -3.0):
        thr = 10 ** (thr_db / 20)
        res[f"ch{c}"][f"n_over_{thr_db}dB"] = int((a >= thr).sum())
    # 連続クリップ（フラットトップ）検出: |x| >= 0.98 が k サンプル以上連続
    thr = 0.98
    over = a >= thr
    if over.any():
        d = np.diff(over.astype(np.int8))
        starts = np.where(d == 1)[0] + 1
        ends = np.where(d == -1)[0] + 1
        if over[0]: starts = np.r_[0, starts]
        if over[-1]: ends = np.r_[ends, len(over)]
        runs = ends - starts
        res[f"ch{c}"]["flat_runs_total"] = int(len(runs))
        for k in (2, 3, 5, 10, 20):
            res[f"ch{c}"][f"flat_runs_ge_{k}"] = int((runs >= k).sum())
        res[f"ch{c}"]["flat_run_max_samples"] = int(runs.max())
        idx = np.argsort(runs)[-8:][::-1]
        res[f"ch{c}"]["worst_runs"] = [{"t_s": round(float(starts[i] / sr), 2), "len": int(runs[i])} for i in idx]
    else:
        res[f"ch{c}"]["flat_runs_total"] = 0
    # ピーク分布の上位: 上位 0.01% のサンプル値が同一値に集中していないか
    top = np.sort(a)[-max(1, n // 10000):]
    res[f"ch{c}"]["top0.01pct_min_dbfs"] = round(20 * np.log10(top.min() + 1e-12), 3)
    res[f"ch{c}"]["top0.01pct_unique_ratio"] = round(float(len(np.unique(top)) / len(top)), 4)
    # クレストファクター（発話区間のみ: 1秒RMSが上位30%の区間）
    sec = np.array([np.sqrt(np.mean(s[i * sr:(i + 1) * sr] ** 2)) for i in range(n // sr)])
    loud = np.argsort(sec)[-int(len(sec) * 0.3):]
    cf = []
    for i in loud:
        seg = s[i * sr:(i + 1) * sr]
        r = np.sqrt(np.mean(seg ** 2)) + 1e-12
        cf.append(20 * np.log10(np.abs(seg).max() / r))
    res[f"ch{c}"]["crest_factor_db_median_loud"] = round(float(np.median(cf)), 2)
    res[f"ch{c}"]["sec_rms_p95_dbfs"] = round(float(20 * np.log10(np.percentile(sec, 95) + 1e-12)), 2)
    res[f"ch{c}"]["sec_rms_p50_dbfs"] = round(float(20 * np.log10(np.percentile(sec, 50) + 1e-12)), 2)
print(json.dumps(res, ensure_ascii=False, indent=1, default=float))
