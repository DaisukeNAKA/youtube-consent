#!/usr/bin/env python3
"""ユニコ15秒CM 音声生成 — 自作ジングル『ユニコ・チップポップ』＋自作SE（第三者音源・サンプル不使用）

仕様（最終絵コンテ準拠）
  120BPM（1拍=0.5秒=15フレーム, 1小節=2.0秒）/ ハ長調 / 7.5小節 = 15.0秒 / 48kHz stereo
  音は 0.00–14.50 秒、14.50–15.00 はデジタル無音（tail_silence）
  サウンドロゴ「ユ・ニ・コ」= E5–A5–G5（8分・8分・4分）を 2.0 秒と 12.0 秒に
    ※ NBCチャイム（G-E-C）と同じ音名列は使わない
  9.50–10.00 は完全無音の「間」（cues.json の music_breaks）→ 10.00 のオチ（ドン）で全編成が戻る
  声の帯域（1–4kHz）を空けたアレンジ。cues.json の voice に本人のWAVを置くと
  voice_windows の区間だけ音楽を約 -6dB（アタック50ms/リリース150ms）下げて自動ミックス

usage: python3 tools/audio.py [--fmt 916|169] [--se-only]
  cues.json の se のうち "fmt" を持つものは、その比率の書き出しにだけ入る（エンドカードBの出現が比率で違うため）
  --se-only … BGMを抜いた効果音だけの版（Shortsの自動音源運用向け）
出力: out/audio/mix_raw_<fmt>.wav（--se-only は mix_raw_<fmt>_se.wav）。ラウドネス調整は tools/master.py
"""
import argparse, json, os, wave
import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
DUR = 15.0
N = int(SR * DUR)
BPM = 120.0
BEAT = 60.0 / BPM
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
rng = np.random.default_rng(20240410)  # 結成日(2024-04-10, M-1公式)を種に固定＝毎回同じ音になる
NOTE = {n: i for i, n in enumerate(['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'])}


def nm(s):
    return 12 * (int(s[-1]) + 1) + NOTE[s[:-1]]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def lp(x, fc, o=2): return sosfilt(butter(o, fc, 'low', fs=SR, output='sos'), x)
def hp(x, fc, o=2): return sosfilt(butter(o, fc, 'high', fs=SR, output='sos'), x)
def bp(x, lo, hi, o=2): return sosfilt(butter(o, [lo, hi], 'band', fs=SR, output='sos'), x)


def adsr(n, a=.005, d=.1, s=.6, r=.08):
    e = np.zeros(n); A = min(int(a * SR), n); e[:A] = np.linspace(0, 1, A, endpoint=False)
    D = min(int(d * SR), n - A); e[A:A + D] = np.linspace(1, s, D, endpoint=False); e[A + D:] = s
    R = min(int(r * SR), n - A - D)
    if R > 0: e[n - R:] = np.linspace(e[n - R - 1], 0, R)
    return e


def place(buf, sig, t0, gain=1.0, pan=0.0, pan_to=None):
    i0 = int(round(t0 * SR))
    if i0 >= buf.shape[1] or len(sig) == 0: return
    if i0 < 0: sig = sig[-i0:]; i0 = 0
    n = min(len(sig), buf.shape[1] - i0)
    p = np.full(n, pan) if pan_to is None else np.linspace(pan, pan_to, n)   # pan_to: 鳴っている間に定位を動かす（シュッ）
    l, r = np.cos((p + 1) * np.pi / 4), np.sin((p + 1) * np.pi / 4)
    buf[0, i0:i0 + n] += sig[:n] * gain * l * 1.4142
    buf[1, i0:i0 + n] += sig[:n] * gain * r * 1.4142


# ---------------- instruments ----------------
def kick(amp=1.0):
    n = int(.42 * SR); t = np.arange(n) / SR
    s = np.sin(2 * np.pi * np.cumsum(46 + 105 * np.exp(-t / .035)) / SR) * np.exp(-t / .17)
    click = hp(rng.standard_normal(n) * np.exp(-t / .004), 2000) * .22
    return np.tanh((s + click) * 1.6) * .9 * amp


def clap():
    n = int(.26 * SR); t = np.arange(n) / SR; e = np.zeros(n)
    for k, off in enumerate([0, .011, .022]):
        i = int(off * SR); e[i:] += np.exp(-t[:n - i] / .006) * (.8 if k < 2 else 1)
    e += np.exp(-t / .08) * .3 * (t > .022)
    return bp(rng.standard_normal(n) * e, 900, 3200)


def hat(open_=False):
    n = int((.22 if open_ else .05) * SR); t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 7500, 4) * np.exp(-t / (.07 if open_ else .016)) * .42


