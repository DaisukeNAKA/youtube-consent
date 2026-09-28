#!/usr/bin/env python3.11
"""yt-auto-edit 共通ユーティリティ（settings 既定値、ffprobe/ffmpeg ラッパ）"""
import json, os, subprocess, sys, copy

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")

DEFAULT_SETTINGS = {
    # v2: 反証レビュー＋試作1回目の所見を反映（SPEC v1 からの差分は各行の # v2 コメント参照）。
    # 旧 settings.json（v1 キーのみ）でも deep_merge で下記既定が補われ、そのまま動く。
    "version": "v2", "resolution": "1080p", "fps": 30,
    "caption": {"font": "Noto Sans JP", "weight": 900,
                "size_ratio": 0.048,      # v2: 0.052 → 0.048
                "bottom_ratio": 0.069,    # v2: 0.068 → 0.069
                "color": "#FFFFFF",
                "style": "shadow",        # v2 A4: "shadow"(縁取りなし+ドロップシャドウ, 既定) | "outline"(黒縁 stroke_ratio + 影)
                "stroke_color": "#000000", "stroke_ratio": 0.004,  # outline 時のみ使う
                "shadow": True, "shadow_offset_px": 2, "shadow_blur_px": 5, "shadow_color": "rgba(0,0,0,0.5)",
                "max_chars": 18,
                "min_dur": 0.6,           # v2: 0.8 → 0.6
                "max_dur": 4.0, "gap_fill": 0.6, "punctuation": False,
                "segment_break_gap": 0.15, "drop_backchannel": True,
                "no_fill_over_dropped": True},  # v2 B2: 落とした語（フィラー/相槌/mute）の帯には gap_fill で伸ばさない
    "heading": {"position": "top-left", "shape": "skew",
                "skew_deg": -8.5,         # v2 A3: -12 → -8.5。帯コンテナごと skewX（文字も傾く擬似斜体）
                "band_color": "#FFFFFF",
                "text_color": "#182028",  # v2 A3
                "size_ratio": 0.041, "band_height_ratio": 0.083,
                "margin_x_ratio": 0.045, "margin_y_ratio": 0.055,
                "pad_x_ratio": 0.019, "pad_y_ratio": 0.02,   # 互換用（px 指定が優先）
                "pad_x_px": 32, "pad_y_px": 20,               # v2 A3: 1080p 基準 px
                "anim": "slide", "anim_in": 0.25, "anim_out": 0.0,  # v2 A3: イン=左からスライド 0.25s、アウト=即消え
                "show_during_screen": True,                   # v2 A3: 画面収録中も表示
                "rounded_radius_px": 20, "rounded_text_color": "#000000", "rounded_anim": "none"},  # shape="rounded" 用
    "wipe": {"position": "bottom-left",   # v2 A1: 既定=左下（Brain 文言は右下だが実動画は左下）
             "size": "standard",
             "diameter_ratio": 0.22,      # v2 A1: 0.20 → 0.22（直径 = H×0.22）
             "small_ratio": 0.16,         # v2 A1: 0.15 → 0.16
             "center_x_ratio": 0.085, "center_y_ratio": 0.72,  # v2 A1: 円中心 (W×0.085, H×0.72)。左右/上下は position で鏡映
             "fade": 0.2,                 # v2 A1: 表示開始時 0.2s フェードイン
             "margin_ratio": 0.04, "border": False, "focus": {"x": 0.5, "y": 0.35}},
    "screen": {"layout": "inset", "bg": "#101627",
               "preset": "author",        # v2 A2: "author"(既定) | "takkatw"
               "presets": {
                   "author": {"width_ratio": 0.875, "top_ratio": 0.028, "left_ratio": 0.092, "align": "left", "radius_px": 12, "bg": "#101627"},
                   "takkatw": {"width_ratio": 0.743, "top_px": 40, "align": "center", "radius_px": 0, "bg": "#101627"}},
               "width_ratio": 0.875, "top_ratio": 0.028, "left_ratio": 0.092, "radius_ratio": 0.011},  # 互換用（preset が優先）
    "vertical_source": {"background": "navy",  # v2 A7: 既定 "navy"(#101627)。"blur" は代替
                        "color": "#101627", "blur_px": 40, "dim": 0.35},
    "broll": {"style": "frosted-card", "speaker_width_ratio": 0.40, "card_radius_ratio": 0.028,
              "zoom_to": 1.06,            # v2 A5: 拡大は kind=photo のみ
              "zoom_kinds": ["photo"],
              "vertical_center_x_ratio": 0.70, "vertical_center_y_ratio": 0.51, "vertical_max_h_ratio": 0.62, "vertical_radius_px": 30, "vertical_shadow": True,  # v2 A5
              "transition": "dissolve", "duration": 0.33,  # v2 A6: レイアウト全体のディゾルブ 0.33s (10f@30)
              "fade": 0.25, "glass_white": 0.70, "blur_px": 40},
    "cuts": {"silence_threshold": 1.0, "silence_keep": 0.5, "remove_fillers": True},
    "audio": {"lufs": -14, "tp": -1, "lra": 11,
              "tp_headroom": 0.0},        # loudnorm の TP 目標を tp-headroom に下げる（AAC の峰の超過対策。0=従来どおり）
    "qc": {"sync_tolerance": 0.04,        # v2 C3: |口元同期ずれ| > 0.04s で警告
           "sync_window": 5.0, "sync_max_lag": 1.0, "sync_min_score": 0.25,
           "lufs_tolerance": 1.0, "tp_max": -1.0,
           "tp_tolerance": 0.1,           # AAC 符号化の峰超過/再測定誤差の許容（TP ≤ tp_max + tp_tolerance で合格）
           "use_lra": False},             # v2 C3: LRA は合否に使わない
    "srt": {"source": "transcript",       # v2 B1: SRT は補正後 transcript の文単位（句読点・冗長語あり）から別生成
            "max_chars": 40, "min_dur": 0.5, "max_dur": 8.0, "apply_caption_mute": False},
    "output": {"codec": "libx264", "crf": 18, "preset": "medium", "audio_bitrate": "192k",
               "final_name": "YouTube_本編_{res}.mp4"},  # v2 C1: {res} は 1080p / 4K
}


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(path):
    """settings.json を読み、既定値とマージして返す。path が None/存在しない場合は既定値。"""
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return deep_merge(DEFAULT_SETTINGS, json.load(f))
    return copy.deepcopy(DEFAULT_SETTINGS)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def run(cmd, check=True, capture=False, quiet=True):
    if not quiet:
        print("$", " ".join(str(c) for c in cmd), file=sys.stderr)
    r = subprocess.run([str(c) for c in cmd], check=False,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None, text=True)
    if check and r.returncode != 0:
        msg = (r.stderr or "")[-4000:] if capture else ""
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(map(str, cmd))}\n{msg}")
    return r


