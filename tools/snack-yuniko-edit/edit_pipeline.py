#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スナックゆに子 本編編集パイプライン（ffmpeg ベース）

入力: 収録原本(MP4) + 編集プラン(JSON) + SE/ED 音源
出力: 1920x1080/30fps/H.264 + AAC 48kHz の完パケ、QA レポート

編集プラン JSON の構造:
{
  "source": "raw.MP4",
  "trim_start": 12.0,                 # 使用開始（原本秒）
  "trim_end": 2900.0,                 # 本編（会話）終了（原本秒）
  "tail_seconds": 10.0,               # trim_end 以降、ED として引っ張る映像の長さ（原本の続きを使用）
  "cuts": [[1520.4, 1544.8]],         # 除去区間（原本秒）
  "themes": [{"source_start": 12.0, "title": "オープニング"}, ...],
  "label": "スナックゆに子 #29",
  "se": [{"file": "doorbell.wav", "source_time": 12.0, "gain_db": -6}],
  "ed": {"music": "hotaru-piano.wav", "music_start_source": 2880.0,
         "music_gain_db": -10, "fade_audio_seconds": 5, "fade_video_seconds": 3,
         "music_offset_seconds": 0.0},
  "dialogue": {"target_lufs": -12.0, "true_peak": -1.0, "lra": 9,
               "denoise": {"nr": 12, "nf": -40}},
  "video": {"crf": 19, "preset": "medium"}
}
"""
import argparse
import json
import math
import os
import shlex
import subprocess
import sys
from pathlib import Path

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")


def run(cmd, **kw):
    print("+", " ".join(shlex.quote(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def probe(path):
    out = subprocess.check_output([
        FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)
    ])
    return json.loads(out)


def duration_of(path):
    return float(probe(path)["format"]["duration"])


# ---------------------------------------------------------------------------
# 原本秒 → 出力秒 の写像（カット区間を除去した後のタイムライン）
# ---------------------------------------------------------------------------
class Timeline:
    def __init__(self, trim_start, trim_end, cuts, tail_seconds):
        self.trim_start = float(trim_start)
        self.trim_end = float(trim_end)
        self.tail = float(tail_seconds)
        # 使用区間（原本秒）の列。cuts は除去区間。
        keep = []
        cur = self.trim_start
        for cs, ce in sorted(cuts):
            cs, ce = float(cs), float(ce)
            if ce <= cur:
                continue
            if cs > cur:
                keep.append([cur, min(cs, self.trim_end + self.tail)])
            cur = max(cur, ce)
        end_all = self.trim_end + self.tail
        if cur < end_all:
            keep.append([cur, end_all])
        self.keep = [k for k in keep if k[1] - k[0] > 0.01]
        # 出力側の各区間の開始
        self.out_starts = []
        t = 0.0
        for a, b in self.keep:
            self.out_starts.append(t)
            t += (b - a)
        self.out_duration = t

    def src_to_out(self, s):
        s = float(s)
        for (a, b), o in zip(self.keep, self.out_starts):
            if a <= s <= b:
                return o + (s - a)
            if s < a:
                # カット区間内 → 直後の使用区間の頭に丸める
                return o
        return self.out_duration

    def out_talk_end(self):
        return self.src_to_out(self.trim_end)


# ---------------------------------------------------------------------------
# 1) 台詞トラックの整音（全編）
# ---------------------------------------------------------------------------
def measure_loudness(path):
    """ebur128 で integrated / true peak / LRA を実測"""
    cmd = [FFMPEG, "-hide_banner", "-nostats", "-i", str(path),
           "-af", "ebur128=peak=true", "-f", "null", "-"]
    p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    txt = p.stderr
    res = {}
    tail = txt[txt.rfind("Summary:"):] if "Summary:" in txt else txt
    for line in tail.splitlines():
        line = line.strip()
        if line.startswith("I:"):
            res["integrated_lufs"] = float(line.split()[1])
        elif line.startswith("LRA:"):
            res["lra"] = float(line.split()[1])
        elif line.startswith("Peak:") and "true_peak_dbtp" not in res:
            res["true_peak_dbtp"] = float(line.split()[1])
    return res


def process_dialogue(src, out_wav, cfg, workdir):
    """原本の音声を抽出し、ノイズ処理→整音→ラウドネス正規化した WAV を作る。"""
    d = cfg.get("dialogue", {})
    target_i = float(d.get("target_lufs", -12.0))
    target_tp = float(d.get("true_peak", -1.0))
    target_lra = float(d.get("lra", 9))
    dn = d.get("denoise", {})
    nr = float(dn.get("nr", 12))
    nf = float(dn.get("nf", -40))
    highpass = float(d.get("highpass_hz", 80))
    lowpass = float(d.get("lowpass_hz", 16000))
    extra = d.get("extra_filters", "")

    raw_wav = Path(workdir) / "dialogue_raw.wav"
    run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn",
         "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(raw_wav)])
    before = measure_loudness(raw_wav)
    print("dialogue raw:", before)

    # ノイズ処理・整音チェーン
    chain = [f"highpass=f={highpass}:poles=2"]
    for hz in d.get("notch_hz", []):                  # 電源ハム等の狭帯域ノッチ
        chain.append(f"bandreject=f={hz}:w=6")
    chain += [
        f"lowpass=f={lowpass}",
        f"afftdn=nr={nr}:nf={nf}:tn=1:tr=1",          # FFT デノイズ（ノイズフロア追従）
        "deesser=i=0.4:m=0.5:f=0.5",                  # 歯擦音の抑制
        "acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120:makeup=2:knee=4",
        "equalizer=f=250:t=q:w=1.2:g=-1.5",           # こもりを軽く抑える
        "equalizer=f=3000:t=q:w=1.0:g=1.5",           # 明瞭度
    ]
    if extra:
        chain.append(extra)
    if d.get("downmix_mono", False):
        # 2本のラベリアマイクが L/R に分かれた収録 → 各ch を処理した後にモノラル合成（両耳センター）
        chain.append("pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1")
    stage1 = Path(workdir) / "dialogue_stage1.wav"
    run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_wav),
         "-af", ",".join(chain), "-c:a", "pcm_s16le", str(stage1)])

    # 2 パス loudnorm（linear=true で実測値を渡す）
    p = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(stage1), "-af",
                        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
                        "-f", "null", "-"], stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    js = p.stderr[p.stderr.rfind("{"):]
    m = json.loads(js[:js.rfind("}") + 1])
    ln = (f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
          f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=summary")
    run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(stage1),
         "-af", f"{ln},alimiter=limit={10 ** (target_tp / 20):.4f}:attack=5:release=50:level=false",
         "-ar", "48000", "-c:a", "pcm_s16le", str(out_wav)])
    after = measure_loudness(out_wav)
    print("dialogue processed:", after)
    return {"before": before, "after": after, "loudnorm_measured": m, "chain": chain}


# ---------------------------------------------------------------------------
# 2) テーマ表示（ASS を生成して libass で焼き込む。drawtext 非搭載ビルドでも動く）
# ---------------------------------------------------------------------------
def ass_time(t):
    t = max(0.0, float(t))
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_color(rgb_hex, alpha=0):
    """'0xRRGGBB' → '&HAABBGGRR'"""
    v = rgb_hex.lower().replace("0x", "").replace("#", "")
    rr, gg, bb = v[0:2], v[2:4], v[4:6]
    return f"&H{alpha:02X}{bb}{gg}{rr}".upper().replace("&H", "&H")


def ass_escape(s):
    return s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", " ")


def build_theme_ass(cfg, tl, fonts, out_path):
    """左上に『番組ラベル』と『トークテーマ』を常時表示する ASS を書き出す。"""
    st = cfg.get("style", {})
    fontname = st.get("fontname", "BIZ UDGothic")
    x0 = int(st.get("x", 48)); y0 = int(st.get("y", 40))
    label = cfg.get("label", "")
    label_size = int(st.get("label_size", 30))
    theme_size = int(st.get("theme_size", 46))
    purple = st.get("purple", "0x3A0F5C")
    purple_alpha = int(round((1 - float(st.get("purple_alpha", 0.86))) * 255))
    pink = st.get("pink", "0xFF2D95")
    yellow = st.get("yellow", "0xFFD400")
    outline = st.get("outline", "0x24063A")
    pad = int(st.get("pad", 14))
    bar_w = int(st.get("bar_w", 12))

    lines = []
    lines.append("[Script Info]")
    lines.append("ScriptType: v4.00+")
    lines.append("PlayResX: 1920")
    lines.append("PlayResY: 1080")
    lines.append("WrapStyle: 2")
    lines.append("ScaledBorderAndShadow: yes")
    lines.append("")
    lines.append("[V4+ Styles]")
    lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    # 箱（BorderStyle=3: OutlineColour で不透明箱、文字は透明）
    lines.append(f"Style: ThemeBox,{fontname},{theme_size},{ass_color(purple, 255)},{ass_color(purple, 255)},{ass_color(purple, purple_alpha)},{ass_color(purple, 255)},-1,0,0,0,100,100,0,0,3,{pad},0,7,0,0,0,1")
    lines.append(f"Style: ThemeText,{fontname},{theme_size},{ass_color('0xFFFFFF')},{ass_color('0xFFFFFF')},{ass_color(outline)},{ass_color(outline, 255)},-1,0,0,0,100,100,0,0,1,3,0,7,0,0,0,1")
    lines.append(f"Style: LabelBox,{fontname},{label_size},{ass_color(purple, 255)},{ass_color(purple, 255)},{ass_color(purple, purple_alpha)},{ass_color(purple, 255)},-1,0,0,0,100,100,0,0,3,{max(6, pad - 6)},0,7,0,0,0,1")
    lines.append(f"Style: LabelText,{fontname},{label_size},{ass_color(yellow)},{ass_color(yellow)},{ass_color(outline)},{ass_color(outline, 255)},-1,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1")
    lines.append(f"Style: Bar,{fontname},20,{ass_color(pink)},{ass_color(pink)},{ass_color(pink)},{ass_color(pink)},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1")
    lines.append("")
    lines.append("[Events]")
    lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    total_end = tl.out_duration + 1.0
    theme_y = y0
    if label:
        lx = x0 + bar_w + pad
        lines.append(f"Dialogue: 0,{ass_time(0)},{ass_time(total_end)},LabelBox,,0,0,0,,{{\\an7\\pos({lx},{y0})}}{ass_escape(label)}")
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(total_end)},LabelText,,0,0,0,,{{\\an7\\pos({lx},{y0})}}{ass_escape(label)}")
        theme_y = y0 + label_size + max(6, pad - 6) * 2 + 10

    themes = cfg.get("themes", [])
    out_times = []
    tx = x0 + bar_w + pad
    bar_h = theme_size + pad * 2
    for i, th in enumerate(themes):
        s_out = tl.src_to_out(th["source_start"])
        e_out = tl.src_to_out(themes[i + 1]["source_start"]) if i + 1 < len(themes) else total_end
        out_times.append({"title": th["title"], "start": round(s_out, 2), "end": round(min(e_out, tl.out_duration), 2),
                          "source_start": th["source_start"]})
        if e_out <= s_out:
            continue
        t = ass_escape(th["title"])
        # ピンクのアクセントバー（ASS 図形）
        lines.append(f"Dialogue: 0,{ass_time(s_out)},{ass_time(e_out)},Bar,,0,0,0,,{{\\an7\\pos({x0},{theme_y - pad})\\p1}}m 0 0 l {bar_w} 0 l {bar_w} {bar_h} l 0 {bar_h}{{\\p0}}")
        lines.append(f"Dialogue: 0,{ass_time(s_out)},{ass_time(e_out)},ThemeBox,,0,0,0,,{{\\an7\\pos({tx},{theme_y})}}{t}")
        lines.append(f"Dialogue: 1,{ass_time(s_out)},{ass_time(e_out)},ThemeText,,0,0,0,,{{\\an7\\pos({tx},{theme_y})}}{t}")
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_times


# ---------------------------------------------------------------------------
# 3) レンダリング
# ---------------------------------------------------------------------------
def render(cfg, plan_dir, workdir, outpath, fonts, dialogue_wav, dry_run=False):
    src = Path(cfg["source"])
    if not src.is_absolute():
        src = plan_dir / src
    se_dir = Path(cfg.get("se_dir", plan_dir))
    tl = Timeline(cfg["trim_start"], cfg["trim_end"], cfg.get("cuts", []), cfg.get("tail_seconds", 0))
    vcfg = cfg.get("video", {})
    fps = int(vcfg.get("fps", 30))
    width, height = int(vcfg.get("width", 1920)), int(vcfg.get("height", 1080))

    # 映像は最初の使用区間の少し手前から入力シーク（先頭からの全デコードを避ける）
    in_off = max(0.0, tl.keep[0][0] - 2.0)
    inputs = ["-ss", f"{in_off:.3f}", "-i", str(src), "-i", str(dialogue_wav)]
    fc = []
    # --- 映像・台詞の区間切り出し（trim / atrim → concat）
    vparts, aparts = [], []
    for i, (a, b) in enumerate(tl.keep):
        fc.append(f"[0:v]trim=start={a - in_off:.3f}:end={b - in_off:.3f},setpts=PTS-STARTPTS[v{i}]")
        seg_len = b - a
        fc.append(f"[1:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                  f"afade=t=in:st=0:d=0.02,afade=t=out:st={max(0.0, seg_len - 0.02):.3f}:d=0.02[a{i}]")
        vparts.append(f"[v{i}]")
        aparts.append(f"[a{i}]")
    n = len(tl.keep)
    if n > 1:
        fc.append("".join(vparts) + f"concat=n={n}:v=1:a=0[vcat]")
        fc.append("".join(aparts) + f"concat=n={n}:v=0:a=1[acat]")
    else:
        fc.append("[v0]null[vcat]")
        fc.append("[a0]anull[acat]")

    # --- SE / ED の入力とディレイ
    mix_inputs = ["[acat]"]
    idx = 2
    se_log = []
    for se in cfg.get("se", []):
        p = se_dir / se["file"]
        t_out = tl.src_to_out(se["source_time"]) + float(se.get("offset_seconds", 0))
        gain = float(se.get("gain_db", -6))
        inputs += ["-i", str(p)]
        ms = int(round(t_out * 1000))
        fc.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={gain}dB,"
                  f"adelay={ms}|{ms}[se{idx}]")
        mix_inputs.append(f"[se{idx}]")
        se_log.append({"file": se["file"], "out_time": round(t_out, 3), "gain_db": gain})
        idx += 1

    ed = cfg.get("ed")
    ed_log = None
    black_tail = float(ed.get("black_tail_seconds", 0)) if ed else 0.0
    fade_v = float(ed.get("fade_video_seconds", 3)) if ed else 0.0
    total_out = tl.out_duration + black_tail
    if ed:
        # 台詞トラック: 映像フェードに合わせてフェードし、黒味の分だけ無音を足す
        dchain = []
        if fade_v > 0:
            dchain.append(f"afade=t=out:st={max(0.0, tl.out_duration - fade_v):.3f}:d={fade_v:.3f}")
        if black_tail > 0:
            dchain.append(f"apad=pad_dur={black_tail:.3f}")
        if dchain:
            fc.append("[acat]" + ",".join(dchain) + "[acat2]")
            mix_inputs[0] = "[acat2]"
        p = se_dir / ed["music"]
        m_start_out = tl.src_to_out(ed["music_start_source"]) + float(ed.get("music_offset_seconds", 0))
        gain = float(ed.get("music_gain_db", -10))
        fade_a = float(ed.get("fade_audio_seconds", 5))
        end_out = total_out
        inputs += ["-i", str(p)]
        ms = int(round(m_start_out * 1000))
        music_len = end_out - m_start_out
        fc.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                  f"atrim=0:{music_len:.3f},volume={gain}dB,"
                  f"afade=t=in:st=0:d={float(ed.get('fade_in_seconds', 0.5)):.2f},"
                  f"afade=t=out:st={max(0.0, music_len - fade_a):.3f}:d={fade_a:.3f},"
                  f"adelay={ms}|{ms}[ed]")
        mix_inputs.append("[ed]")
        ed_log = {"music": ed["music"], "out_start": round(m_start_out, 3), "gain_db": gain,
                  "fade_audio_seconds": fade_a, "music_len": round(music_len, 3)}
        idx += 1

    if len(mix_inputs) > 1:
        fc.append("".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=longest:normalize=0:dropout_transition=0[amixed]")
    else:
        fc.append("[acat]anull[amixed]")
    tp = float(cfg.get("dialogue", {}).get("true_peak", -1.0))
    a_chain = f"alimiter=limit={10 ** ((tp - 0.3) / 20):.4f}:attack=5:release=50:level=false"
    fc.append(f"[amixed]{a_chain}[aout]")

    # --- 映像: スケール/フレームレート/テーマ表示/フェード
    ass_path = Path(workdir) / "themes.ass"
    theme_out = build_theme_ass(cfg, tl, fonts, ass_path)
    vchain = [f"scale={width}:{height}:flags=lanczos:force_original_aspect_ratio=decrease",
              f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2", f"fps={fps}", "format=yuv420p"]
    fontsdir = fonts.get("dir")
    ass_arg = str(ass_path).replace("\\", "/").replace(":", "\\:")
    vchain.append(f"ass='{ass_arg}'" + (f":fontsdir='{fontsdir}'" if fontsdir else ""))
    if ed and fade_v > 0:
        vchain.append(f"fade=t=out:st={max(0.0, tl.out_duration - fade_v):.3f}:d={fade_v:.3f}")
    if black_tail > 0:
        vchain.append(f"tpad=stop_mode=add:stop_duration={black_tail:.3f}:color=black")
    fc.append("[vcat]" + ",".join(vchain) + "[vout]")

    filter_script = Path(workdir) / "filter_complex.txt"
    filter_script.write_text(";\n".join(fc), encoding="utf-8")

    cmd = [FFMPEG, "-hide_banner", "-y", "-stats_period", "30"] + inputs + [
        "-filter_complex_script", str(filter_script),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", vcfg.get("preset", "medium"), "-crf", str(vcfg.get("crf", 19)),
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-g", str(fps * 2), "-bf", "2",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-t", f"{total_out:.3f}", str(outpath)]
    meta = {"keep_segments": tl.keep, "out_duration": round(tl.out_duration, 3), "total_out": round(total_out, 3),
            "themes_out": theme_out, "se": se_log, "ed": ed_log,
            "talk_end_out": round(tl.out_talk_end(), 3), "cmd": cmd}
    if dry_run:
        return meta
    run(cmd)
    return meta


# ---------------------------------------------------------------------------
# 4) QA
# ---------------------------------------------------------------------------
def qa(outpath, workdir, meta):
    info = probe(outpath)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    loud = measure_loudness(outpath)
    # 黒画面・無音の検出
    p = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(outpath),
                        "-vf", "blackdetect=d=0.5:pic_th=0.98", "-af", "silencedetect=n=-50dB:d=2",
                        "-f", "null", "-"], stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    black = [l.strip() for l in p.stderr.splitlines() if "black_start" in l]
    silence = [l.strip() for l in p.stderr.splitlines() if "silence_start" in l]
    # サムネイル（コンタクトシート）
    dur = float(info["format"]["duration"])
    pts = [max(0.5, dur * k / 12) for k in range(12)]
    sheet = Path(workdir) / "qa_contact_sheet.jpg"
    sel = "+".join([f"eq(n\\,{int(round(t * 30))})" for t in pts])
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(outpath),
                    "-vf", f"select='{sel}',scale=480:-1,tile=4x3", "-frames:v", "1", str(sheet)])
    report = {
        "file": str(outpath), "duration": dur,
        "video": {"codec": v["codec_name"], "width": v["width"], "height": v["height"],
                  "r_frame_rate": v["r_frame_rate"], "pix_fmt": v.get("pix_fmt"),
                  "color_primaries": v.get("color_primaries")},
        "audio": {"codec": a["codec_name"], "sample_rate": a["sample_rate"], "channels": a["channels"],
                  "bit_rate": a.get("bit_rate")},
        "loudness": loud, "black_frames": black, "silences": silence,
        "contact_sheet": str(sheet), "meta": {k: v for k, v in meta.items() if k != "cmd"},
    }
    (Path(workdir) / "qa_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--fonts-dir", default=os.environ.get("FONTS_DIR", ""))
    ap.add_argument("--skip-dialogue", action="store_true", help="整音済み WAV を再利用")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan_path = Path(args.plan).resolve()
    cfg = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_dir = plan_path.parent
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    fonts = {"dir": args.fonts_dir or None}

    src = Path(cfg["source"])
    if not src.is_absolute():
        src = plan_dir / src
    dialogue_wav = workdir / "dialogue_processed.wav"
    dlog = None
    if not (args.skip_dialogue and dialogue_wav.exists()):
        dlog = process_dialogue(src, dialogue_wav, cfg, workdir)
        (workdir / "dialogue_log.json").write_text(json.dumps(dlog, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = render(cfg, plan_dir, workdir, Path(args.out), fonts, dialogue_wav, dry_run=args.dry_run)
    (workdir / "render_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if args.dry_run:
        print(json.dumps({k: v for k, v in meta.items() if k != "cmd"}, ensure_ascii=False, indent=2))
        print(" ".join(shlex.quote(c) for c in meta["cmd"]))
        return
    rep = qa(Path(args.out), workdir, meta)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("meta",)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