def tri_bass(m, dur):
    n = int(dur * SR); t = np.arange(n) / SR; f = hz(m)
    ph = (t * f) % 1.0; tri = 4 * np.abs(ph - .5) - 1
    s = tri * .8 + np.sin(2 * np.pi * f * t) * .5
    return lp(s, 900) * adsr(n, .004, .1, .75, .03) * .55


def lead(m, dur, bright=1.0):
    n = int((dur + .06) * SR); t = np.arange(n) / SR
    f = hz(m) * (1 + .004 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - .12) / .2, 0, 1))
    ph = np.cumsum(f) / SR
    pulse = np.where((ph % 1.0) < .25, 1.0, -1.0) * .65 + (2 * (ph % 1.0) - 1) * .35   # 25%パルス
    return lp(pulse, 3000 * bright) * adsr(n, .006, .08, .75, .05) * .15


def marimba(m, dur=.6):
    n = int(dur * SR); t = np.arange(n) / SR; f = hz(m)
    idx = 1.6 * np.exp(-t / .02)
    s = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * 4 * t)) * np.exp(-t / .22)
    s += .25 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-t / .05)
    return s * np.clip(t / .002, 0, 1) * .22


def pad_stab(ms, dur, gain=1.0):
    n = int((dur + .2) * SR); t = np.arange(n) / SR; out = np.zeros(n)
    for m in ms:
        f = hz(m)
        out += np.sin(2 * np.pi * f * t + (1.8 * np.exp(-t / .2) + .3) * np.sin(2 * np.pi * f * t)) * adsr(n, .003, .35, .45, .18) * .13
    return out * gain


def riser(dur):
    n = int(dur * SR); t = np.arange(n) / SR; x = rng.standard_normal(n); out = np.zeros(n); seg = 480
    for i in range(0, n, seg):
        fc = 800 + 7000 * (i / n) ** 1.5
        y = bp(x[max(0, i - 256):i + seg], fc * .7, min(fc * 1.3, SR / 2 - 200)); out[i:i + seg] = y[-min(seg, n - i):]
    return out * (t / dur) ** 2 * .35


# ---------------- SE（自作4種）----------------
def se_pon(pitch=1.0, vib=False):
    """①ポン: 1320→660Hz を指数下降＋2msクリック、減衰約120ms。vib=True は8Hzビブラートの「ボヨン」"""
    n = int((.2 if vib else .14) * SR); t = np.arange(n) / SR
    f = (660 + 660 * np.exp(-t / .025)) * pitch
    if vib: f = f * (1 + .06 * np.sin(2 * np.pi * 8 * t))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (.09 if vib else .05))
    c = int(.002 * SR); s[:c] += rng.standard_normal(c) * .3
    return s * .55


def se_shu(dur=.22):
    """②シュッ: ノイズのバンドパスを500Hz→7kHzへスイープ"""
    n = int(dur * SR); t = np.arange(n) / SR; x = rng.standard_normal(n); out = np.zeros(n); seg = 240
    for i in range(0, n, seg):
        fc = 500 * (14 ** (i / n))
        y = bp(x[max(0, i - 128):i + seg], fc * .75, min(fc * 1.3, SR / 2 - 200)); out[i:i + seg] = y[-min(seg, n - i):]
    return out * np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.2 * .9


def se_don(level='strong', pitch=1.0):
    """③ドン: 110→42Hzのキック＋15msノイズ（HPF2k）、ソフトクリップ。strong/mid/weak"""
    n = int(.4 * SR); t = np.arange(n) / SR
    f = (42 + 68 * np.exp(-t / .07)) * pitch
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / .16)
    nb = hp(rng.standard_normal(n), 2000) * np.exp(-t / .006) * (t < .015)
    g = {'strong': 1.0, 'mid': .5, 'weak': .2}[level]
    return np.tanh((s + nb * .8) * (2.2 if level == 'strong' else 1.5)) * .85 * g


def se_kira():
    """④キラッ: FMベル G6–C7–E7 を30ms間隔、減衰600ms＋自作ディレイ"""
    n = int(1.0 * SR); out = np.zeros(n)
    for k, m in enumerate(['G6', 'C7', 'E7']):
        tt = np.arange(int(.7 * SR)) / SR; f = hz(nm(m))
        b = np.sin(2 * np.pi * f * tt + 2.5 * np.exp(-tt / .1) * np.sin(2 * np.pi * f * 3.5 * tt)) * np.exp(-tt / .2) * .25
        i = int(k * .03 * SR); out[i:i + len(b)] += b[:n - i]
    d = int(.12 * SR); out[d:] += out[:-d] * .35
    return out


