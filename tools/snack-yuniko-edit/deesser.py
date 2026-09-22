#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分割帯域ディエッサー。直線位相 FIR で帯域を完全分割し、高域だけを圧縮する。
ffmpeg 内蔵の deesser は本素材に対してほとんど効かなかったため自前で実装した。"""
import numpy as np
from scipy.signal import firwin, fftconvolve


def split(s, sr, fc=5200, ntaps=1023):
    """直線位相 FIR で高域と低域に完全分割（加算すると元に戻る）。"""
    h = firwin(ntaps, fc, fs=sr, pass_zero=True)          # ローパス
    lf = fftconvolve(s, h, mode='full')[(ntaps - 1) // 2:][:len(s)]
    d = np.zeros(ntaps); d[(ntaps - 1) // 2] = 1.0        # 同じ遅延の全通過
    dl = fftconvolve(s, d, mode='full')[(ntaps - 1) // 2:][:len(s)]
    return dl - lf, lf                                     # (hf, lf)


def envelope(x, sr, atk=0.0015, rel=0.045):
    """速いアタック（窓内の最大）＋指数リリース。1億サンプルでも実用速度で動く。"""
    from scipy.ndimage import maximum_filter1d
    from scipy.signal import lfilter
    n_at = max(1, int(sr * atk))
    pk = maximum_filter1d(np.abs(x), size=n_at, mode='nearest')
    a = np.exp(-1.0 / (sr * rel))
    return lfilter([1 - a], [1.0, -a], pk)


def deess(s, sr, fc=5200, thresh_db=-30.0, ratio=4.0, knee_db=6.0, max_gr_db=12.0):
    hf, lf = split(s, sr, fc)
    env = envelope(hf, sr)
    ed = 20 * np.log10(env + 1e-12)
    over = ed - thresh_db
    # ソフトニー
    gr = np.zeros_like(over)
    m1 = over > knee_db / 2
    gr[m1] = over[m1] * (1 - 1 / ratio)
    m2 = (over > -knee_db / 2) & (~m1)
    gr[m2] = (1 - 1 / ratio) * (over[m2] + knee_db / 2) ** 2 / (2 * knee_db)
    gr = np.minimum(gr, max_gr_db)
    g = 10 ** (-gr / 20)
    return lf + hf * g, gr




def deess_ratio(s, sr, fc=5200, ratio_thresh_db=-14.0, ratio=4.0, knee_db=6.0,
                max_gr_db=10.0, gate_db=-45.0, atk=0.0015, rel=0.012):
    """比駆動ディエッサー。

    「高域の包絡 ÷ 全体の包絡」が閾値を超えたときだけ高域を圧縮する。
    母音の大声では作動せず、歯擦音のフレームだけを捉える。
    """
    hf, lf = split(s, sr, fc)
    he = envelope(hf, sr, atk, rel)
    te = envelope(s, sr, atk, rel)
    rd = 20 * np.log10(he + 1e-12) - 20 * np.log10(te + 1e-12)
    over = rd - ratio_thresh_db
    gr = np.zeros_like(over)
    m1 = over > knee_db / 2
    gr[m1] = over[m1] * (1 - 1 / ratio)
    m2 = (over > -knee_db / 2) & (~m1)
    gr[m2] = (1 - 1 / ratio) * (over[m2] + knee_db / 2) ** 2 / (2 * knee_db)
    gr = np.minimum(gr, max_gr_db)
    gr[20 * np.log10(te + 1e-12) < gate_db] = 0.0          # 無音では何もしない
    return lf + hf * 10 ** (-gr / 20), gr
