#!/usr/bin/env python3.11
"""build_timeline.py --plan edit_plan.json --captions captions.json --settings settings.json --probe probe.json --sync sync.json --out timeline.json [--limit-seconds 40]
SPEC 3.7 形式の timeline.json（Remotion inputProps）。headings/screen/broll の src 時刻を出力時刻に写像。"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, save_json, load_settings, resolution_wh
from captions import Mapper


def map_range(mapper, s, e):
    """src 区間 → 出力区間（keep 外は最寄りへ寄せる）。出力長 0 以下なら None。"""
    os_, oe = mapper.to_out(float(s)), mapper.to_out(float(e))
    if oe - os_ <= 0.02:
        return None
    return round(os_, 3), round(oe, 3)


def main():
    ap = argparse.ArgumentParser(description="Remotion 用 timeline.json を作る")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--captions", required=True)
    ap.add_argument("--settings", default=None)
    ap.add_argument("--probe", default=None)
    ap.add_argument("--sync", default=None)
    ap.add_argument("--cut-media", default=None, help="cut_media.json（fps/長さの実測。省略時は workdir 推定）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit-seconds", type=float, default=None)
    ap.add_argument("--fps", default=None, help="上書き fps（既定: settings.fps。'auto' で素材 fps を四捨五入）")
    a = ap.parse_args()

    st = load_settings(a.settings)
    plan = load_json(a.plan)
    caps = load_json(a.captions)
    probe = load_json(a.probe) if a.probe and os.path.exists(a.probe) else {}
    sync = load_json(a.sync) if a.sync and os.path.exists(a.sync) else {}
    cm_path = a.cut_media or os.path.join(os.path.dirname(os.path.abspath(a.out)), "cut_media.json")
    cm = load_json(cm_path) if os.path.exists(cm_path) else {}
    primary = probe.get("primary") or {}
    mapper = Mapper(plan.get("keep") or [])
    total = mapper.total
    if cm.get("duration"):
        total = min(total, float(cm["duration"])) if a.limit_seconds is None else total
    if a.limit_seconds:
        total = min(total, float(a.limit_seconds))

    fps_setting = a.fps or st.get("fps", 30)
    if str(fps_setting) == "auto":
        src_fps = float(primary.get("fps") or cm.get("fps") or 30)
        fps = int(round(src_fps)) if 10 <= src_fps <= 120 else 30
    else:
        fps = int(round(float(fps_setting)))
    W, H = resolution_wh(st)
    src_aspect = primary.get("aspect") or "16:9"
    if src_aspect == "other":
        src_aspect = "9:16" if (primary.get("display_height") or 0) > (primary.get("display_width") or 1) else "16:9"

    def clip(seg):
        if seg is None:
            return None
        s, e = seg
        if s >= total:
            return None
        return (s, min(e, total))

    captions = []
    for c in caps.get("cues", []):
        r = clip((float(c["start"]), float(c["end"])))
        if r:
            captions.append({"start": r[0], "end": round(r[1], 3), "text": c["text"]})
    headings = []
    for h in plan.get("headings") or []:
        r = clip(map_range(mapper, h["src_start"], h["src_end"]))
        if r:
            headings.append({"start": r[0], "end": round(r[1], 3), "text": h["text"]})
    screen_segs = []
    has_screen = bool(sync.get("screen")) and bool(cm.get("screen") or os.path.exists(os.path.join(os.path.dirname(cm_path), "screen_cut.mp4")))
    for s_ in plan.get("screen") or []:
        r = clip(map_range(mapper, s_["src_start"], s_["src_end"]))
        if r:
            screen_segs.append({"start": r[0], "end": round(r[1], 3)})
    if not has_screen:
        screen_segs = []
    broll = []
    for b in plan.get("broll") or []:
        r = clip(map_range(mapper, b["src_start"], b["src_end"]))
        if r and b.get("file"):
            f = b["file"]
            broll.append({"start": r[0], "end": round(r[1], 3), "file": f if not os.path.isabs(f) else os.path.relpath(f, os.path.dirname(os.path.abspath(a.out))),
                          "kind": b.get("kind", "photo")})
    plan_letter = str(plan.get("plan", "A")).upper()
    wipe_segs = [dict(x) for x in screen_segs] if plan_letter in ("B", "C") else []

    tl = {"fps": fps, "width": W, "height": H, "durationInFrames": int(round(total * fps)),
          "duration": round(total, 3), "plan": plan_letter,
          "video": cm.get("video") or "cut.mp4", "screen": ("screen_cut.mp4" if has_screen and screen_segs else None),
          "sourceAspect": src_aspect, "sourceFps": primary.get("fps"), "style": st,
          "captions": captions, "headings": headings, "screenSegments": screen_segs,
          "wipeSegments": wipe_segs, "broll": broll}
    save_json(a.out, tl)
    print(f"[build_timeline] {tl['durationInFrames']} frames @{fps}fps ({total:.2f}s) captions={len(captions)} headings={len(headings)} "
          f"screen={len(screen_segs)} broll={len(broll)} -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
