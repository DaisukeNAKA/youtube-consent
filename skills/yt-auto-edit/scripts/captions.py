#!/usr/bin/env python3.11
"""captions.py --transcript transcript.json --plan edit_plan.json --settings settings.json --out captions.json --srt 字幕.srt
keep 区間に含まれる単語だけを出力タイムライン時刻へ写像し、SPEC 2.1 の規則で1行キューに分割する。
- max_chars(既定18)、意味の切れ目優先（句読点・終助詞・助詞の直後）、次に文字数上限
- 句読点除去（読点→半角スペース）、全角英数→半角、行頭NG文字回避
- min_dur / max_dur / gap_fill、caption_overrides 適用。SRT 同時出力（--srt は互換用。正式な SRT は make_srt.py）。
v2 追加:
- B2: 落としたトークン（フィラー/相槌/接続の「で」/caption_mute）の時間帯を dropped_spans として保持し、
      apply_timing の gap_fill でその帯に重なる隙間は埋めない（発話中に字幕が出ない）。
- B3: edit_plan.caption_mute: [{src_start,src_end}] の語は字幕化しない（transcript は変えない）。"""
import argparse, os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, save_json, load_settings
from jatext import (zen2han, strip_punct, token_core, break_priority, detect_fillers, LINE_HEAD_NG, PUNCT_STRONG, PUNCT_WEAK)


class Mapper:
    """src(カメラ)時刻 → 出力時刻。keep 区間を順に詰める。"""
    def __init__(self, keep):
        self.keep = []
        t = 0.0
        for k in sorted(keep, key=lambda k: k["src_start"]):
            s, e = float(k["src_start"]), float(k["src_end"])
            if e <= s:
                continue
            self.keep.append((s, e, t))
            t += e - s
        self.total = t

    def contains(self, t):
        return any(s <= t < e for s, e, _ in self.keep)

    def to_out(self, t, clamp=True):
        for s, e, o in self.keep:
            if s <= t <= e:
                return o + (t - s)
        if not clamp:
            return None
        # 区間外: 直前の keep の終端 / 直後の keep の始端へ寄せる
        best = None
        for s, e, o in self.keep:
            if t < s:
                cand = o
            else:
                cand = o + (e - s)
            d = min(abs(t - s), abs(t - e))
            if best is None or d < best[0]:
                best = (d, cand)
        return best[1] if best else 0.0


def in_ranges(t, ranges):
    return any(s <= t <= e for s, e in ranges)


def mute_ranges(plan):
    """edit_plan.caption_mute → [(src_start, src_end)]（B3）"""
    out = []
    for m in (plan or {}).get("caption_mute") or []:
        try:
            s, e = float(m["src_start"]), float(m["src_end"])
        except (KeyError, TypeError, ValueError):
            continue
        if e > s:
            out.append((s, e))
    return out


def flat_tokens(tr, remove_fillers=True, mute=None, dropped=None):
    """transcript → 時刻順トークン列。落としたトークンの時間帯は dropped（list）に {"s","e","reason"} で追記する（B2）。
    mute: [(src_start, src_end)] の区間に中心があるトークンは字幕化しない（B3）。"""
    toks = []
    segs = tr.get("segments", [])
    drop = set()
    if dropped is None:
        dropped = []
    if remove_fillers:
        for f in detect_fillers(segs):
            drop.update(f["tokens"])
            dropped.append({"s": float(f["start"]), "e": float(f["end"]), "reason": "filler", "text": f["text"]})
    mute = mute or []
    for si, seg in enumerate(segs):
        ws = seg.get("words") or []
        if not ws:
            ws = [{"w": seg["text"], "s": seg["start"], "e": seg["end"]}]
        for i, w in enumerate(ws):
            if (si, i) in drop:
                continue
            ws_, we_ = float(w["s"]), float(w["e"])
            if mute and in_ranges((ws_ + we_) / 2.0, mute):
                dropped.append({"s": ws_, "e": we_, "reason": "mute", "text": w["w"]})
                continue
            toks.append({"w": w["w"], "s": ws_, "e": we_, "seg_end": i == len(ws) - 1, "seg": si, "seg_tail": "".join(token_core(x["w"]) for x in ws[max(0, len(ws) - 3):]) if i == len(ws) - 1 else None})
    toks.sort(key=lambda x: x["s"])
    # ポーズ/文末の直前に孤立した接続の「で」「でー」だけのトークンは落とす（「…書かれてて、で、」→「…書かれてて」）
    out = []
    for i, t in enumerate(toks):
        core = token_core(t["w"])
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        raw = zen2han(t["w"]).rstrip()
        if remove_fillers and core in ("で", "でー") and (nxt is None or nxt["s"] - t["e"] >= 0.3 or raw.endswith(("、", ",", "。"))):
            prev_raw = zen2han(out[-1]["w"]).rstrip() if out else ""
            if not out or prev_raw.endswith(("、", ",", "。", "て", "で")) or (out and t["s"] - out[-1]["e"] >= 0.3):
                dropped.append({"s": t["s"], "e": t["e"], "reason": "conj", "text": t["w"]})
                continue
        out.append(t)
    return out