def make_se(c):
    k = c['name']
    if k == 'pon': return se_pon(c.get('pitch', 1.0), c.get('vib', False))
    if k == 'shu': return se_shu(c.get('dur', .22))
    if k == 'don': return se_don(c.get('level', 'strong'), c.get('pitch', 1.0))
    if k == 'kira': return se_kira()
    raise ValueError(k)


# ---------------- 楽曲（絵コンテの秒割りに合わせた編曲）----------------
C_ = ['C4', 'E4', 'G4']; F_C = ['C4', 'F4', 'A4']; Am = ['A3', 'C4', 'E4']; F_ = ['F3', 'A3', 'C4']; G_ = ['G3', 'B3', 'D4']; G7 = ['G3', 'B3', 'D4', 'F4']
HARM = [  # (開始秒, 長さ秒, 和音, ベース)
    (0.0, 2.0, C_, 'C2'),
    (2.0, 1.0, C_, 'C2'), (3.0, .5, F_C, 'C2'), (3.5, .5, C_, 'C2'),
    (4.0, 1.0, Am, 'A1'), (5.0, 1.0, F_, 'F1'),
    (6.0, 1.0, F_, 'F1'), (7.0, 1.0, G_, 'G1'),
    (8.0, 1.5, G7, 'G1'),
    (10.0, 2.0, C_, 'C2'),
    (12.0, 1.0, C_, 'C2'), (13.0, .5, F_C, 'C2'), (13.5, .5, C_, 'C2'),
    (14.0, .5, C_ + ['C5'], 'C2'),
]
HARM_OCHI = 10.0
OCHI, BRK = 10.0, 9.5
LOGO = [(0.0, 'E5', .25), (.25, 'A5', .25), (.5, 'G5', .5)]          # ユ・ニ・コ
ARP = {  # マリンバの分散（主に C5 以上。声の基音より上を動かす）
    0.0: ['C5', 'E5', 'G5', 'C6'], 4.0: ['A5', 'C6', 'E6', 'C6'], 5.0: ['F5', 'A5', 'C6', 'A5'],
    6.0: ['F5', 'A5', 'C6', 'A5'], 7.0: ['G5', 'B5', 'D6', 'B5'], 8.0: ['G5', 'B5', 'D6', 'F6'],
    11.0: ['C6', 'E6', 'G6', 'C7'],
}


def silent(t, cues):
    return any(a <= t < b for a, b in cues['music_breaks']) or t >= DUR - cues.get('tail_silence', .5)


def build_music(cues, voice=False):
    global OCHI, BRK
    BRK, OCHI = cues['music_breaks'][0]      # 「間」の開始とオチ（全編成が戻る）の秒
    assert abs(OCHI - HARM_OCHI) < 1e-6, 'HARM のオチ位置と music_breaks が不一致'
    mus = np.zeros((2, N)); drm = np.zeros((2, N)); kicks = []
    for t0, d, ch, bs in HARM:
        if t0 >= 14.0:   # 締めの和音（14.0–14.5 で減衰）
            place(mus, pad_stab([nm(x) for x in ch], .5), t0, 1.2); place(mus, tri_bass(nm(bs), .5), t0, .9); continue
        if abs(t0 - OCHI) < 1e-6:   # オチ：スタブで全編成が戻る
            place(mus, pad_stab([nm(x) for x in ch + ['C5']], .4, 1.6), t0, 1.0)
        e = 0.0
        while e < d - 1e-6:
            t = t0 + e
            if not silent(t, cues):
                place(mus, tri_bass(nm(bs) + (12 if int(round(e / .25)) % 2 else 0), .22), t, .9 if t >= 2 else .5)
                if abs((e / .5) % 1 - .5) < 1e-6 and t >= 2.0:
                    place(mus, pad_stab([nm(x) for x in ch], .16), t, .9, -.2)
            e += .25
    # ドラム：1小節目はキックなし（イントロ）。2.0から全部。4.0–「間」までは声枠なのでベース＋ハイハット中心
    for i in range(int(DUR / BEAT)):
        t = i * BEAT
        if silent(t, cues): continue
        full = (2.0 <= t < 4.0) or (OCHI <= t < 14.0)
        if t >= 2.0 and (full or t == 6.0 or (4.0 <= t < BRK and i % 2 == 0)):
            place(drm, kick(1.0 if t in (2.0, 6.0, OCHI, 12.0) else .8), t, .85); kicks.append(t)
        if full and i % 2 == 1: place(drm, clap(), t, .45, .05)
        for h in (0, .5):
            th = t + h * BEAT
            if not silent(th, cues) and th < 14.0: place(drm, hat(open_=(h == .5 and i % 4 == 3)), th, .45 if h else .3, .25)
    for k in range(3): place(drm, clap(), OCHI + .125 * (k + 1), .25 + .08 * k, -.1 + .07 * k)   # フィル
    place(mus, riser(.5), 11.5, 1.0)                                                             # ライザー
    place(drm, kick(.6), 13.5, .8); place(drm, clap(), 13.5, .35)                                # 軽い再ヒット
    for t0, notes in ARP.items():
        dur = 2.0 if t0 == 0 else 1.0
        for j in range(int(dur / .25)):
            t = t0 + j * .25
            if not silent(t, cues): place(mus, marimba(nm(notes[j % 4])), t, .7 if t0 == 0 else .5, .3)
    for base in (2.0, 12.0):   # サウンドロゴ①②（E5–A5–G5）
        lg = .316 if (voice and base == 2.0) else 1.0   # 声あり版: 名乗りの声と重なる①はリードを −10dB（マリンバ主体）
        for dt, n_, ln in LOGO:
            place(mus, lead(nm(n_), ln * .95, 1.3), base + dt, 1.35 * lg, 0)
            place(mus, marimba(nm(n_) + 12, .8), base + dt, .6, 0)
    duck = np.ones(N)
    for k in kicks:
        i = int(k * SR); n = min(int(.2 * SR), N - i)
        duck[i:i + n] = np.minimum(duck[i:i + n], 1 - .3 * np.exp(-np.arange(n) / SR / .06))
    out = mus * duck + drm
    end = N - int(cues.get('tail_silence', .5) * SR); i0 = int(14.0 * SR)
    out[:, i0:end] *= np.exp(-np.linspace(0, 4.5, end - i0)); out[:, end:] = 0
    for a, b in cues['music_breaks']:   # 「間」は残響ごと完全無音（30msフェードでクリック防止）
        ia, ib = int(a * SR), int(b * SR); f = int(.03 * SR)
        out[:, ia:ia + f] *= np.linspace(1, 0, f); out[:, ia + f:ib] = 0
    return out


