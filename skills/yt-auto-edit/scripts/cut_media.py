#!/usr/bin/env python3.11
"""cut_media.py --plan edit_plan.json --sync sync.json --settings settings.json --workdir OUT/work [--probe probe.json] [--limit-seconds 40]
keep 区間でカメラを切り出し連結（libx264 crf18 / aac、fps は素材に追従、回転メタデータは正規化）→ cut.mp4。
別録り音声があれば offset を適用して差し替え。screen があれば同じ keep 区間（offset 適用）で screen_cut.mp4（画面が無い時間は黒）。
音声は loudnorm 2パス（I=-14 TP=-1 LRA=11）で正規化して cut.mp4 に焼く。"""
import argparse, os, sys, json, re, subprocess, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, save_json, load_settings, run, probe_media, FFMPEG


def keep_list(plan, limit=None):
    keep = sorted([(float(k["src_start"]), float(k["src_end"])) for k in plan.get("keep", []) if float(k["src_end"]) > float(k["src_start"])])
    if limit:
        out, acc = [], 0.0
        for s, e in keep:
            if acc >= limit:
                break
            d = min(e - s, limit - acc)
            out.append((s, s + d))
            acc += d
        keep = out
    return keep


def build_cut_video(camera, keep, out_path, st, audio_src=None, audio_offset=0.0, fps=None):
    """keep 区間を trim/concat で1回のエンコードで連結。音声は audio_src(offset付き) か camera 自身。"""
    o = st["output"]
    inputs = ["-i", camera]
    a_idx = 0
    if audio_src:
        inputs += ["-i", audio_src]
        a_idx = 1
    parts, labels = [], []
    for i, (s, e) in enumerate(keep):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        as_, ae = s + (audio_offset if audio_src else 0.0), e + (audio_offset if audio_src else 0.0)
        if True:
            # 音声が負時刻に食い込む場合は無音で補う
            if as_ < 0:
                pad = -as_
                parts.append(f"[{a_idx}:a]atrim=start=0:end={max(ae,0):.3f},asetpts=PTS-STARTPTS,adelay={int(pad*1000)}|{int(pad*1000)}[a{i}]")
            else:
                parts.append(f"[{a_idx}:a]atrim=start={as_:.3f}:end={ae:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(keep)}:v=1:a=1[vout][aout]"
    # 回転は ffmpeg の autorotate で映像に焼かれ、出力にはメタデータが乗らない（-metadata:s:v rotate=0 で明示）
    vf = "format=yuv420p"
    cmd = [FFMPEG, "-y", "-v", "error", "-stats"] + inputs + [
        "-filter_complex", fc + f";[vout]{vf}[vfin]", "-map", "[vfin]", "-map", "[aout]",
        "-c:v", o.get("codec", "libx264"), "-crf", str(o.get("crf", 18)), "-preset", o.get("preset", "medium"),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-metadata:s:v", "rotate=0",
        "-c:a", "aac", "-b:a", o.get("audio_bitrate", "192k"), "-ar", "48000", "-ac", "2"]
    if fps:
        cmd += ["-r", str(fps)]
    cmd += [out_path]
    run(cmd, capture=True)


def build_screen_cut(screen, keep, offset, out_path, st, fps, screen_info):
    """screen を keep(+offset) で切り出し。範囲外は黒。無音（音声なし）。"""
    o = st["output"]
    sw, sh = screen_info["display_width"], screen_info["display_height"]
    sdur = screen_info["duration"]
    parts, labels, n = [], [], 0
    for s, e in keep:
        ss, ee = s + offset, e + offset
        pieces = []
        # [ss, ee] を [0, sdur] との交差で 黒/実映像/黒 に分ける
        if ss < 0:
            pieces.append(("black", min(ee, 0.0) - ss))
        lo, hi = max(ss, 0.0), min(ee, sdur)
        if hi > lo:
            pieces.append(("real", lo, hi))
        if ee > sdur:
            pieces.append(("black", ee - max(ss, sdur)))
        for p in pieces:
            if p[0] == "black":
                if p[1] <= 0.01:
                    continue
                parts.append(f"color=c=black:s={sw}x{sh}:r={fps}:d={p[1]:.3f},format=yuv420p[v{n}]")
            else:
                parts.append(f"[0:v]trim=start={p[1]:.3f}:end={p[2]:.3f},setpts=PTS-STARTPTS,fps={fps},scale={sw}:{sh},format=yuv420p[v{n}]")
            labels.append(f"[v{n}]")
            n += 1
    if n == 0:
        return False
    fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={n}:v=1:a=0[vout]"
    cmd = [FFMPEG, "-y", "-v", "error", "-stats", "-i", screen, "-filter_complex", fc, "-map", "[vout]",
           "-c:v", o.get("codec", "libx264"), "-crf", str(o.get("crf", 18)), "-preset", o.get("preset", "medium"),
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", "-r", str(fps), out_path]
    run(cmd, capture=True)
    return True


def loudnorm_measure(path, I, TP, LRA):
    r = subprocess.run([FFMPEG, "-v", "info", "-nostats", "-i", path, "-vn",
                        "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError("loudnorm measurement failed:\n" + r.stderr[-2000:])
    return json.loads(m.group(0))


def loudnorm_apply(src, dst, st, meas):
    a = st["audio"]
    o = st["output"]
    I, TP, LRA = a.get("lufs", -14), a.get("tp", -1), a.get("lra", 11)
    # audio.tp_headroom (既定 0): AAC 符号化後の真のピークが目標を約0.1dB超えるため、必要なら目標を下げる
    TP = float(TP) - float(a.get("tp_headroom", 0.0) or 0.0)
    af = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
          f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:"
          f"linear=true:print_format=summary")
    run([FFMPEG, "-y", "-v", "error", "-stats", "-i", src, "-c:v", "copy", "-af", af, "-ar", "48000",
         "-c:a", "aac", "-b:a", o.get("audio_bitrate", "192k"), "-movflags", "+faststart", dst], capture=True)


def main():
    ap = argparse.ArgumentParser(description="keep 区間の切り出し・連結・同期・ラウドネス正規化")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--sync", default=None)
    ap.add_argument("--settings", default=None)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--camera", default=None, help="sync.json が無い場合のカメラ素材")
    ap.add_argument("--limit-seconds", type=float, default=None, help="試作用: keep 先頭からこの秒数だけ")
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--fps", default="auto", help="auto=素材に追従 / 数値で固定")
    a = ap.parse_args()

    st = load_settings(a.settings)
    plan = load_json(a.plan)
    sync = load_json(a.sync) if a.sync and os.path.exists(a.sync) else {}
    camera = a.camera or sync.get("camera")
    if not camera or not os.path.exists(camera):
        print("[cut_media] camera が見つかりません (--camera か sync.json)", file=sys.stderr)
        sys.exit(2)
    os.makedirs(a.workdir, exist_ok=True)
    keep = keep_list(plan, a.limit_seconds)
    if not keep:
        print("[cut_media] keep が空です", file=sys.stderr)
        sys.exit(2)
    cam_info = probe_media(camera)
    if a.fps == "auto":
        fps = cam_info["fps"] or float(st.get("fps", 30))
        # 29.97/59.94 等はそのまま、極端な値は settings.fps
        if not (10 <= fps <= 120):
            fps = float(st.get("fps", 30))
    else:
        fps = float(a.fps)
    audio_src = sync.get("audio") if sync.get("audio") and os.path.exists(sync.get("audio")) else None
    if not cam_info["has_audio"] and not audio_src:
        print("[cut_media] カメラに音声が無く別録り音声もありません", file=sys.stderr)
        sys.exit(2)
    total = sum(e - s for s, e in keep)
    print(f"[cut_media] keep={len(keep)} total={total:.2f}s fps={fps} audio={'external' if audio_src else 'camera'}", file=sys.stderr)

    raw = os.path.join(a.workdir, "cut_raw.mp4")
    cut = os.path.join(a.workdir, "cut.mp4")
    build_cut_video(camera, keep, raw, st, audio_src, float(sync.get("audio_offset") or 0.0), fps=None)
    meas = None
    if a.no_loudnorm:
        shutil.move(raw, cut)
    else:
        au = st["audio"]
        meas = loudnorm_measure(raw, au.get("lufs", -14), au.get("tp", -1), au.get("lra", 11))
        print(f"[cut_media] loudnorm measured I={meas['input_i']} TP={meas['input_tp']} LRA={meas['input_lra']}", file=sys.stderr)
        loudnorm_apply(raw, cut, st, meas)
        os.remove(raw)
    result = {"video": "cut.mp4", "screen": None, "keep": [{"src_start": s, "src_end": e} for s, e in keep],
              "duration": round(total, 3), "fps": fps, "loudnorm_measured": meas}

    screen = sync.get("screen") if sync.get("screen") and os.path.exists(sync.get("screen")) else None
    if screen and plan.get("screen"):
        sinfo = probe_media(screen)
        ok = build_screen_cut(screen, keep, float(sync.get("screen_offset") or 0.0),
                              os.path.join(a.workdir, "screen_cut.mp4"), st, fps, sinfo)
        if ok:
            result["screen"] = "screen_cut.mp4"
            print("[cut_media] screen_cut.mp4 ok", file=sys.stderr)
    elif screen and not plan.get("screen"):
        print("[cut_media] screen 素材はあるが plan.screen が空なので screen_cut.mp4 は作りません", file=sys.stderr)
    save_json(os.path.join(a.workdir, "cut_media.json"), result)
    out_info = probe_media(cut)
    print(f"[cut_media] cut.mp4 {out_info['duration']}s {out_info['display_width']}x{out_info['display_height']} {out_info['fps']}fps", file=sys.stderr)


if __name__ == "__main__":
    main()