def merge_spans(spans, join_gap=0.05):
    """[{"s","e",...}] → 昇順・重なり/近接を結合した [(s,e)]"""
    xs = sorted((float(x["s"]), float(x["e"])) for x in spans if float(x["e"]) > float(x["s"]) - 1e-9)
    out = []
    for s, e in xs:
        if out and s <= out[-1][1] + join_gap:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def dropped_spans_out(dropped, mapper):
    """落としたトークンの帯（src）→ 出力時刻の [(start,end)]。keep 外の帯は捨てる。"""
    out = []
    for s, e in merge_spans(dropped):
        for ks, ke, ko in mapper.keep:
            lo, hi = max(s, ks), min(e, ke)
            if hi - lo > 0.01:
                out.append((round(ko + (lo - ks), 3), round(ko + (hi - ks), 3)))
    return merge_spans([{"s": s, "e": e} for s, e in out])


BACKCHANNEL = ["はい", "はいはい", "はいはいはい", "うん", "うんうん", "ええ", "へー", "へえ", "ふーん", "ほう", "なるほど", "そうそう", "そうそうそう",
               "そうだね", "そうですね", "ほんま", "まじで", "え", "えー", "えぇ", "あー", "うわ", "うわっ", "おー", "おお", "おぉ"]


def seg_break_ok(tok, nxt, min_gap):
    """セグメント末トークン tok の直後で切ってよいか。間が min_gap 以上、または文末表現で終わる、または次が別の発話（短い相槌）なら切る"""
    from jatext import ends_with_any, SENT_END, token_core
    gap = nxt["s"] - tok["e"]
    if gap >= min_gap:
        return True
    core = token_core(tok["w"])
    if ends_with_any(core, SENT_END) and len(core) >= 2:
        return True
    # トークンが1文字（「よ」「ね」等）でも、セグメント末尾の連結文字列が文末表現なら切る（例: ます|よ → 「ますよ」）
    tail = tok.get("seg_tail") or core
    m = ends_with_any(tail, SENT_END) if tail else None
    if m and len(m) >= 2:
        return True
    return False


def is_backchannel_group(g, max_dur=2.5):
    """相槌だけの発話グループ（はい/うん/へー 等）か。字幕にしない（音声は残る）"""
    from jatext import token_core
    text = "".join(token_core(t["w"]) for t in g)
    dur = g[-1]["e"] - g[0]["s"]
    if not text or dur > max_dur:
        return False
    t = text.replace("ー", "").replace("っ", "")
    for b in BACKCHANNEL:
        b2 = b.replace("ー", "").replace("っ", "")
        if t == b2 or (len(t) <= 8 and set(t) <= set(b2 + "はいうんそうねだよ")):
            return True
    return False


def join_text(toks):
    """トークン列 → 字幕テキスト（句読点除去・読点は半角スペース・全角英数→半角）"""
    raw = "".join(zen2han(t["w"]) for t in toks)
    return strip_punct(raw)


