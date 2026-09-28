#!/usr/bin/env python3.11
"""qc.py --timeline timeline.json --video 本編.mp4 --captions captions.json --settings settings.json --out qc_report.md
       [--source camera.mp4 --plan edit_plan.json] [--cut-media cut_media.json]
字数超過/表示時間/重なり/ラウドネス/ブラックフレーム/フリーズ/A-V尺一致/字幕総数とカバー率 を Markdown で出す。
v2 C3:
- --source と --plan を渡すと、keep 各区間の中央±sync_window(5)秒（短ければ区間全体）で、出力音声(該当出力時刻)と
  素材音声のエンベロープ(100Hz RMS)の相互相関から遅延を推定し、|遅延| > qc.sync_tolerance(0.04s) を「口元同期ずれ」として警告。
  keep は cut_media.json（--limit-seconds 適用後の実際の区間）があればそれを、無ければ plan.keep を使う。
- ラウドネスは I=-14±1、TP ≤ -1.0（+qc.tp_tolerance 0.1dB: AAC 符号化の峰超過分）で判定。LRA は表示のみ（合否に使わない）。"""
import argparse, os, sys, re, json, subprocess, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, load_settings, probe_media, FFMPEG, fmt_time


def ff_stderr(args):
    r = subprocess.run([FFMPEG, "-v", "info", "-nostats"] + args + ["-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return r.stderr


def loudness(video, I, TP, LRA):
    err = ff_stderr(["-i", video, "-vn", "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    return json.loads(m.group(0)) if m else None


def blackdetect(video, min_d=0.5):
    err = ff_stderr(["-i", video, "-an", "-vf", f"blackdetect=d={min_d}:pix_th=0.10"])
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]


def freezedetect(video, min_d=5.0):
    err = ff_stderr(["-i", video, "-an", "-vf", f"freezedetect=n=0.003:d={min_d}"])
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", err)]
    out = []
    for i, s in enumerate(starts):
        out.append((s, ends[i] if i < len(ends) else None))
    return out


def load_pcm_range(path, start, dur, sr=16000):
    """path の [start, start+dur] をモノラル float32 で読む。"""
    import numpy as np
    cmd = [FFMPEG, "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{dur:.3f}", "-i", path, "-vn",
           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0 or len(r.stdout) < 4 * sr // 10:
        return None
    return np.frombuffer(r.stdout, dtype=np.float32)


def envelope_100hz(x, sr=16000, hz=100):
    """100Hz RMS エンベロープ（対数圧縮・平均除去）。sync.py と同じ定義。"""
    import numpy as np
    hop = sr // hz
    n = len(x) // hop
    if n == 0:
        return np.zeros(1, dtype=np.float32)
    y = x[: n * hop].reshape(n, hop)
    env = np.sqrt(np.mean(y * y, axis=1) + 1e-12)
    env = np.log1p(env * 50.0)
    env = env - env.mean()
    return env.astype(np.float32)


def xcorr_lag(ref, other, max_lag_s, hz=100):
    """other が ref に対してどれだけ遅れているか（秒）と正規化相関。lag>0: other(出力) の音が ref(素材) より後。"""
    import numpy as np
    m = int(round(max_lag_s * hz))
    n = min(len(ref), len(other))
    ref, other = ref[:n], other[:n]
    if n < 3 * m + 10:
        m = max(1, (n - 10) // 3)
    best = (-1e18, 0)
    scores = {}
    for lag in range(-m, m + 1):
        if lag >= 0:
            a, b = ref[: n - lag], other[lag:]
        else:
            a, b = ref[-lag:], other[: n + lag]
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        c = float(np.dot(a, b) / denom)
        scores[lag] = c
        if c > best[0]:
            best = (c, lag)
    c, lag = best
    # サブサンプル補正（放物線）
    frac = 0.0
    if (lag - 1) in scores and (lag + 1) in scores:
        y0, y1, y2 = scores[lag - 1], scores[lag], scores[lag + 1]
        d = y0 - 2 * y1 + y2
        if d != 0:
            frac = float(max(-1.0, min(1.0, (y0 - y2) / (2 * d))))
    return (lag + frac) / hz, c


def sync_check(video, source, keep, tl_dur, st, audio_offset=0.0):
    """keep 区間ごとに出力音声と素材音声のずれを推定。戻り値: [{"i","src_start","src_end","out_start","delay","score","ok"}]"""
    q = st.get("qc") or {}
    win = float(q.get("sync_window", 5.0))
    max_lag = float(q.get("sync_max_lag", 1.0))
    tol = float(q.get("sync_tolerance", 0.04))
    min_score = float(q.get("sync_min_score", 0.25))
    res = []
    o = 0.0
    for i, (s, e) in enumerate(keep):
        d = e - s
        out_s = o
        o += d
        if out_s >= tl_dur - 0.2:
            break
        d = min(d, tl_dur - out_s)
        if d < 0.5:
            continue
        # 中央±win（短ければ全体）。相関の探索余裕として素材側は前後 max_lag 広げて読む
        mid = d / 2.0
        a0 = max(0.0, mid - win)
        a1 = min(d, mid + win)
        seg_len = a1 - a0
        out_pcm = load_pcm_range(video, out_s + a0, seg_len)
        src_pcm = load_pcm_range(source, s + a0 + audio_offset - max_lag, seg_len + 2 * max_lag)
        row = {"i": i + 1, "src_start": round(s, 3), "src_end": round(e, 3), "out_start": round(out_s, 3),
               "window": [round(out_s + a0, 3), round(out_s + a1, 3)], "delay": None, "score": None, "ok": None}
        if out_pcm is None or src_pcm is None:
            row["note"] = "音声を読めません"
            res.append(row)
            continue
        oe = envelope_100hz(out_pcm)
        se = envelope_100hz(src_pcm)
        # src は max_lag 分早くから読んでいるので、out を max_lag だけ遅らせて同じ位相に揃える
        import numpy as np
        pad = int(round(max_lag * 100))
        oe2 = np.concatenate([np.zeros(pad, dtype=np.float32), oe, np.zeros(pad, dtype=np.float32)])
        n = min(len(oe2), len(se))
        lag, score = xcorr_lag(se[:n], oe2[:n], max_lag)
        row["delay"] = round(lag, 3)
        row["score"] = round(score, 3)
        row["ok"] = (abs(lag) <= tol) if score >= min_score else None
        res.append(row)
    return res


def main():
    ap = argparse.ArgumentParser(description="自動検品レポート")
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--captions", required=True)
    ap.add_argument("--settings", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-media", action="store_true", help="ffmpeg 解析（ラウドネス/黒/フリーズ）を省く")
    ap.add_argument("--source", default=None, help="v2 C3: カメラ素材（口元同期ずれチェック）")
    ap.add_argument("--plan", default=None, help="v2 C3: edit_plan.json（keep 区間）")
    ap.add_argument("--cut-media", default=None, help="cut_media.json（実際に切った keep。既定: timeline と同じ場所）")
    ap.add_argument("--sync", default=None, help="sync.json（別録り音声の offset を考慮する場合）")
    a = ap.parse_args()
    st = load_settings(a.settings)
    cap = st["caption"]
    qcfg = st.get("qc") or {}
    tl = load_json(a.timeline)
    caps = load_json(a.captions)
    cues = sorted(caps.get("cues", []), key=lambda c: c["start"])
    tl_dur = float(tl.get("duration") or tl.get("durationInFrames", 0) / max(1, tl.get("fps", 30)))
    # timeline が --limit-seconds で切られている場合は範囲内のキューだけを対象にする
    cues = [dict(c, end=min(c["end"], tl_dur)) for c in cues if c["start"] < tl_dur]
    max_chars = int(caps.get("max_chars") or cap.get("max_chars", 18))
    min_dur, max_dur = float(cap.get("min_dur", 0.8)), float(cap.get("max_dur", 4.0))
    issues, warns = [], []

    # 字幕チェック
    over = [c for c in cues if len(c["text"]) > max_chars]
    short = [c for c in cues if c["end"] - c["start"] < min_dur - 1e-3 and not (tl_dur and c["end"] >= tl_dur - 0.05)]  # 尺の末尾で切れたキューは除外
    longc = [c for c in cues if c["end"] - c["start"] > max_dur + 1e-3]
    overlap = [(p, n) for p, n in zip(cues, cues[1:]) if n["start"] < p["end"] - 1e-3]
    badhead = [c for c in cues if c["text"] and c["text"][0] in "ーんっッ々ぁぃぅぇぉゃゅょァィゥェォャュョ、。」）)"]
    punct = [c for c in cues if re.search(r"[、。！？]", c["text"])]
    fullwidth = [c for c in cues if re.search(r"[Ａ-Ｚａ-ｚ０-９]", c["text"])]
    covered = sum(min(c["end"], tl_dur) - c["start"] for c in cues if c["start"] < tl_dur)
    coverage = covered / tl_dur if tl_dur else 0.0
    for c in over:
        issues.append(f"字数超過 {len(c['text'])}>{max_chars}: {fmt_time(c['start'])} 「{c['text']}」")
    for c in short:
        issues.append(f"表示時間不足 {c['end']-c['start']:.2f}s<{min_dur}: {fmt_time(c['start'])} 「{c['text']}」")
    for c in longc:
        warns.append(f"表示時間超過 {c['end']-c['start']:.2f}s>{max_dur}: {fmt_time(c['start'])} 「{c['text']}」")
    for p, n in overlap:
        issues.append(f"字幕の重なり: {fmt_time(p['start'])}「{p['text']}」 と {fmt_time(n['start'])}「{n['text']}」")
    for c in badhead:
        warns.append(f"行頭NG文字: {fmt_time(c['start'])} 「{c['text']}」")
    for c in punct:
        warns.append(f"句読点が残っている: {fmt_time(c['start'])} 「{c['text']}」")
    for c in fullwidth:
        warns.append(f"全角英数: {fmt_time(c['start'])} 「{c['text']}」")

    # 映像/音声チェック
    media = {}
    if os.path.exists(a.video):
        info = probe_media(a.video)
        media["probe"] = info
        vd, ad = info.get("video_duration"), info.get("audio_duration")
        if vd and ad and abs(vd - ad) > 0.2:
            issues.append(f"A/V 尺不一致: video={vd}s audio={ad}s")
        if abs(info["duration"] - tl_dur) > 0.5:
            warns.append(f"timeline 長 {tl_dur:.2f}s と動画長 {info['duration']:.2f}s の差が 0.5s 超")
        if (info["display_width"], info["display_height"]) != (tl.get("width"), tl.get("height")):
            warns.append(f"解像度 {info['display_width']}x{info['display_height']} ≠ timeline {tl.get('width')}x{tl.get('height')}")
        if not a.skip_media:
            au = st["audio"]
            ln = loudness(a.video, au.get("lufs", -14), au.get("tp", -1), au.get("lra", 11))
            media["loudness"] = ln
            if ln:
                I, TP = float(ln["input_i"]), float(ln["input_tp"])
                tol_i = float(qcfg.get("lufs_tolerance", 1.0))
                tp_max = float(qcfg.get("tp_max", au.get("tp", -1.0)))
                tp_tol = float(qcfg.get("tp_tolerance", 0.1))  # AAC 符号化による峰の超過（≈0.1dB）は許容
                if abs(I - float(au.get("lufs", -14))) > tol_i:
                    issues.append(f"ラウドネス {I:.1f} LUFS（目標 {au.get('lufs')} ±{tol_i:g}）")
                if TP > tp_max + tp_tol + 1e-6:
                    issues.append(f"トゥルーピーク {TP:.2f} dBTP（上限 {tp_max:g}、許容 +{tp_tol:g}）")
                # LRA は合否に使わない（表示のみ）。qc.use_lra=true の時だけ目安超過を注意に出す
                if bool(qcfg.get("use_lra", False)) and float(ln.get("input_lra", 0)) > float(au.get("lra", 11)) + 3:
                    warns.append(f"LRA {float(ln['input_lra']):.1f} LU（目安 {au.get('lra')}）")
            bl = blackdetect(a.video)
            media["black"] = bl
            for s, e in bl:
                if e - s >= 0.5:
                    issues.append(f"ブラックフレーム {fmt_time(s)}–{fmt_time(e)} ({e-s:.2f}s)")
            fz = freezedetect(a.video)
            media["freeze"] = fz
            for s, e in fz:
                d = (e - s) if e else None
                if d is None or d >= 5.0:
                    warns.append(f"フリーズ（静止画像）{fmt_time(s)}–{fmt_time(e) if e else '末尾'}" + (f" ({d:.2f}s)" if d else ""))
    else:
        issues.append(f"動画が見つかりません: {a.video}")

    # v2 C3: 口元同期ずれ（出力音声 vs 素材音声）
    sync_rows = []
    if a.source and os.path.exists(a.video) and not a.skip_media:
        if not os.path.exists(a.source):
            warns.append(f"同期チェック: 素材が見つかりません: {a.source}")
        else:
            keep = []
            cm_path = a.cut_media or os.path.join(os.path.dirname(os.path.abspath(a.timeline)), "cut_media.json")
            if os.path.exists(cm_path):
                cm = load_json(cm_path)
                keep = [(float(k["src_start"]), float(k["src_end"])) for k in cm.get("keep") or []]
            if not keep and a.plan and os.path.exists(a.plan):
                plan = load_json(a.plan)
                keep = [(float(k["src_start"]), float(k["src_end"])) for k in plan.get("keep") or []]
            keep = sorted(k for k in keep if k[1] > k[0])
            if not keep:
                warns.append("同期チェック: keep 区間が取れません（--plan か cut_media.json）")
            else:
                audio_offset = 0.0
                if a.sync and os.path.exists(a.sync):
                    sy = load_json(a.sync)
                    # 別録り音声を使った場合、出力音声は audio 側なので camera との比較には offset を足す
                    if sy.get("audio") and os.path.abspath(sy["audio"]) == os.path.abspath(a.source):
                        audio_offset = float(sy.get("audio_offset") or 0.0)
                sync_rows = sync_check(a.video, a.source, keep, tl_dur, st, audio_offset)
                media["sync"] = sync_rows
                tol = float(qcfg.get("sync_tolerance", 0.04))
                for r in sync_rows:
                    if r.get("delay") is None:
                        warns.append(f"同期チェック不可（区間{r['i']} {fmt_time(r['out_start'])}〜）: {r.get('note', '')}")
                    elif r["ok"] is None:
                        warns.append(f"同期チェック: 相関が弱く判定不能（区間{r['i']} {fmt_time(r['out_start'])}〜, score={r['score']:.2f}, 推定 {r['delay']:+.3f}s）")
                    elif not r["ok"]:
                        warns.append(f"口元同期ずれ {r['delay']:+.3f}s（許容 ±{tol:g}s）: 区間{r['i']} 出力 {fmt_time(r['out_start'])}〜 / 素材 {fmt_time(r['src_start'])}〜{fmt_time(r['src_end'])}")

    verdict = "OK" if not issues else "要確認"
    L = [f"# 自動検品レポート ({verdict})", "",
         f"- 日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
         f"- 動画: `{a.video}`", f"- 長さ: {tl_dur:.2f}s / {tl.get('durationInFrames')} frames @ {tl.get('fps')}fps / {tl.get('width')}x{tl.get('height')}",
         f"- 字幕: {len(cues)} キュー, カバー率 {coverage*100:.1f}%, 最大 {max(len(c['text']) for c in cues) if cues else 0} 文字, "
         f"平均 {sum(len(c['text']) for c in cues)/len(cues) if cues else 0:.1f} 文字, 平均表示 {sum(c['end']-c['start'] for c in cues)/len(cues) if cues else 0:.2f}s",
         f"- 見出し: {len(tl.get('headings') or [])} 本, 画面区間: {len(tl.get('screenSegments') or [])}, Bロール: {len(tl.get('broll') or [])}", ""]
    if media.get("probe"):
        p = media["probe"]
        L += ["## 映像・音声", f"- 出力: {p['display_width']}x{p['display_height']} {p['fps']}fps {p.get('video_codec')}/{p.get('audio_codec')} "
              f"video={p.get('video_duration')}s audio={p.get('audio_duration')}s"]
        ln = media.get("loudness")
        if ln:
            L.append(f"- ラウドネス: {float(ln['input_i']):.1f} LUFS (目標 {st['audio'].get('lufs')}), TP {float(ln['input_tp']):.1f} dBTP, LRA {float(ln['input_lra']):.1f}")
        if "black" in media:
            L.append(f"- ブラックフレーム: {len(media['black'])} 区間, フリーズ: {len(media['freeze'])} 区間")
        L.append("")
    if sync_rows:
        tol = float(qcfg.get("sync_tolerance", 0.04))
        bad = [r for r in sync_rows if r.get("ok") is False]
        und = [r for r in sync_rows if r.get("ok") is None]
        L += [f"## 口元同期（出力音声 vs 素材音声, 許容 ±{tol:g}s）", "",
              f"- 検査区間 {len(sync_rows)}: ずれ {len(bad)}, 判定不能 {len(und)}, 素材: `{a.source}`", "",
              "| 区間 | 出力 | 素材 | 検査窓(出力) | 推定ずれ | 相関 | 判定 |", "|--:|--|--|--|--:|--:|--|"]
        for r in sync_rows:
            d = "-" if r.get("delay") is None else f"{r['delay']:+.3f}s"
            sc = "-" if r.get("score") is None else f"{r['score']:.2f}"
            j = "OK" if r.get("ok") else ("ずれ" if r.get("ok") is False else "判定不能")
            w = r.get("window") or [r["out_start"], r["out_start"]]
            L.append(f"| {r['i']} | {fmt_time(r['out_start'])} | {fmt_time(r['src_start'])}–{fmt_time(r['src_end'])} | "
                     f"{fmt_time(w[0])}–{fmt_time(w[1])} | {d} | {sc} | {j} |")
        L.append("")
    L += ["## 問題（要修正）"] + ([f"- {x}" for x in issues] or ["- なし"]) + ["", "## 注意（確認推奨）"] + ([f"- {x}" for x in warns] or ["- なし"]) + [""]
    L += ["## 字幕一覧（先頭30件）", "", "| # | 開始 | 終了 | 秒 | 字数 | テキスト |", "|--:|--|--|--:|--:|--|"]
    for i, c in enumerate(cues[:30], 1):
        L.append(f"| {i} | {fmt_time(c['start'])} | {fmt_time(c['end'])} | {c['end']-c['start']:.2f} | {len(c['text'])} | {c['text']} |")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"[qc] {verdict}: issues={len(issues)} warns={len(warns)} -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
