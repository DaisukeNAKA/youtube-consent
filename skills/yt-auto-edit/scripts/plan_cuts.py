#!/usr/bin/env python3.11
"""plan_cuts.py --transcript transcript.json [--audio file] --settings settings.json --out cuts_auto.json
無音区間（単語ギャップ ∪ ffmpeg silencedetect）→ 無音 > threshold を silence_keep 秒に詰める keep_auto、
フィラー候補、言い直し候補 を SPEC 3.4 形式で出す。エージェント(LLM)はこれを読んで edit_plan.json を確定する。"""
import argparse, os, sys, re, difflib, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, save_json, load_settings, FFMPEG, probe_media
from jatext import detect_fillers, token_core, zen2han


def flat_words(tr):
    ws = []
    for seg in tr.get("segments", []):
        if seg.get("words"):
            for w in seg["words"]:
                ws.append({"w": w["w"], "s": float(w["s"]), "e": float(w["e"]), "seg": seg})
        else:
            ws.append({"w": seg["text"], "s": float(seg["start"]), "e": float(seg["end"]), "seg": seg})
    ws.sort(key=lambda x: x["s"])
    return ws


def silencedetect(path, noise_db=-35, min_d=0.3):
    cmd = [FFMPEG, "-v", "info", "-nostats", "-i", path, "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_d}", "-f", "null", "-"]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start:\s*([\d.\-]+)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end:\s*([\d.\-]+)", line)
        if m and start is not None:
            out.append({"start": max(0.0, start), "end": float(m.group(1))})
            start = None
    if start is not None:
        out.append({"start": start, "end": None})
    return out


