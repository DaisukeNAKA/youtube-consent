#!/usr/bin/env python3
"""ユニコ15秒CM 自動QA（最終絵コンテ v2 の受け入れ基準）
usage: python3 tools/qa.py out/unico_cm15_916.mp4 [out/unico_cm15_169.mp4 ...]

書き出した MP4 と、書き出し時に記録した qa_boxes.json（各要素の外接矩形・読める状態・2人のステッカー間隔）から判定する。
issues（不合格）が1件でもあれば終了コード1。warnings は参考値（公開判断の材料として報告するが不合格にはしない）。

 1. 尺・形式 : 映像 450 フレーム・30fps・所定の解像度。コンテナ尺と各トラックの実尺（mdhd）・編集リスト（elst）が
               すべて 15.000 秒以下。音声は 718,848 サンプル・ステレオ。H.264 High / yuv420p / BT.709 / AAC-LC 48kHz / faststart
 2. 音       : 統合ラウドネス -14±1 LUFS、トゥルーピーク -1.0 dBTP 以下
 3. 安全域   : テロップ・ラベル・吹き出しのしっぽ・ロゴが UI の共通セーフゾーン内。顔（頭部枠）は 0.4 秒を超えてはみ出さない
 4. 重なり   : 文字要素同士・文字要素（しっぽを含む）と頭部枠（髪を含む）・頭部枠同士の重なりが 0
 5. 間隔     : 同じ画面にいる2人のステッカー（白フチ込みの外形）の間隔が 20px 以上（オチの反応ステッカーは絵コンテで除外）
 6. 読む速さ : 字数は句読点・記号を除き全角1字・半角0.5字。「読める状態」（枠が9割以上の大きさ・不透明度9割以上）の秒で数える。
               台詞は1回の表示ごとに 5.6字/秒以下（絵コンテ v2 の設計上限）。4.8字/秒（小畑ほか 1985）を超えるものは warnings。
               名札・ラベルは1回1.0秒以上かつ 8字/秒以下。同じ文字列を含む表示の累計が 4.8字/秒に届かないものは warnings
 7. 文字の大きさ: すべての文字要素が 40px 以上（短辺1080換算）、台詞は 56px 以上
 8. ABCD     : 0 フレーム目に顔、4.5 秒までにロゴまたは「ユニコ」表記
 9. 相方の見え方: 中塚の顔が見えるフレーム ≥180（40%）、台詞の字数の中塚比率 ≥40%、2人が並ぶとき頭部枠の高さ 中塚≥リッチャン☆、
               最大の打撃音（cues.json の strong）の瞬間は中塚だけが映る、最後の台詞は中塚
10. 点滅     : 一般閃光（輝度差10%以上の逆向きの変化の対が画面の25%以上）が どの1秒間でも3回以下（ITU-R BT.1702 の考え方の簡易判定）
"""
import json, re, struct, subprocess, sys, os
import numpy as np
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS, NF, NS, LIM = 30, 450, 718848, 15.0
SAFE = {
    '916': [(120, 288, 780, 1248), (780, 288, 888, 840)],
    '169': [(96, 183, 1758, 693), (496, 38, 1443, 183)],
}
RES = {'916': (1080, 1920), '169': (1920, 1080)}
PUNCT = re.compile(r'[\s、。！？!?「」…・ー〜~☆★✓@_.,｜|／/]')
CPS_DIALOGUE, CPS_ADVISE, CPS_LABEL = 5.6, 4.8, 8.0


def chars(s):
    s = PUNCT.sub('', s)
    return sum(.5 if ord(c) < 0x2000 else 1 for c in s)


def inside(b, rects, tol=2):
    pts = [(b['x0'], b['y0']), (b['x1'], b['y0']), (b['x0'], b['y1']), (b['x1'], b['y1']), ((b['x0'] + b['x1']) / 2, (b['y0'] + b['y1']) / 2)]
    return all(any(x0 - tol <= x <= x1 + tol and y0 - tol <= y <= y1 + tol for x0, y0, x1, y1 in rects) for x, y in pts)


def inter(A, B, eps=1.0):
    iw = min(A['x1'], B['x1']) - max(A['x0'], B['x0']); ih = min(A['y1'], B['y1']) - max(A['y0'], B['y0'])
    return iw > eps and ih > eps


def runs(frames):
    out = []
    for i in sorted(set(frames)):
        if out and i == out[-1][1] + 1: out[-1][1] = i
        else: out.append([i, i])
    return out


