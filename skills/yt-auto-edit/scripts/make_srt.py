#!/usr/bin/env python3.11
"""make_srt.py --transcript transcript.json --plan edit_plan.json --out 字幕.srt [--settings settings.json] [--limit-seconds 40]
v2 B1: SRT（YouTube にアップする字幕ファイル）は焼き込みキュー(captions.json)とは別物として作る。
- 補正後 transcript.segments を文単位（句読点あり・フィラー/相槌もそのまま）で keep 区間へ写像する。
- keep 外の語は落とす。1セグメントが keep 境界をまたぐ場合は語単位で分け、keep ごとに別キューにする。
- 長すぎるセグメント（srt.max_chars 超）は句点→読点の順で語境界で分ける。
- 全角英数は半角に、余分な空白は除く。時刻は出力タイムライン（カット後）。
- 既定では edit_plan.caption_mute は無視する（SRT は全文が原則）。settings.srt.apply_caption_mute=true か --apply-mute で除外。"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, load_settings
from captions import Mapper, mute_ranges, in_ranges, srt_time
from jatext import zen2han, PUNCT_STRONG, PUNCT_WEAK


def seg_words(seg):
    ws = seg.get("words") or []
    out = []
    for w in ws:
        try:
            s, e = float(w["s"]), float(w["e"])
        except (KeyError, TypeError, ValueError):
            continue
        if not str(w.get("w", "")):
            continue
        out.append({"w": str(w["w"]), "s": s, "e": max(e, s)})
    if not out:
        out = [{"w": str(seg.get("text", "")), "s": float(seg["start"]), "e": float(seg["end"])}]
    return out


def clean_text(s):
    t = zen2han(s).replace("\n", " ")
    while "  " in t:
        t = t.replace("  ", " ")
    return t.strip()


def keep_index(mapper, t):
    for i, (s, e, _) in enumerate(mapper.keep):
        if s <= t < e:
            return i
    return None


def _len(words):
    return len(clean_text("".join(w["w"] for w in words)))


def _greedy(words, max_chars, punct):
    """語列を、punct（None=任意の語境界）で終わる位置だけで切りつつ max_chars 以下に詰める。
    候補が無く超える塊は次の候補まで伸ばす（後段のレベルで再分割）。必ず前進する。"""
    def can_cut(i):
        if punct is None:
            return True
        raw = zen2han(words[i]["w"]).rstrip()
        return bool(raw) and raw[-1] in punct
    out, start, last_ok = [], 0, None
    for i in range(len(words)):
        if _len(words[start:i + 1]) > max_chars and last_ok is not None and last_ok >= start:
            out.append(words[start:last_ok + 1])
            start = last_ok + 1
            last_ok = None
        if i >= start and can_cut(i) and i < len(words) - 1:
            last_ok = i
    if start < len(words):
        out.append(words[start:])
    return out


def split_long(words, max_chars):
    """語列を max_chars 以下の塊へ。切れ目は 句点 > 読点 > 語境界 の順に試す（各レベルで超える塊だけ次へ）。"""
    chunks = [words]
    for punct in (PUNCT_STRONG, PUNCT_WEAK, None):
        nxt = []
        for c in chunks:
            if _len(c) > max_chars and len(c) > 1:
                nxt.extend(_greedy(c, max_chars, punct))
            else:
                nxt.append(c)
        chunks = nxt
    return chunks


def build_srt_cues(tr, mapper, st, mute=None, limit=None):
    srt = st.get("srt") or {}
    max_chars = int(srt.get("max_chars", 40))
    min_dur = float(srt.get("min_dur", 0.5))
    max_dur = float(srt.get("max_dur", 8.0))
    total = mapper.total if limit is None else min(mapper.total, float(limit))
    cues = []
    for seg in tr.get("segments", []):
        words = seg_words(seg)
        # keep 区間ごとに語を振り分け（中心時刻）。keep 外/mute は落とす
        groups, cur, cur_k = [], [], None
        for w in words:
            mid = (w["s"] + w["e"]) / 2.0
            k = keep_index(mapper, mid)
            if k is None or (mute and in_ranges(mid, mute)):
                if cur:
                    groups.append((cur_k, cur))
                    cur, cur_k = [], None
                continue
            if cur and k != cur_k:
                groups.append((cur_k, cur))
                cur = []
            cur.append(w)
            cur_k = k
        if cur:
            groups.append((cur_k, cur))
        for k, g in groups:
            for chunk in split_long(g, max_chars):
                text = clean_text("".join(w["w"] for w in chunk))
                if not text:
                    continue
                ks, ke, ko = mapper.keep[k]
                s = ko + (max(chunk[0]["s"], ks) - ks)
                e = ko + (min(chunk[-1]["e"], ke) - ks)
                cues.append({"start": s, "end": max(e, s + 0.05), "text": text})
    cues.sort(key=lambda c: c["start"])
    # 表示時間の整形: min_dur まで伸ばす（次のキュー/末尾を越えない）、max_dur で切る、重なりを解消
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else total
        end = c["end"]
        if end - c["start"] < min_dur:
            end = c["start"] + min_dur
        end = min(end, c["start"] + max_dur)
        if nxt > c["start"]:
            end = min(end, nxt)
        c["end"] = max(end, c["start"] + 0.05)
    # limit で切る
    out = []
    for c in cues:
        if c["start"] >= total:
            continue
        c["end"] = min(c["end"], total)
        if c["end"] - c["start"] < 0.05:
            continue
        out.append({"start": round(c["start"], 3), "end": round(c["end"], 3), "text": c["text"]})
    return out


def write_srt(path, cues):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n")


def main():
    ap = argparse.ArgumentParser(description="補正後 transcript から SRT を生成（焼き込み字幕とは別）")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--settings", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit-seconds", type=float, default=None, help="試作用: 出力タイムライン先頭からこの秒数だけ")
    ap.add_argument("--apply-mute", action="store_true", help="edit_plan.caption_mute の語も SRT から落とす")
    ap.add_argument("--max-chars", type=int, default=None)
    a = ap.parse_args()
    st = load_settings(a.settings)
    st.setdefault("srt", {})
    if a.max_chars:
        st["srt"]["max_chars"] = a.max_chars
    tr = load_json(a.transcript)
    plan = load_json(a.plan)
    mapper = Mapper(plan.get("keep") or [])
    if not mapper.keep:
        print("[make_srt] plan.keep が空です", file=sys.stderr)
        sys.exit(2)
    mute = mute_ranges(plan) if (a.apply_mute or bool(st["srt"].get("apply_caption_mute", False))) else []
    cues = build_srt_cues(tr, mapper, st, mute=mute, limit=a.limit_seconds)
    write_srt(a.out, cues)
    total = mapper.total if a.limit_seconds is None else min(mapper.total, a.limit_seconds)
    print(f"[make_srt] {len(cues)} cues, total={total:.2f}s, max_chars={st['srt'].get('max_chars', 40)}, "
          f"mute={'on' if mute else 'off'} -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