def ffprobe_json(path):
    r = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path], capture=True)
    return json.loads(r.stdout)


def parse_fps(s):
    try:
        n, d = s.split("/")
        n, d = float(n), float(d)
        return n / d if d else 0.0
    except Exception:
        try:
            return float(s)
        except Exception:
            return 0.0


def probe_media(path):
    """probe.py と同じ辞書を返す。"""
    info = ffprobe_json(path)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = info.get("format", {})
    dur = float(fmt.get("duration") or 0.0)
    out = {"file": os.path.abspath(path), "duration": round(dur, 3), "has_video": v is not None,
           "has_audio": a is not None, "width": 0, "height": 0, "fps": 0.0, "rotation": 0,
           "display_width": 0, "display_height": 0, "aspect": "other",
           "video_codec": v.get("codec_name") if v else None,
           "audio_codec": a.get("codec_name") if a else None,
           "sample_rate": int(a.get("sample_rate")) if a and a.get("sample_rate") else None,
           "channels": a.get("channels") if a else None}
    if v:
        w, h = int(v.get("width") or 0), int(v.get("height") or 0)
        fps = parse_fps(v.get("r_frame_rate") or "0/1") or parse_fps(v.get("avg_frame_rate") or "0/1")
        avg = parse_fps(v.get("avg_frame_rate") or "0/1")
        if avg and fps and avg < fps * 0.9:  # 可変フレームレート等: 実効値を優先
            fps = avg
        rot = 0
        tags = v.get("tags") or {}
        if tags.get("rotate"):
            try:
                rot = int(float(tags["rotate"]))
            except Exception:
                rot = 0
        for sd in v.get("side_data_list") or []:
            if "rotation" in sd:
                try:
                    rot = int(round(float(sd["rotation"])))
                except Exception:
                    pass
        rot = rot % 360
        dw, dh = (h, w) if rot in (90, 270) else (w, h)
        if v.get("nb_frames") in (None, "N/A") and dur == 0 and v.get("duration"):
            dur = float(v["duration"])
        out.update({"width": w, "height": h, "fps": round(fps, 3), "rotation": rot,
                    "display_width": dw, "display_height": dh, "aspect": classify_aspect(dw, dh),
                    "duration": round(dur, 3)})
        if v.get("duration"):
            out["video_duration"] = round(float(v["duration"]), 3)
    if a and a.get("duration"):
        out["audio_duration"] = round(float(a["duration"]), 3)
    return out


def classify_aspect(w, h):
    if not w or not h:
        return "other"
    r = w / h
    if abs(r - 16 / 9) < 0.05:
        return "16:9"
    if abs(r - 9 / 16) < 0.03:
        return "9:16"
    return "other"


def resolution_wh(settings, source_aspect="16:9"):
    res = str(settings.get("resolution", "1080p"))
    if res in ("4k", "4K", "2160p"):
        return 3840, 2160
    if res == "720p":
        return 1280, 720
    return 1920, 1080


def final_name(settings):
    """v2 C1: 完成版ファイル名。resolution が 4K なら YouTube_本編_4K.mp4、それ以外は YouTube_本編_1080p.mp4。"""
    res = str(settings.get("resolution", "1080p"))
    tag = "4K" if res in ("4k", "4K", "2160p") else ("720p" if res == "720p" else "1080p")
    tmpl = (settings.get("output") or {}).get("final_name") or "YouTube_本編_{res}.mp4"
    return tmpl.replace("{res}", tag)


def fmt_time(t):
    m, s = divmod(max(0.0, t), 60)
    h, m = divmod(int(m), 60)
    return f"{h:d}:{int(m):02d}:{s:05.2f}"