def load_wav(path):
    with wave.open(path) as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth(); raw = w.readframes(w.getnframes())
    dt = {2: np.int16, 4: np.int32}[sw]; x = np.frombuffer(raw, dt).astype(np.float64) / np.iinfo(dt).max
    x = x.reshape(-1, ch).mean(1)
    if sr != SR: x = np.interp(np.arange(0, len(x) / sr, 1 / SR), np.arange(len(x)) / sr, x)
    return x


def write_wav(path, st):
    pcm = (np.clip(st, -1, 1).T * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--fmt', default='916', choices=['916', '169']); ap.add_argument('--se-only', action='store_true')
    a = ap.parse_args()
    cues = json.load(open(os.path.join(ROOT, 'cues.json'), encoding='utf-8'))
    out = os.path.join(ROOT, 'out', 'audio'); os.makedirs(out, exist_ok=True)
    voice = np.zeros((2, N)); has = False
    for v in cues.get('voice', []):
        p = os.path.join(ROOT, v['file'])
        if os.path.exists(p): place(voice, load_wav(p), v['t'], v.get('gain', 1.0), v.get('pan', 0.0)); has = True
    music = build_music(cues, voice=has) * (0.0 if a.se_only else cues.get('music_gain', .55))
    se = np.zeros((2, N))
    for c in cues['se']:
        if c.get('fmt', a.fmt) != a.fmt: continue
        place(se, make_se(c), c['t'], c.get('gain', 1.0), c.get('pan', 0.0), c.get('pan_to'))
    se *= cues.get('se_gain', .8)
    if has:  # 声枠で音楽と効果音を約 -6dB（アタック50ms/リリース150ms）。打撃音が語頭を消さないように
        env = np.zeros(N)
        for w0, w1 in cues.get('voice_windows', []): env[int(w0 * SR):int(w1 * SR)] = 1
        sm = np.zeros(N); cur = 0.0
        for i in range(0, N, 240):
            k = 240 / ((.05 if env[i] > cur else .15) * SR); cur += (env[i] - cur) * min(1, k); sm[i:i + 240] = cur
        music *= 1 - .5 * sm; se *= 1 - .5 * sm
    mix = music + se + voice
    mix[:, N - int(cues.get('tail_silence', .5) * SR):] = 0
    mix = np.tanh(mix * 1.05) / 1.05
    name = f"mix_raw_{a.fmt}{'_se' if a.se_only else ''}.wav"
    write_wav(os.path.join(out, name), mix)
    print('audio written', os.path.join(out, name), 'voice' if has else 'no-voice', 'SE only' if a.se_only else '')


if __name__ == '__main__':
    main()
