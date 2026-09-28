#!/usr/bin/env python3.11
"""sync.py --camera A [--screen B] [--audio C] --out sync.json
音声エンベロープ（100Hz RMS）の FFT 相互相関で offset を求める。
offset の定義 (SPEC 3.3): カメラ時刻 t に対応する当該ファイル時刻 = t + offset。"""
import argparse, os, sys, tempfile, subprocess
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import run, save_json, FFMPEG, probe_media

SR = 16000
ENV_HZ = 100


def load_pcm(path, max_sec=None):
    cmd = [FFMPEG, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    if max_sec:
        cmd = cmd[:3] + ["-t", str(max_sec)] + cmd[3:]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0 or len(r.stdout) == 0:
        return None
    return np.frombuffer(r.stdout, dtype=np.float32)


def envelope(x):
    hop = SR // ENV_HZ
    n = len(x) // hop
    if n == 0:
        return np.zeros(1, dtype=np.float32)
    y = x[: n * hop].reshape(n, hop)
    env = np.sqrt(np.mean(y * y, axis=1) + 1e-12)
    env = np.log1p(env * 50.0)
    env = env - env.mean()
    return env.astype(np.float32)


def xcorr_offset(ref_env, other_env, max_lag_sec=None):
    """other が ref に対してどれだけ遅れているか（秒）。lag>0: other の音は ref より後に出る。
    → ref 時刻 t に対応する other 時刻 = t + lag（other 側にリードがあれば負）。"""
    n = len(ref_env) + len(other_env)
    nfft = 1 << (n - 1).bit_length()
    R = np.fft.rfft(ref_env, nfft)
    O = np.fft.rfft(other_env, nfft)
    cc = np.fft.irfft(O * np.conj(R), nfft)  # cc[k] = sum other[i+k]*ref[i]
    lags = np.arange(nfft)
    lags[lags > nfft // 2] -= nfft
    if max_lag_sec:
        m = int(max_lag_sec * ENV_HZ)
        mask = np.abs(lags) <= m
        cc = np.where(mask, cc, -np.inf)
    k = int(np.argmax(cc))
    lag = lags[k]
    # 正規化スコア
    norm = (np.linalg.norm(ref_env) * np.linalg.norm(other_env)) or 1.0
    score = float(cc[k] / norm)
    # サブサンプル補正(放物線)
    if 0 < k < nfft - 1 and np.isfinite(cc[k - 1]) and np.isfinite(cc[k + 1]):
        y0, y1, y2 = cc[k - 1], cc[k], cc[k + 1]
        d = (y0 - y2) / (2 * (y0 - 2 * y1 + y2)) if (y0 - 2 * y1 + y2) != 0 else 0.0
        lag = lag + float(np.clip(d, -1, 1))
    return float(lag) / ENV_HZ, score


def main():
    ap = argparse.ArgumentParser(description="カメラ/画面収録/別録り音声の同期オフセット推定")
    ap.add_argument("--camera", required=True)
    ap.add_argument("--screen", default=None)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-lag", type=float, default=None, help="探索する最大ズレ秒（既定: 制限なし）")
    ap.add_argument("--max-sec", type=float, default=1800, help="解析に使う先頭秒数")
    a = ap.parse_args()

    cam = load_pcm(a.camera, a.max_sec)
    if cam is None:
        print("[sync] camera has no audio; offsets default to 0", file=sys.stderr)
    cam_env = envelope(cam) if cam is not None else None
    out = {"camera": os.path.abspath(a.camera), "screen": os.path.abspath(a.screen) if a.screen else None,
           "audio": os.path.abspath(a.audio) if a.audio else None, "screen_offset": 0.0, "audio_offset": 0.0,
           "screen_score": None, "audio_score": None, "method": f"envelope-xcorr {ENV_HZ}Hz"}
    for key in ("screen", "audio"):
        p = getattr(a, key)
        if not p:
            continue
        if cam_env is None:
            continue
        x = load_pcm(p, a.max_sec)
        if x is None or len(x) < SR:
            print(f"[sync] {key}: no audio track; offset=0 (手動で設定してください)", file=sys.stderr)
            continue
        lag, score = xcorr_offset(cam_env, envelope(x), a.max_lag)
        out[f"{key}_offset"] = round(lag, 3)
        out[f"{key}_score"] = round(score, 4)
        print(f"[sync] {key}_offset={lag:+.3f}s score={score:.3f}", file=sys.stderr)
    save_json(a.out, out)
    print(f"[sync] wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