def split_group(toks, max_chars, min_chars=4):
    """1つの発話グループ（ポーズ/文末で区切られた列）を max_chars 以下の行に分割する。"""
    lines = []
    i = 0
    n = len(toks)
    while i < n:
        # 収まる範囲で最良の切れ目を探す
        best = None
        j = i
        cur_len = 0
        while j < n:
            cand_text = join_text(toks[i:j + 1])
            L = len(cand_text)
            if L > max_chars and j > i:
                break
            nxt = toks[j + 1]["w"] if j + 1 < n else ""
            gap = (toks[j + 1]["s"] - toks[j]["e"]) if j + 1 < n else 9.0
            rest = join_text(toks[j + 1:]) if j + 1 < n else ""
            pr = break_priority(toks[j]["w"], nxt, gap, toks[j - 1]["w"] if j > 0 else "")
            if toks[j].get("seg_end") and pr and pr < 3:
                pr = 3  # Whisper セグメント末は意味の切れ目とみなす
            if j + 1 >= n:
                pr = 5  # 末尾
            if pr == 0 or (L < min_chars and j + 1 < n):
                score = -1
            else:
                score = pr * 10 + 8.0 * L / max_chars
                # 残りが短すぎる断片になる場合は少し減点（ただし文末優先）
                if 0 < len(rest) < min_chars and pr < 4:
                    score -= 12
            if score > (best[0] if best else -2):
                best = (score, j)
            j += 1
        if best is None or best[1] < i:
            # 1トークンで上限超えなどの例外: 1トークンだけで行にする
            best = (0, i)
        k = best[1]
        # 上限内に良い切れ目がなく(pr=1で L がかなり短い)、次の意味切れ目が近ければ許容範囲で伸ばさない（単純化）
        lines.append(toks[i:k + 1])
        i = k + 1
    return lines


def build_cues(toks, mapper, st, dropped=None):
    """dropped（list）を渡すと、相槌として落とした発話グループの帯を追記する（B2）。"""
    cap = st["caption"]
    max_chars = int(cap.get("max_chars", 18))
    # keep 内のトークンのみ（中心時刻で判定）
    kept = [t for t in toks if mapper.contains((t["s"] + t["e"]) / 2.0) and token_core(t["w"])]
    # 相槌だけのセグメント番号
    by_seg = {}
    for t in kept:
        by_seg.setdefault(t.get("seg"), []).append(t)
    bc_segs = {k for k, g in by_seg.items() if is_backchannel_group(g)}
    # 発話グループ: 文末句読点 / ポーズ >= 0.7s / keep 境界 で区切る
    groups, cur = [], []
    for idx, t in enumerate(kept):
        cur.append(t)
        nxt = kept[idx + 1] if idx + 1 < len(kept) else None
        end_here = False
        raw = zen2han(t["w"]).rstrip()
        if raw.endswith(tuple(PUNCT_STRONG)):
            end_here = True
        if nxt is None:
            end_here = True
        else:
            if nxt["s"] - t["e"] >= 0.7:
                end_here = True
            # Whisper セグメント境界（多くは文末/話者交代）: 直後に 0.15s 以上の間があるか、文末表現で終わっていれば切る
            if t.get("seg_end") and seg_break_ok(t, nxt, float(cap.get("segment_break_gap", 0.15))):
                end_here = True
            # 相槌だけのセグメントは前後から切り離す（後で落とす）
            if nxt.get("seg") != t.get("seg") and (nxt.get("seg") in bc_segs or t.get("seg") in bc_segs):
                end_here = True
            # keep 境界をまたぐ
            if mapper.to_out(nxt["s"]) - mapper.to_out(t["e"]) > (nxt["s"] - t["e"]) + 0.01 or \
               mapper.to_out(nxt["s"]) - mapper.to_out(t["e"]) < (nxt["s"] - t["e"]) - 0.01:
                end_here = True
        if end_here:
            groups.append(cur)
            cur = []
    cues = []
    drop_bc = bool(cap.get("drop_backchannel", True))
    for g in groups:
        if drop_bc and is_backchannel_group(g):
            if dropped is not None:
                dropped.append({"s": g[0]["s"], "e": g[-1]["e"], "reason": "backchannel", "text": join_text(g)})
            continue
        for line in split_group(g, max_chars):
            text = join_text(line)
            if not text:
                continue
            # 行頭NG文字の救済（前行末へ移す代わりに先頭を削る/そのまま）: 先頭がNGなら前のキューへ結合を試みる
            if text[0] in LINE_HEAD_NG and cues and len(cues[-1]["text"]) + len(text) <= max_chars + 2 and cues[-1]["_g"] is g:
                prev = cues[-1]
                prev["text"] = prev["text"] + text
                prev["src_end"] = line[-1]["e"]
                continue
            cues.append({"text": text, "src_start": line[0]["s"], "src_end": line[-1]["e"], "_g": g})
    for c in cues:
        c.pop("_g", None)
    return cues