def mean_volume(path):
    r = subprocess.run([FFMPEG, "-v", "info", "-nostats", "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    m = re.search(r"mean_volume:\s*([\-\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None


def merge_intervals(iv, min_gap=0.0):
    iv = sorted([(a, b) for a, b in iv if b > a])
    out = []
    for a, b in iv:
        if out and a <= out[-1][1] + min_gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def main():
    ap = argparse.ArgumentParser(description="無音/フィラー/言い直しの候補検出と keep_auto 生成")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--audio", default=None, help="silencedetect に使う音声/動画（省略時は transcript.audio）")
    ap.add_argument("--settings", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--noise-db", default="auto", help="silencedetect の閾値dB。auto=平均音量-15dB（-45〜-28に制限）")
    ap.add_argument("--duration", type=float, default=None, help="素材の長さ（省略時 ffprobe）")
    a = ap.parse_args()

    st = load_settings(a.settings)
    thr = float(st["cuts"]["silence_threshold"])
    keep_sil = float(st["cuts"]["silence_keep"])
    tr = load_json(a.transcript)
    words = flat_words(tr)
    audio = a.audio or tr.get("audio")
    dur = a.duration
    if dur is None and audio and os.path.exists(audio):
        dur = probe_media(audio)["duration"]
    if dur is None:
        dur = max((w["e"] for w in words), default=0.0)

    # 1) 無音: 単語ギャップ(>=0.3s) ∪ silencedetect
    gaps = []
    if words:
        if words[0]["s"] > 0.3:
            gaps.append((0.0, words[0]["s"]))
        for p, n in zip(words, words[1:]):
            if n["s"] - p["e"] >= 0.3:
                gaps.append((p["e"], n["s"]))
        if dur - words[-1]["e"] > 0.3:
            gaps.append((words[-1]["e"], dur))
    sd = []
    if audio and os.path.exists(audio):
        noise = a.noise_db
        if str(noise) == "auto":
            mv = mean_volume(audio)
            noise = -35.0 if mv is None else max(-45.0, min(-28.0, mv - 15.0))
        noise = float(noise)
        print(f"[plan_cuts] silencedetect noise={noise:.1f}dB", file=sys.stderr)
        sd = [(s["start"], s["end"] if s["end"] is not None else dur) for s in silencedetect(audio, noise)]
    # 音声区間（silencedetectで無音でない所）には発話があるとみなす → 単語ギャップは silencedetect と交差した部分だけ採用
    silences = []
    if sd:
        for g0, g1 in gaps:
            for s0, s1 in sd:
                lo, hi = max(g0, s0), min(g1, s1)
                if hi - lo > 0.05:
                    silences.append((lo, hi))
        # 発話が検出されていない長い silencedetect 区間もそのまま採用（Whisperが落とした無音）
        for s0, s1 in sd:
            if s1 - s0 >= thr:
                silences.append((s0, s1))
    else:
        silences = gaps
    silences = merge_intervals(silences)

    # 2) keep_auto: 無音 > thr を keep_sil 秒に詰める（前後 keep_sil/2 ずつ残す）
    half = keep_sil / 2.0
    cuts = []
    for s0, s1 in silences:
        if s1 - s0 > thr:
            c0 = 0.0 if s0 <= 0.01 else s0 + half           # 冒頭の無音は頭から落とす
            c1 = dur if s1 >= dur - 0.01 else s1 - half     # 末尾の無音は最後まで落とす
            if c1 - c0 > 0.05:
                cuts.append((c0, c1))
    cuts = merge_intervals(cuts)
    keep, cur = [], 0.0
    for c0, c1 in cuts:
        if c0 - cur > 0.1:
            keep.append({"src_start": round(cur, 3), "src_end": round(c0, 3)})
        cur = max(cur, c1)
    if dur - cur > 0.1:
        keep.append({"src_start": round(cur, 3), "src_end": round(dur, 3)})

    # 3) フィラー候補: セグメント先頭 or ポーズ(>=0.4s)直後のフィラー語（jatext.detect_fillers）
    fillers = [{"start": f["start"], "end": f["end"], "text": f["text"]} for f in detect_fillers(tr.get("segments", []))]

    # 4) 言い直し候補: 直後に近い文字列が繰り返される
    retakes = []
    chars = []  # (ch, s, e)
    for w in words:
        c = token_core(w["w"])
        if not c:
            continue
        n = len(c)
        for k, ch in enumerate(c):
            s = w["s"] + (w["e"] - w["s"]) * k / n
            e = w["s"] + (w["e"] - w["s"]) * (k + 1) / n
            chars.append((ch, s, e))
    N = len(chars)
    i = 0
    used_until = -1
    while i < N:
        found = None
        for n in range(12, 2, -1):
            if i + 2 * n > N:
                continue
            a_ = "".join(c[0] for c in chars[i:i + n])
            b_ = "".join(c[0] for c in chars[i + n:i + 2 * n])
            if a_ == b_ or (n >= 4 and difflib.SequenceMatcher(None, a_, b_).ratio() >= 0.85):
                # 繰り返しの間に長いポーズがあっても言い直しとみなす（<2s）
                if chars[i + n][1] - chars[i + n - 1][2] < 2.0:
                    found = n
                    break
        if found and i > used_until:
            n = found
            retakes.append({"start": round(chars[i][1], 3), "end": round(chars[i + n - 1][2], 3), "reason": "repeat",
                            "text": "".join(c[0] for c in chars[i:i + n]),
                            "repeat_text": "".join(c[0] for c in chars[i + n:i + 2 * n])})
            used_until = i + 2 * n - 1
            i += n
        else:
            i += 1
    # 同一文字の連続（「あああ」）などノイズを除く
    retakes = [r for r in retakes if len(set(r["text"])) >= 2]

    out = {"duration": round(dur, 3), "silence_threshold": thr, "silence_keep": keep_sil,
           "silences": [{"start": round(s, 3), "end": round(e, 3)} for s, e in silences],
           "keep_auto": keep,
           "filler_candidates": fillers, "retake_candidates": retakes}
    save_json(a.out, out)
    removed = dur - sum(k["src_end"] - k["src_start"] for k in keep)
    print(f"[plan_cuts] dur={dur:.2f}s silences={len(silences)} keep={len(keep)} removed={removed:.2f}s "
          f"fillers={len(fillers)} retakes={len(retakes)} -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