def mp4_tracks(path):
    """moov を直接読み、トラックごとの実尺（mdhd）と編集リストの尺（elst）を秒で返す"""
    data = open(path, 'rb').read()
    def boxes(buf, a, b):
        i = a
        while i + 8 <= b:
            size, typ = struct.unpack('>I4s', buf[i:i + 8]); hdr = 8
            if size == 1: size = struct.unpack('>Q', buf[i + 8:i + 16])[0]; hdr = 16
            if size == 0: size = b - i
            yield typ.decode('latin1'), i + hdr, i + size; i += size
    def find(buf, a, b, path):
        for typ, s, e in boxes(buf, a, b):
            if typ == path[0]: return (s, e) if len(path) == 1 else find(buf, s, e, path[1:])
        return None
    moov = find(data, 0, len(data), ['moov']); mvhd = find(data, *moov, ['mvhd'])
    v = data[mvhd[0]]; mts = struct.unpack('>I', data[mvhd[0] + (20 if v == 1 else 12):][:4])[0]
    mdur = struct.unpack('>Q' if v == 1 else '>I', data[mvhd[0] + (24 if v == 1 else 16):][:8 if v == 1 else 4])[0]
    out = {'movie': mdur / mts}
    for typ, s, e in boxes(data, *moov):
        if typ != 'trak': continue
        hdlr = find(data, s, e, ['mdia', 'hdlr']); kind = data[hdlr[0] + 8:hdlr[0] + 12].decode('latin1')
        md = find(data, s, e, ['mdia', 'mdhd']); v = data[md[0]]
        ts = struct.unpack('>I', data[md[0] + (20 if v == 1 else 12):][:4])[0]
        du = struct.unpack('>Q' if v == 1 else '>I', data[md[0] + (24 if v == 1 else 16):][:8 if v == 1 else 4])[0]
        el = find(data, s, e, ['edts', 'elst']); edit = None
        if el:
            v2 = data[el[0]]; n = struct.unpack('>I', data[el[0] + 4:el[0] + 8])[0]; p = el[0] + 8; tot = 0
            for _ in range(n):
                seg = struct.unpack('>Q' if v2 == 1 else '>I', data[p:p + (8 if v2 == 1 else 4)])[0]; p += (8 if v2 == 1 else 4)
                mt = struct.unpack('>q' if v2 == 1 else '>i', data[p:p + (8 if v2 == 1 else 4)])[0]; p += (8 if v2 == 1 else 4) + 4
                if mt != -1: tot += seg
            edit = tot / mts
        out[kind] = {'media': du / ts, 'edit': edit}
    return out


