#!/usr/bin/env python3
"""音声マスタリング: 目標 -14 LUFS（±0.5）/ トゥルーピーク -1.0 dBTP 以下 / 718,848 サンプル
- 718,848 = AAC の 1024 サンプル×702 フレーム（=14.976秒）。AAC エンコーダが先頭に 1024 サンプルの
  プライミングを足すため、ストリーム上は 703 フレーム＝14.9973秒になり、コンテナでも音声トラックの
  実尺（mdhd）でも 15.000 秒を超えない。15 秒枠の入稿で尺超過と判定されないようにするため。
  14.5 秒以降は無音なので実害はない。
- 手順: 線形ゲインで -14 LUFS へ → ルックアヘッド・リミッター（4倍オーバーサンプリング相当の
  トゥルーピーク近似）→ 再測定し、必要なら1回だけ再調整。
usage: python3 tools/master.py in.wav out.wav [--gain-from ref.wav.json]
"""
import json, os, re, subprocess, sys
import numpy as np, wave
from scipy.signal import resample_poly
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
SR, NS = 48000, 718848
TARGET_I, CEIL_TP = -14.0, -1.2


def read(path):
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), '<i2').reshape(-1, w.getnchannels()).T / 32768.0
    return x.astype(np.float64)


def write(path, x):
    pcm = (np.clip(x, -1, 1).T * 32767).round().astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def measure(path):
    e = subprocess.run([FF, '-hide_banner', '-nostats', '-i', path, '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
    s = e[e.rfind('Summary:'):]
    return float(re.search(r'I:\s+(-?[\d.]+) LUFS', s)[1]), float(re.search(r'Peak:\s+(-?[\d.]+) dBFS', s)[1])


def true_peak_env(x):
    # 各チャンネルを符号付きのまま4倍オーバーサンプリング → 絶対値（ITU-R BS.1770 の真のピーク近似）
    env = np.zeros(x.shape[1])
    for ch in x:
        up = np.abs(resample_poly(ch, 4, 1))[:4 * x.shape[1]]
        env = np.maximum(env, up.reshape(-1, 4).max(1))
    return env


def limit(x, ceil_db, look=0.0015, rel=0.06):
    c = 10 ** (ceil_db / 20)
    pk = np.maximum(true_peak_env(x), np.abs(x).max(0))
    need = np.minimum(1.0, c / np.maximum(pk, 1e-9))
    L = int(look * SR)
    # ルックアヘッド: 先読み区間の最小値をとる
    from scipy.ndimage import minimum_filter1d
    g = minimum_filter1d(need, size=2 * L + 1, origin=0)
    # リリース（指数で戻す）
    a = np.exp(-1 / (rel * SR)); out = np.empty_like(g); cur = 1.0
    for i in range(len(g)):
        cur = g[i] if g[i] < cur else a * cur + (1 - a) * g[i]
        out[i] = cur
    return x * out


def main(src, dst, fixed_gain_db=None):
    x = read(src)[:, :NS]
    if x.shape[1] < NS: x = np.pad(x, ((0, 0), (0, NS - x.shape[1])))
    tmp = dst + '.tmp.wav'; total = 0.0
    if fixed_gain_db is not None:   # 効果音だけの版: 本編と同じゲインでそろえ、トゥルーピークだけ制限する
        total = fixed_gain_db; x = limit(x * 10 ** (total / 20), CEIL_TP - .3)
    else:
        for it in range(3):
            write(tmp, x); I, TP = measure(tmp)
            g = TARGET_I - I
            if abs(g) < .25 and TP <= CEIL_TP + .05: break
            x = limit(x * 10 ** (g / 20), CEIL_TP - .3); total += g
    write(dst, x); I, TP = measure(dst)
    if os.path.exists(tmp): os.remove(tmp)
    json.dump({'gain_db': round(total, 3), 'I': I, 'TP': TP, 'samples': x.shape[1]}, open(dst + '.json', 'w'))
    print(f'mastered: I={I} LUFS, TP={TP} dBTP, gain={total:+.2f} dB, samples={x.shape[1]} ({x.shape[1] / SR:.4f}s)')


if __name__ == '__main__':
    g = None
    if len(sys.argv) > 4 and sys.argv[3] == '--gain-from':
        g = json.load(open(sys.argv[4]))['gain_db']
    main(sys.argv[1], sys.argv[2], g)