def merge_short_cues(cues, st):
    """表示が min_dur 未満で短い（≤6字）キュー、または行頭NG文字・「って」で始まるキューを、
    間が 0.4s 未満で字数上限に収まるなら前（優先）か後ろのキューへ併合する。src 時刻ベース（apply_timing 前）。"""
    cap = st["caption"]
    max_chars = int(cap.get("max_chars", 18)); min_dur = float(cap.get("min_dur", 0.6))
    out = []
    i = 0
    while i < len(cues):
        c = cues[i]
        dur = c["src_end"] - c["src_start"]
        needs = (dur < min_dur and len(c["text"]) <= 6) or (c["text"] and (c["text"][0] in LINE_HEAD_NG and not c["text"].startswith("って")))
        if needs and out and (c["src_start"] - out[-1]["src_end"]) < 0.4 and len(out[-1]["text"]) + len(c["text"]) <= max_chars:
            out[-1]["text"] = out[-1]["text"] + c["text"]; out[-1]["src_end"] = c["src_end"]; i += 1; continue
        if needs and i + 1 < len(cues) and (cues[i + 1]["src_start"] - c["src_end"]) < 0.4 and len(c["text"]) + len(cues[i + 1]["text"]) <= max_chars \
                and not (cues[i + 1]["text"] and cues[i + 1]["text"][0] in LINE_HEAD_NG):
            cues[i + 1]["text"] = c["text"] + cues[i + 1]["text"]; cues[i + 1]["src_start"] = c["src_start"]; i += 1; continue
        out.append(c); i += 1
    return out


def apply_timing(cues, mapper, st, total_out, dropped_out=None):
    """dropped_out: 出力時刻の [(start,end)]（落とした語の発話帯）。gap_fill はこの帯に重なる隙間を埋めない（B2）。"""
    cap = st["caption"]
    min_dur = float(cap.get("min_dur", 0.8))
    max_dur = float(cap.get("max_dur", 4.0))
    gap_fill = float(cap.get("gap_fill", 0.6))
    no_fill = bool(cap.get("no_fill_over_dropped", True))
    dropped_out = dropped_out or []

    def first_dropped_after(t0, t1):
        """(t0,t1) に食い込む落とし帯のうち最初の開始時刻。無ければ None"""
        best = None
        for s, e in dropped_out:
            if e > t0 + 0.02 and s < t1 - 0.02:
                best = s if best is None else min(best, s)
        return best

    for c in cues:
        c["start"] = round(mapper.to_out(c["src_start"]), 3)
        c["end"] = round(max(c["start"] + 0.05, mapper.to_out(c["src_end"])), 3)
    cues.sort(key=lambda c: c["start"])
    for i, c in enumerate(cues):
        nxt_start = cues[i + 1]["start"] if i + 1 < len(cues) else total_out
        spoken_end = c["end"]
        end = spoken_end
        if end - c["start"] < min_dur:
            end = c["start"] + min_dur
        blocked = first_dropped_after(spoken_end, nxt_start) if no_fill else None
        if blocked is None:
            if nxt_start - end <= gap_fill:
                end = nxt_start
        else:
            # 落とした語（フィラー/相槌/mute）の発話中は字幕を出さない: 伸ばすのはその帯の手前まで
            end = min(end, max(spoken_end, blocked))
        # 上限: 発話が続いている間は消さないが、延長分は max_dur まで
        end = min(end, max(spoken_end, c["start"] + max_dur))
        end = min(end, nxt_start, total_out) if nxt_start > c["start"] else end
        c["end"] = round(max(end, c["start"] + 0.05), 3)
    return cues


