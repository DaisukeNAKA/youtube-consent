#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整音候補を LTASS・ノイズ・サ行・ダイナミクスの4軸で採点する。

LTASS は Byrne et al. (1994) JASA 96(4) の "universal" 長時間平均話声スペクトル
（1/3 オクターブ、総和 70 dB SPL 正規化）。絶対値ではなく「形」だけを使うため、
315〜1000 Hz の平均で基準化して比較する。
"""
import numpy as np, soundfile as sf, sys, json

LTASS = {  # Hz: dB SPL
    63: 38.6, 80: 43.5, 100: 54.4, 125: 57.7, 160: 56.8, 200: 60.2,
    250: 60.3, 315: 59.0, 400: 62.1, 500: 62.1, 630: 60.5, 800: 56.8,
    1000: 53.7, 1250: 53.0, 1600: 52.0, 2000: 48.7, 2500: 48.1,
    3150: 46.8, 4000: 45.6, 5000: 44.5, 6300: 44.3, 8000: 43.7,
    10000: 43.0, 12500: 40.2, 16000: 36.4,
}
BANDS = sorted(LTASS)
SCORE_LO, SCORE_HI = 125, 10000          # 採点対象の帯域


LONG_W = 16384                            # 2.93 Hz 分解能。125 Hz 帯でも 10 本のビンが入る


def third_oct_spectrum(s, sr, sel_mask, W=LONG_W, hop=None):
    """長い FFT で 1/3 オクターブ帯域の平均パワーを返す（dB）。

    sel_mask は短ブロック（SHORT_W）単位の真偽値。長窓の 80% 以上が
    選択ブロックで占められている位置だけを平均に使う。
    """
    hop = hop or W // 2
    win = np.hanning(W)
    acc = np.zeros(W // 2 + 1)
    n = 0
    ratio = W // SHORT_W
    for start in range(0, len(s) - W, hop):
        b0 = start // SHORT_W
        if sel_mask[b0:b0 + ratio].mean() < 0.8:
            continue
        acc += np.abs(np.fft.rfft(s[start:start + W] * win)) ** 2
        n += 1
    if n == 0:                                    # 条件を満たす窓が無ければ全体平均
        for start in range(0, len(s) - W, hop):
            acc += np.abs(np.fft.rfft(s[start:start + W] * win)) ** 2
            n += 1
    acc /= max(1, n)
    fr = np.fft.rfftfreq(W, 1 / sr)
    out = {}
    for fc in BANDS:
        lo, hi = fc / 2 ** (1 / 6), fc * 2 ** (1 / 6)
        m = (fr >= lo) & (fr < hi)
        if SCORE_LO <= fc <= SCORE_HI:
            assert m.sum() >= 3, f"band {fc} has only {m.sum()} bins at sr={sr}"
        out[fc] = 10 * np.log10(acc[m].sum() + 1e-20)
    return out


SHORT_W = 1024                            # 21.3 ms。発話/無音の判定と歯擦音の測定に使う


def block_levels(s, sr, W=SHORT_W):
    m = len(s) // W
    blk = s[:m * W].reshape(m, W)
    rms = np.sqrt((blk ** 2).mean(axis=1)) + 1e-12
    return 20 * np.log10(rms)


def evaluate(path, label):
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    s = x.mean(axis=1).astype(np.float64) if x.shape[1] > 1 else x[:, 0].astype(np.float64)
    W = SHORT_W
    blk_db = block_levels(s, sr, W)
    thr = np.percentile(blk_db, 60)
    speech_mask = blk_db >= thr
    quiet_mask = blk_db <= np.percentile(blk_db, 10)
    spf = {"W": W, "idx": np.where(speech_mask)[0]}
    qtf = {"W": W, "idx": np.where(quiet_mask)[0]}

    sp = third_oct_spectrum(s, sr, speech_mask)
    nz = third_oct_spectrum(s, sr, quiet_mask)

    # --- LTASS 乖離（315-1000 Hz で基準化）
    anchor = [315, 400, 500, 630, 800, 1000]
    off_sig = np.mean([sp[f] for f in anchor])
    off_ref = np.mean([LTASS[f] for f in anchor])
    dev = {f: round(sp[f] - off_sig - (LTASS[f] - off_ref), 2)
           for f in BANDS if SCORE_LO <= f <= SCORE_HI}
    devv = np.array(list(dev.values()))
    ltass_rms = float(np.sqrt((devv ** 2).mean()))
    ltass_max = float(np.abs(devv).max())

    # --- S/N（発話ブロック RMS の中央値 − 静寂ブロック RMS の中央値）
    speech_db = float(np.median(blk_db[spf["idx"]]))
    noise_db = float(np.median(blk_db[qtf["idx"]]))
    snr = speech_db - noise_db
    # ノイズの高域傾斜（NR のかけ過ぎ / HF ブーストでのヒス増を見る）
    nz_anchor = np.mean([nz[f] for f in (315, 400, 500, 630, 800, 1000)])
    noise_hf = float(np.mean([nz[f] for f in (4000, 5000, 6300, 8000)]) - nz_anchor)

    # --- サ行（発話フレームのうち 5-9 kHz が 1-4 kHz を上回るフレームの強さ）
    m = len(s) // W
    fr = np.fft.rfftfreq(W, 1 / sr)
    b_sib = (fr >= 5000) & (fr < 9000)
    b_voc = (fr >= 1000) & (fr < 4000)
    win = np.hanning(W)
    ratios = []
    for k in spf["idx"]:
        seg = s[k * W:(k + 1) * W]
        if len(seg) < W:
            continue
        P = np.abs(np.fft.rfft(seg * win)) ** 2
        ratios.append(10 * np.log10((P[b_sib].sum() + 1e-20) / (P[b_voc].sum() + 1e-20)))
    ratios = np.array(ratios)
    sib_p99 = float(np.percentile(ratios, 99))
    sib_med = float(np.median(ratios))

    # --- ダイナミクス（400ms ブロックのクレスト、発話部のレベル分布幅）
    W2 = int(sr * 0.4)
    m2 = len(s) // W2
    b2 = s[:m2 * W2].reshape(m2, W2)
    r2 = 20 * np.log10(np.sqrt((b2 ** 2).mean(axis=1)) + 1e-12)
    p2 = 20 * np.log10(np.abs(b2).max(axis=1) + 1e-12)
    sel = r2 > np.percentile(r2, 60)
    crest = float(np.median(p2[sel] - r2[sel]))
    spread = float(np.percentile(r2[sel], 95) - np.percentile(r2[sel], 5))

    peak = float(20 * np.log10(np.abs(s).max() + 1e-12))

    return {
        "label": label, "file": path,
        "ltass_dev_rms_db": round(ltass_rms, 2),
        "ltass_dev_max_db": round(ltass_max, 2),
        "ltass_dev": dev,
        "snr_db": round(snr, 1),
        "noise_hf_tilt_db": round(noise_hf, 1),
        "sibilance_med_db": round(sib_med, 1),
        "sibilance_p99_db": round(sib_p99, 1),
        "crest_db": round(crest, 1),
        "level_spread_db": round(spread, 1),
        "peak_dbfs": round(peak, 2),
    }


if __name__ == "__main__":
    out = [evaluate(p, p.split("/")[-1].replace(".wav", "")) for p in sys.argv[1:]]
    print(json.dumps(out, ensure_ascii=False, indent=1))