def probe(path):
    r = subprocess.run([FF, '-hide_banner', '-i', path, '-map', '0:v', '-f', 'null', '-'], capture_output=True, text=True).stderr
    frames = int(re.findall(r'frame=\s*(\d+)', r)[-1])
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', r); dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    vs = re.search(r'Video: .*?, (\d+)x(\d+).*?, ([\d.]+) fps', r)
    info = {k: bool(re.search(p, r)) for k, p in [('H.264 High', r'h264 \(High\)'), ('yuv420p', r'yuv420p'), ('BT.709', r'bt709'), ('AAC-LC 48kHz', r'aac \(LC\).*48000 Hz'), ('stereo', r'48000 Hz, stereo')]}
    pcm = subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-i', path, '-map', '0:a', '-f', 's16le', '-ac', '2', '-'], capture_output=True).stdout
    a = subprocess.run([FF, '-hide_banner', '-i', path, '-map', '0:a', '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
    s = a[a.rfind('Summary:'):]
    I = float(re.search(r'I:\s+(-?[\d.]+) LUFS', s)[1]); TP = float(re.search(r'Peak:\s+(-?[\d.]+) dBFS', s)[1])
    head = open(path, 'rb').read(1 << 20); mo, md = head.find(b'moov'), head.find(b'mdat'); moov_first = mo >= 0 and (md < 0 or mo < md)   # faststart
    return frames, dur, (int(vs[1]), int(vs[2]), float(vs[3])) if vs else None, len(pcm) // 4, I, TP, info, moov_first


def flashes(path, W, H):
    w, h = (54, 96) if H > W else (96, 54)
    raw = subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-i', path, '-vf', f'scale={w}:{h}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    v = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3).astype(np.float64) / 255
    lin = np.where(v <= .04045, v / 12.92, ((v + .055) / 1.055) ** 2.4)
    L = lin @ np.array([.2126, .7152, .0722])
    red = (v[..., 0] / np.maximum(v.sum(-1), 1e-6) >= .8).mean((1, 2)).max()
    n = L.shape[0]; ext = L[0].copy(); dirn = np.zeros_like(ext); events = []
    for i in range(1, n):
        cur = L[i]
        up = (cur - ext >= .1) & (np.minimum(cur, ext) < .8); dn = (ext - cur >= .1) & (np.minimum(cur, ext) < .8)
        trans = up | dn; new_dir = np.where(up, 1, np.where(dn, -1, 0))
        flash = trans & (dirn != 0) & (new_dir != dirn)
        if flash.mean() >= .25: events.append(i)
        dirn = np.where(trans, new_dir, dirn)
        ext = np.where(trans, cur, np.where(dirn >= 0, np.maximum(ext, cur), np.minimum(ext, cur)))
    worst = max((sum(1 for e in events if s <= e < s + FPS) for s in range(n)), default=0)
    return worst, events, float(red)


def main(paths):
    ok = True; report = []
    cues = json.load(open(os.path.join(ROOT, 'cues.json'), encoding='utf-8'))
    strong = [c['t'] for c in cues['se'] if c.get('level') == 'strong']
    for p in paths:
        base = os.path.basename(p); fmt = '169' if '_169' in base else '916'
        frames, d, vid, samples, I, TP, info, moov = probe(p); tr = mp4_tracks(p)
        res = {'file': base, 'format': fmt, 'variant': 'SNS' if '_sns' in base else ('YT' if fmt == '916' else '169'), 'frames': frames, 'duration': d,
               'audio_samples': samples, 'LUFS': I, 'TP': TP, 'tracks': tr, 'issues': [], 'warnings': [], 'checks': {}}
        chk = res['checks']
        def check(name, passed, value, need):
            chk[name] = {'pass': bool(passed), 'value': value, 'need': need}
            if not passed: res['issues'].append(f'{name}: {value}（基準 {need}）')
        W_, H_ = RES[fmt]
        check('映像フレーム数', frames == NF, frames, '450')
        check('解像度・fps', vid is not None and vid[:2] == (W_, H_) and abs(vid[2] - 30) < 1e-6, f'{vid[0]}x{vid[1]} {vid[2]:g}fps' if vid else '不明', f'{W_}x{H_} 30fps')
        durs = [tr['movie']] + [x for k in ('vide', 'soun') if k in tr for x in (tr[k]['media'], tr[k]['edit']) if x is not None]
        check('尺（コンテナ・各トラック）', max(durs) <= LIM + 1e-9, f'最大 {max(durs):.4f}s（movie {tr["movie"]:.4f} / 映像 {tr.get("vide", {}).get("media", 0):.4f} / 音声 {tr.get("soun", {}).get("media", 0):.4f}）', '≤15.000s')
        check('音声サンプル数', samples == NS, samples, f'{NS}（{NS / 48000:.4f}s）')
        check('統合ラウドネス', -15.0 <= I <= -13.0, f'{I} LUFS', '-14±1 LUFS')
        check('トゥルーピーク', TP <= -1.0, f'{TP} dBTP', '≤-1.0 dBTP')
        check('エンコード', all(info.values()) and moov, ', '.join(k for k, v in info.items() if v) + (', faststart' if moov else ''), 'H.264 High / yuv420p / BT.709 / AAC-LC 48kHz stereo / faststart')
        bx = p[:-4] + '.qa_boxes.json'
        if not os.path.exists(bx):
            res['issues'].append('qa_boxes.json がない'); ok = False; report.append(res); continue
        B = json.load(open(bx, encoding='utf-8')); rects = SAFE[fmt]; W, H = B['W'], B['H']
        TXT = ('telop', 'label')
        outside, head_out, overl, weak, spans, rspans, spk, first_seen, small = {}, {}, {}, {}, {}, {}, {}, {}, {}
        naka = 0; brand_t = None; size_bad = []; onsets = []
        for i, fr in enumerate(B['frames']):
            on = [b for b in fr if b['x1'] > 0 and b['y1'] > 0 and b['x0'] < W and b['y0'] < H and (b['x1'] - b['x0']) > 1]
            vis = [b for b in on if b['a'] > .5]; faint = [b for b in on if .1 < b['a'] <= .5]
            txt = [b for b in vis if b['kind'] in TXT]; tails = [b for b in vis if b['kind'] == 'tail']
            heads = [b for b in vis if b['kind'] == 'head']; logos = [b for b in vis if b['kind'] == 'logo']
            for b in txt:
                spans.setdefault((b['kind'], b['label']), []).append(i)
                if b.get('rd', True): rspans.setdefault((b['kind'], b['label']), []).append(i)
                if b['label'] not in first_seen: first_seen[b['label']] = i; onsets.append((i, chars(b['label'])))
                if b.get('spk'): spk[b['label']] = b['spk']
                if 'ユニコ' in b['label'] and brand_t is None: brand_t = i / FPS
                need = 56 if b.get('spk') and b['kind'] == 'telop' else 40
                if b.get('px') and b['px'] < need - 1e-6: small.setdefault(f"{b['label']}（{b['px']:g}px < {need}px）", []).append(i)
            if logos and brand_t is None: brand_t = i / FPS
            for b in txt + tails + logos:
                if not inside(b, rects): outside.setdefault(b['label'] + ('のしっぽ' if b['kind'] == 'tail' else ''), []).append(i)
            for b in heads:
                if not inside(b, rects, tol=4): head_out.setdefault(b['label'], []).append(i)
            els = txt + logos
            for x in range(len(els)):
                for y in range(x + 1, len(els)):
                    if els[x]['label'] != els[y]['label'] and inter(els[x], els[y]): overl.setdefault(f"{els[x]['label']}×{els[y]['label']}", []).append(i)
                for hb in heads:
                    if inter(els[x], hb): overl.setdefault(f"{els[x]['label']}×{hb['label']}の頭部", []).append(i)
            for tb in tails:   # しっぽ: 自分の枠以外の文字要素・頭部と重ならない
                for o in els + heads:
                    if o['kind'] != 'head' and o['label'] == tb['label']: continue
                    if inter(tb, o): overl.setdefault(f"{tb['label']}のしっぽ×{o['label']}{'の頭部' if o['kind'] == 'head' else ''}", []).append(i)
            for x in range(len(heads)):
                for y in range(x + 1, len(heads)):
                    if heads[x]['label'] != heads[y]['label'] and inter(heads[x], heads[y]): overl.setdefault('頭部同士', []).append(i)
            for b in faint:   # 出入りの途中（不透明度 0.1–0.5）の重なり・はみ出しは参考値
                if b['kind'] in TXT and not inside(b, rects): weak.setdefault(f"出入り中のはみ出し「{b['label']}」", []).append(i)
            hn = [b['y1'] - b['y0'] for b in heads if b['label'] == 'nakatsuka']; hr = [b['y1'] - b['y0'] for b in heads if b['label'] == 'ricchan']
            if hn and hr and max(hr) > max(hn) + 1: size_bad.append(i)
            if any(b['kind'] == 'face' and b['label'] == 'nakatsuka' for b in vis): naka += 1
        for lab, fs in outside.items(): res['issues'].append(f'セーフゾーン外「{lab}」 frames {fs[0]}–{fs[-1]} ({len(fs)}f)')
        long_out = {lab: [r for r in runs(fs) if r[1] - r[0] + 1 > 12] for lab, fs in head_out.items()}
        for lab, rs in long_out.items():
            if rs: res['issues'].append(f'セーフゾーン外の顔（{lab}） frames ' + ', '.join(f'{a}–{b}' for a, b in rs))
        for lab, fs in overl.items(): res['issues'].append(f'重なり {lab} frames {fs[0]}–{fs[-1]} ({len(fs)}f)')
        for lab, fs in weak.items(): res['warnings'].append(f'{lab} frames {fs[0]}–{fs[-1]} ({len(fs)}f)')
        for lab, fs in small.items(): res['issues'].append(f'文字が小さい {lab} frames {fs[0]}–{fs[-1]}')
        chk['セーフゾーン'] = {'pass': not outside and not any(long_out.values()), 'value': f'はみ出し {len(outside) + sum(1 for v in long_out.values() if v)} 件', 'need': '文字・しっぽ・ロゴ・顔が共通安全域内'}
        chk['重なり'] = {'pass': not overl, 'value': f'{len(overl)} 件', 'need': '文字同士・文字（しっぽ含む）と頭部・頭部同士 0'}
        chk['文字の大きさ'] = {'pass': not small, 'value': f'下限未満 {len(small)} 件', 'need': '全文字 ≥40px・台詞 ≥56px'}
        # 2人のステッカー間隔
        gaps = [(i, g) for i, g in enumerate(B.get('gaps', [])) if g is not None]
        gmin = min(gaps, key=lambda x: x[1]) if gaps else None
        check('2人のステッカー間隔', gmin is None or gmin[1] >= 20, f'最小 {gmin[1]:.0f}px（f{gmin[0]}）' if gmin else '同時に映る場面なし', '≥20px（白フチ込み）')
        # 読む速さ
        reading = {}; rbad = []
        for (kind, lab), fs in spans.items():
            n = chars(lab)
            if not n: continue
            rr = [r for r in runs(rspans.get((kind, lab), []))]
            if not rr: rbad.append(f'読める状態にならない「{lab}」'); continue
            shortest = min(r[1] - r[0] + 1 for r in rr) / FPS
            if kind == 'telop':
                cps = n / shortest
                if cps > CPS_DIALOGUE + 1e-6: rbad.append(f'読む速さ超過「{lab}」 {n:g}字/{shortest:.2f}s＝{cps:.2f}字/秒（上限 {CPS_DIALOGUE}）')
                elif cps > CPS_ADVISE + 1e-6: res['warnings'].append(f'4.8字/秒超（上限内）「{lab}」 {cps:.2f}字/秒')
            else:
                cps = n / shortest
                cum = len({i for (k2, l2), f2 in rspans.items() if lab in l2 for i in f2}) / FPS
                if shortest < 1.0 - 1e-6 or cps > CPS_LABEL + 1e-6: rbad.append(f'読む速さ超過（ラベル）「{lab}」 1回 {shortest:.2f}s・{cps:.2f}字/秒（基準 1.0s以上・{CPS_LABEL}字/秒以下）')
                elif cum + 1e-6 < n / CPS_ADVISE: res['warnings'].append(f'ラベルの累計表示が4.8字/秒に届かない「{lab}」 累計 {cum:.2f}s（目安 {n / CPS_ADVISE:.2f}s）')
            reading[lab] = {'kind': kind, 'speaker': spk.get(lab), 'chars': n, 'readable_s': round(shortest, 2), 'cps': round(cps, 2)}
        res['issues'] += rbad
        chk['読む速さ'] = {'pass': not rbad, 'value': f'超過 {len(rbad)} 件（4.8字/秒超の参考 {sum(1 for w in res["warnings"] if w.startswith("4.8"))} 件）', 'need': f'台詞 ≤{CPS_DIALOGUE}字/秒・ラベル ≤{CPS_LABEL}字/秒かつ1回1.0秒以上'}
        res['reading'] = reading
        load = max((sum(c for i, c in onsets if s <= i < s + 60) for s in range(len(B['frames']))), default=0)
        if load > 16: res['warnings'].append(f'参考: 2秒間に新しく読む字数の最大 {load:g}字（目安16字）')
        chk['同時に読む量（参考）'] = {'pass': True, 'value': f'2秒間で最大 {load:g}字', 'need': '参考値（16字以下が目安）'}
        # ABCD
        f0 = B['frames'][0]
        check('0フレーム目に顔', any(b['kind'] in ('face', 'head') for b in f0), 'あり' if any(b['kind'] in ('face', 'head') for b in f0) else 'なし', 'あり（ABCD: Attract）')
        check('ブランド初出', brand_t is not None and brand_t <= 4.5, f'{brand_t}s', '≤4.5s（ABCD: Brand）')
        # 相方の見え方
        check('中塚の顔が見えるフレーム', naka >= 180, f'{naka}/{len(B["frames"])}（{naka / len(B["frames"]):.0%}）', '≥180（40%）')
        tot = sum(chars(l) for l in spk); nk = sum(chars(l) for l, s in spk.items() if s == 'nakatsuka')
        check('台詞の字数の中塚比率', tot and nk / tot >= .40, f'{nk:g}/{tot:g}字（{(nk / tot if tot else 0):.0%}）', '≥40%')
        check('頭部の大きさ 中塚≥リッチャン☆', not size_bad, f'逆転 {len(size_bad)} フレーム', '0')
        sb = []
        for t in strong:
            fr = B['frames'][min(len(B['frames']) - 1, round(t * FPS))]
            who = {b['label'] for b in fr if b['kind'] in ('face', 'head') and b['a'] > .5}
            sb.append(f'{t:.2f}s={"・".join(sorted(who)) or "なし"}')
            if who != {'nakatsuka'}: sb[-1] += '（NG）'
        check('最大の打撃音の瞬間', all('NG' not in x for x in sb), ', '.join(sb), '中塚だけが映る')
        last = max((first_seen[l], l) for l in spk if chars(l)) if spk else (None, None)
        check('最後の台詞', spk.get(last[1]) == 'nakatsuka', f'{last[1]}（{spk.get(last[1])}）', '中塚')
        worst, ev, red = flashes(p, W, H)
        check('一般閃光（任意の1秒間）', worst <= 3, f'最大 {worst} 回（検出フレーム {ev}）', '≤3回')
        chk['飽和赤の最大面積'] = {'pass': True, 'value': f'{red:.1%}', 'need': '参考値'}
        res['nakatsuka_face_frames'] = naka; res['brand_first_s'] = brand_t
        res['issues'] = sorted(set(res['issues']), key=res['issues'].index)
        ok &= not res['issues']; report.append(res)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