def apply_overrides(cues, overrides):
    for ov in overrides or []:
        text = ov.get("text")
        idx = None
        if "index" in ov:
            idx = int(ov["index"])
        else:
            key = "src_time" if "src_time" in ov else ("out_time" if "out_time" in ov else None)
            if key is None:
                continue
            t = float(ov[key])
            ks, ke = ("src_start", "src_end") if key == "src_time" else ("start", "end")
            for i, c in enumerate(cues):
                if c[ks] - 0.05 <= t <= c[ke] + 0.05:
                    idx = i
                    break
            if idx is None and cues:
                idx = min(range(len(cues)), key=lambda i: abs((cues[i][ks] + cues[i][ke]) / 2 - t))
        if idx is None or not (0 <= idx < len(cues)):
            continue
        if text is None or text == "":
            cues[idx]["_delete"] = True
        else:
            cues[idx]["text"] = strip_punct(zen2han(text))
        if "start" in ov:
            cues[idx]["start"] = float(ov["start"])
        if "end" in ov:
            cues[idx]["end"] = float(ov["end"])
    return [c for c in cues if not c.get("_delete")]


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(path, cues):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n")


def main():
    ap = argparse.ArgumentParser(description="字幕キュー生成（captions.json + SRT）")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--settings", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--srt", default=None)
    ap.add_argument("--max-chars", type=int, default=None)
    a = ap.parse_args()
    st = load_settings(a.settings)
    if a.max_chars:
        st["caption"]["max_chars"] = a.max_chars
    tr = load_json(a.transcript)
    plan = load_json(a.plan)
    mapper = Mapper(plan.get("keep") or [])
    if not mapper.keep:
        print("[captions] plan.keep が空です", file=sys.stderr)
        sys.exit(2)
    dropped = []
    mute = mute_ranges(plan)
    toks = flat_tokens(tr, remove_fillers=bool(st["cuts"].get("remove_fillers", True)), mute=mute, dropped=dropped)
    cues = build_cues(toks, mapper, st, dropped=dropped)
    cues = merge_short_cues(cues, st)
    dropped_out = dropped_spans_out(dropped, mapper)
    cues = apply_timing(cues, mapper, st, mapper.total, dropped_out=dropped_out)
    cues = apply_overrides(cues, plan.get("caption_overrides"))
    cues.sort(key=lambda c: c["start"])
    out_cues = [{"start": round(c["start"], 3), "end": round(c["end"], 3), "text": c["text"],
                 "src_start": round(c["src_start"], 3), "src_end": round(c["src_end"], 3)} for c in cues]
    out_dropped = [{"start": s, "end": e} for s, e in dropped_out]
    save_json(a.out, {"max_chars": st["caption"]["max_chars"], "duration": round(mapper.total, 3), "cues": out_cues,
                      "dropped_spans": out_dropped,
                      "dropped_src": [{"src_start": round(d["s"], 3), "src_end": round(d["e"], 3), "reason": d["reason"],
                                       "text": d.get("text", "")} for d in sorted(dropped, key=lambda d: d["s"])
                                      if mapper.contains((d["s"] + d["e"]) / 2.0)],
                      "caption_mute": [{"src_start": s, "src_end": e} for s, e in mute]})
    if a.srt:
        write_srt(a.srt, out_cues)
    over = sum(1 for c in out_cues if len(c["text"]) > st["caption"]["max_chars"])
    print(f"[captions] {len(out_cues)} cues, over-limit={over}, dropped_spans={len(out_dropped)}, mute={len(mute)}, "
          f"total={mapper.total:.2f}s -> {a.out}" + (f", srt={a.srt}" if a.srt else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
