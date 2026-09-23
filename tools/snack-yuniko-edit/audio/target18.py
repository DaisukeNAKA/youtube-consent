#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#18（e935 + P4next）の実測スペクトルを目標に、#29 の補正カーブを導く。

LTASS は「一般的な話声の平均」であって、この番組の良かった頃の音ではない。
実際 #18 は 1〜4 kHz で LTASS より 6〜10 dB 明るく、近接カーディオイドの
プレゼンスと P4next の TONE がそう作っている。目標はそちらに置く。
"""
import numpy as np, soundfile as sf, subprocess, json, sys
import evaluate as E

ANCHOR = (315, 400, 500, 630, 800, 1000)
NOISE_MARGIN = 6.0        # 補正後のノイズが #18 のノイズをこれ以上超えないようにする
MAX_BOOST, MAX_CUT = 15.0, 10.0


def spectra(path):
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    s = x.mean(axis=1).astype(np.float64)
    b = E.block_levels(s, sr)
    sp = E.third_oct_spectrum(s, sr, b >= np.percentile(b, 60))
    nz = E.third_oct_spectrum(s, sr, b <= np.percentile(b, 10))
    a = np.mean([sp[k] for k in ANCHOR])
    return {k: sp[k] - a for k in E.BANDS}, {k: nz[k] - a for k in E.BANDS}


if __name__ == "__main__":
    HP = "highpass=f=75:poles=2,bandreject=f=100:w=6"
    NR = sys.argv[1] if len(sys.argv) > 1 else "afftdn=nr=16:nf=-50"
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', 'test_src.wav', '-af',
                    f"pan=mono|c0=0.5*c0+0.5*c1,{HP},{NR}", '-c:a', 'pcm_f32le', 'src29_nr.wav'], check=True)

    t_sp, t_nz = spectra('ref18_src.wav')          # 目標
    s_sp, s_nz = spectra('src29_nr.wav')           # NR 後の #29

    print(f"{'Hz':>6} {'目標#18':>8} {'#29nr':>7} {'欲しい':>7} {'雑音余裕':>8} {'採用':>6}")
    gain = {}
    for k in E.BANDS:
        want = t_sp[k] - s_sp[k]
        head = (t_nz[k] + NOISE_MARGIN) - s_nz[k]      # ノイズ制約から許される上限
        g = float(np.clip(want, -MAX_CUT, MAX_BOOST))
        if g > 0:
            g = float(min(g, max(0.0, head)))
        gain[k] = g
        if 100 <= k <= 16000:
            print(f"{k:6} {t_sp[k]:8.1f} {s_sp[k]:7.1f} {want:7.1f} {head:8.1f} {g:6.1f}")
    json.dump({'target': t_sp, 'src': s_sp, 'gain': gain,
               'target_noise': t_nz, 'src_noise': s_nz}, open('target18.json', 'w'))
