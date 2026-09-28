#!/usr/bin/env python3.11
"""日本語字幕テキスト処理の共通部（captions.py / plan_cuts.py / qc.py が使う）"""
import re

PUNCT_STRONG = "。！？!?"
PUNCT_WEAK = "、,，"
PUNCT_ALL = PUNCT_STRONG + PUNCT_WEAK + "…‥・「」『』（）()［］[]【】〈〉《》〔〕\"'“”‘’"
SMALL_KANA = "ぁぃぅぇぉゃゅょゎゕゖァィゥェォャュョヮヵヶ"
LINE_HEAD_NG = set("ーんっッ々〜~" + SMALL_KANA + PUNCT_STRONG + PUNCT_WEAK + "」』）)］]】〉》〕…‥・")
# 意味の切れ目（この語で終わるトークンの直後は切りやすい）。長いものを先に。
SENT_END = ["ですよね", "ますよね", "でしょう", "ですけど", "ますけど", "ですね", "ますね", "ですよ", "ますよ", "ですが", "ますが",
            "ました", "でした", "ません", "です", "ます", "けど", "けれど", "よね", "かな", "から", "ので", "のに", "たら", "れば",
            "ながら", "って", "やん", "ね", "よ", "し", "が", "て", "で", "か"]
PARTICLES = ["は", "を", "に", "の", "と", "も", "へ", "や", "まで", "より", "だけ", "など", "とか", "では", "には", "とは"]
FILLERS = ["えーっと", "えーと", "ええと", "えっと", "えーっ", "えー", "ええ", "あのー", "あのう", "あの", "まあ", "まぁ", "なんか",
           "その", "うーん", "うーんと", "んーと", "んー", "あー", "えっとー", "そのー", "まあまあ", "でー", "で", "あ", "え", "あっ", "えっ"]

_ZEN2HAN = {chr(c): chr(c - 0xFEE0) for c in range(0xFF01, 0xFF5F)}
_ZEN2HAN["　"] = " "


def zen2han(s: str) -> str:
    return "".join(_ZEN2HAN.get(ch, ch) for ch in s)


def strip_punct(s: str, comma_to_space=True) -> str:
    """句読点除去。読点は半角スペースに（連続スペース圧縮、前後trim）。"""
    out = []
    for ch in s:
        if ch in PUNCT_STRONG or ch in "…‥":
            continue
        if ch in PUNCT_WEAK:
            out.append(" " if comma_to_space else "")
            continue
        if ch in "「」『』（）()［］[]【】〈〉《》\"“”":
            continue
        out.append(ch)
    t = "".join(out)
    t = re.sub(r"[ \t]+", " ", t).strip()
    return t


def normalize_caption_text(s: str) -> str:
    return strip_punct(zen2han(s))


def visible_len(s: str) -> int:
    return len(s)


def token_core(w: str) -> str:
    """トークンから空白・句読点を除いた本体"""
    return strip_punct(zen2han(w), comma_to_space=False).replace(" ", "")


def ends_with_any(core: str, lst):
    for x in lst:
        if core.endswith(x):
            return x
    return None


def break_priority(tok_text: str, next_text: str, gap: float, prev_text: str = "") -> int:
    """tok_text(トークン原文)の直後で改行する望ましさ。0=不可,1=任意,2=助詞後,3=意味の切れ目,4=文末/句読点/長ポーズ"""
    raw = zen2han(tok_text)
    core = token_core(tok_text)
    nxt = token_core(next_text) if next_text else ""
    if nxt and nxt[0] in LINE_HEAD_NG:
        return 0
    if nxt and nxt in LONE_PARTICLES and gap < 0.7:
        return 0
    if raw.rstrip().endswith(tuple(PUNCT_STRONG)) or gap >= 0.7:
        return 4
    if raw.rstrip().endswith(tuple(PUNCT_WEAK)) or gap >= 0.35:
        return 3
    if ends_with_any(core, SENT_END):
        # 「よ|く」「か|ら」のように語の途中で切れているケース: 次が1文字のかなで間が無いなら不可
        if nxt and len(nxt) == 1 and re.match(r"[ぁ-ゖ]", nxt) and gap < 0.25:
            return 0
        if len(core) >= 2 or core in ("ね", "よ"):
            return 3
        prev = token_core(prev_text) if prev_text else ""
        # 「〜のが」「〜るけど」など節の切れ目に立つ接続助詞
        if core in ("が", "し", "て", "で", "か") and prev and prev[-1] in "のるたいうくすんだ":
            return 3
        return 2
    if ends_with_any(core, PARTICLES):
        return 2
    return 1


LONE_PARTICLES = set(["が", "は", "を", "に", "の", "と", "も", "へ", "で", "ね", "よ", "か", "な", "し", "て", "や", "わ", "さ", "な"])


def detect_fillers(segments, min_pause=0.25):
    """セグメント先頭 or ポーズ(>=min_pause)直後のフィラー語を検出。
    戻り値: [{"start","end","text","tokens":[(seg_idx, tok_idx),...]}]"""
    out = []
    for si, seg in enumerate(segments):
        ws = seg.get("words") or []
        i = 0
        while i < len(ws):
            w = ws[i]
            prev_raw = zen2han(ws[i - 1]["w"]).rstrip() if i > 0 else ""
            at_head = (i == 0) or (float(w["s"]) - float(ws[i - 1]["e"]) >= min_pause) or prev_raw.endswith(tuple(PUNCT_STRONG))
            if at_head:
                text, spans = "", []
                for j in range(i, min(i + 4, len(ws))):
                    for ch in token_core(ws[j]["w"]):
                        text += ch
                        spans.append(j)
                hit = None
                for f in sorted(FILLERS, key=len, reverse=True):
                    if text.startswith(f):
                        k = spans[len(f) - 1]
                        raw = zen2han(ws[k]["w"]).rstrip()
                        nxt_gap = (float(ws[k + 1]["s"]) - float(ws[k]["e"])) if k + 1 < len(ws) else 1.0
                        boundary = raw.endswith(("、", ",", " ", "。", "?", "？", "!", "！")) or nxt_gap >= 0.3 or len(text) == len(f) \
                            or len(spans) > len(f) and spans[len(f)] != k  # フィラー語がトークン境界で終わる
                        if f in ("で", "その", "でー", "ええ", "な", "あ", "え", "あっ", "えっ"):
                            # 実語になりやすいものは読点/ポーズが直後にある時だけ
                            if not (raw.endswith(("、", ",", " ", "。", "?", "？", "!", "！")) or nxt_gap >= 0.3 or len(text) == len(f)):
                                continue
                        if not boundary:
                            continue
                        hit = f
                        break
                if hit:
                    k0, k1 = spans[0], spans[len(hit) - 1]
                    out.append({"start": round(float(ws[k0]["s"]), 3), "end": round(float(ws[k1]["e"]), 3),
                                "text": hit, "tokens": [(si, j) for j in range(k0, k1 + 1)]})
                    i = k1 + 1
                    continue
            i += 1
    return out
