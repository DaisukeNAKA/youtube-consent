#!/usr/bin/env python3
"""ユニコ15秒CM 自動QA（最終絵コンテ v2 の受け入れ基準）
usage: python3 tools/qa.py out/unico_cm15_916.mp4 [out/unico_cm15_169.mp4 ...]

検査項目（すべて書き出した MP4 と、書き出し時に記録した qa_boxes.json から機械的に判定）
 1. 尺・形式 : 映像450フレーム・15.000秒以下、音声 719,872 サンプル（AAC 703 フレーム）・15.000秒以下
 2. 音       : 統合ラウドネス -14±1 LUFS、トゥルーピーク -1.0 dBTP 以下
 3. 安全域   : テロップ・ラベル・ロゴが各プラットフォームUIの共通セーフゾーン内。
               顔（頭部枠）は 12 フレーム（0.4秒）を超えてはみ出さない（登場・退場の動きは許容）
 4. 重なり   : 文字要素同士・文字要素と頭部枠（髪を含む）・頭部枠同士の重なりが 0
 5. 読了     : 字数 = 句読点・記号を除き全角1字・半角0.5字。
               台詞テロップ（kind=telop）は 1回の表示ごとに 字数/4.8 秒以上（小畑ほか 1985「秒当たり4.8字以下」）。
               ラベル（名札・チップ・名前。kind=label）は同じ文字列を含む表示の累計で 字数/4.8 秒以上、かつ1回1.0秒以上
 6. ABCD     : 0フレーム目に顔、4.5秒までにロゴまたは「ユニコ」表記
 7. 相方保護 : 中塚の顔が画面内にあるフレーム ≥180（40%）、台詞の字数の中塚比率 ≥40%、
               2人が同じ画面にいるとき中塚の頭部枠の高さ ≥ リッチャン☆、最後の台詞は中塚
 8. 点滅     : 一般閃光（輝度差10%以上の逆向き変化の対、画面の25%以上）が どの1秒間でも3回以下（ITU-R BT.1702 の簡易判定）。
               飽和赤（R/(R+G+B)≥0.8）の最大面積も報告
"""
import json, re, subprocess, sys, os
import numpy as np
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
FPS, NF, NS = 30, 450, 719872
SAFE = {
    '916': [(120, 288, 780, 1248), (780, 288, 888, 840)],
    '169': [(96, 183, 1758, 693), (496, 38, 1445, 183)],
}
PUNCT = re.compile(r'[\s、。！？!?「」…・ー〜~☆★✓@_.,｜|／/]')
READ_CPS = 4.8


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
    for i in frames:
        if out and i == out[-1][1] + 1: out[-1][1] = i
        else: out.append([i, i])
    return out


def probe(path):
    r = subprocess.run([FF, '-hide_banner', '-i', path, '-map', '0:v', '-f', 'null', '-'], capture_output=True, text=True).stderr
    frames = int(re.findall(r'frame=\s*(\d+)', r)[-1])
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', r); dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    info = {k: bool(re.search(p, r)) for k, p in [('h264_high', r'h264 \(High\)'), ('yuv420p', r'yuv420p'), ('bt709', r'bt709'), ('aac_48k', r'aac \(LC\).*48000 Hz')]}
    pcm = subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-i', path, '-map', '0:a', '-f', 's16le', '-ac', '2', '-'], capture_output=True).stdout
    samples = len(pcm) // 4
    a = subprocess.run([FF, '-hide_banner', '-i', path, '-map', '0:a', '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
    s = a[a.rfind('Summary:'):]
    I = float(re.search(r'I:\s+(-?[\d.]+) LUFS', s)[1]); TP = float(re.search(r'Peak:\s+(-?[\d.]+) dBFS', s)[1])
    moov_first = open(path, 'rb').read(64 * 1024).find(b'moov') >= 0
    return frames, dur, samples, I, TP, info, moov_first


def flashes(path, W, H):
    w, h = (54, 96) if H > W else (96, 54)
    raw = subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-i', path, '-vf', f'scale={w}:{h}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    v = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3).astype(np.float64) / 255
    lin = np.where(v <= .04045, v / 12.92, ((v + .055) / 1.055) ** 2.4)
    L = lin @ np.array([.2126, .7152, .0722])                      # 相対輝度（0–1、白=1）
    red = (v[..., 0] / np.maximum(v.sum(-1), 1e-6) >= .8).mean((1, 2)).max()
    n = L.shape[0]; ext = L[0].copy(); dirn = np.zeros_like(ext); events = []
    for i in range(1, n):
        cur = L[i]
        up = (cur - ext >= .1) & (np.minimum(cur, ext) < .8); dn = (ext - cur >= .1) & (np.minimum(cur, ext) < .8)
        trans = up | dn; new_dir = np.where(up, 1, np.where(dn, -1, 0))
        flash = trans & (dirn != 0) & (new_dir != dirn)              # 逆向きの変化で「対」が完成＝1回
        if flash.mean() >= .25: events.append(i)
        dirn = np.where(trans, new_dir, dirn)
        # 極値の更新: 変化が確定した画素は現在値から、未確定の画素は同方向の極値を追う
        ext = np.where(trans, cur, np.where(dirn >= 0, np.maximum(ext, cur), np.minimum(ext, cur)))
    worst = max((sum(1 for e in events if s <= e < s + FPS) for s in range(n)), default=0)
    return worst, events, float(red)


def main(paths):
    ok = True; report = []
    for p in paths:
        fmt = '169' if '169' in os.path.basename(p) else '916'
        frames, d, samples, I, TP, info, moov = probe(p)
        res = {'file': os.path.basename(p), 'format': fmt, 'frames': frames, 'duration': d, 'audio_samples': samples, 'LUFS': I, 'TP': TP, 'issues': [], 'checks': {}}
        chk = res['checks']
        def check(name, passed, value, need):
            chk[name] = {'pass': bool(passed), 'value': value, 'need': need}
            if not passed: res['issues'].append(f'{name}: {value}（基準 {need}）')
        check('映像フレーム数', frames == NF, frames, '450')
        check('尺（コンテナ）', d <= 15.0005, f'{d:.3f}s', '≤15.000s')
        check('音声サンプル数', samples == NS, samples, f'{NS}（{NS / 48000:.4f}s）')
        check('統合ラウドネス', -15.0 <= I <= -13.0, f'{I} LUFS', '-14±1 LUFS')
        check('トゥルーピーク', TP <= -1.0, f'{TP} dBTP', '≤-1.0 dBTP')
        check('エンコード', all(info.values()) and moov, ', '.join(k for k, v in info.items() if v) + (', faststart' if moov else ''), 'H.264 High / yuv420p / BT.709 / AAC-LC 48kHz / faststart')
        bx = p[:-4] + '.qa_boxes.json'
        if not os.path.exists(bx):
            res['issues'].append('qa_boxes.json がない'); ok = False; report.append(res); continue
        B = json.load(open(bx, encoding='utf-8')); rects = SAFE[fmt]; W, H = B['W'], B['H']
        TXT = ('telop', 'label')
        outside, head_out, overl, spans, spk, first_seen = {}, {}, {}, {}, {}, {}
        naka = 0; brand_t = None; size_bad = []
        for i, fr in enumerate(B['frames']):
            vis = [b for b in fr if b['a'] > .5 and b['x1'] > 0 and b['y1'] > 0 and b['x0'] < W and b['y0'] < H and (b['x1'] - b['x0']) > 1]
            txt = [b for b in vis if b['kind'] in TXT]; heads = [b for b in vis if b['kind'] == 'head']; logos = [b for b in vis if b['kind'] == 'logo']
            for b in txt:
                spans.setdefault((b['kind'], b['label']), []).append(i)
                first_seen.setdefault(b['label'], i)
                if b.get('spk'): spk[b['label']] = b['spk']
                if 'ユニコ' in b['label'] and brand_t is None: brand_t = i / FPS
            if logos and brand_t is None: brand_t = i / FPS
            for b in txt + logos:
                if not inside(b, rects): outside.setdefault(b['label'], []).append(i)
            for b in heads:
                if not inside(b, rects, tol=4): head_out.setdefault(b['label'], []).append(i)
            els = txt + logos
            for x in range(len(els)):
                for y in range(x + 1, len(els)):
                    if els[x]['label'] != els[y]['label'] and inter(els[x], els[y]): overl.setdefault(f"{els[x]['label']}×{els[y]['label']}", []).append(i)
                for hb in heads:
                    if inter(els[x], hb): overl.setdefault(f"{els[x]['label']}×{hb['label']}の頭部", []).append(i)
            for x in range(len(heads)):
                for y in range(x + 1, len(heads)):
                    if heads[x]['label'] != heads[y]['label'] and inter(heads[x], heads[y]): overl.setdefault('頭部同士', []).append(i)
            hn = [b['y1'] - b['y0'] for b in heads if b['label'] == 'nakatsuka']; hr = [b['y1'] - b['y0'] for b in heads if b['label'] == 'ricchan']
            if hn and hr and max(hr) > max(hn) + 1: size_bad.append(i)
            if any(b['kind'] == 'face' and b['label'] == 'nakatsuka' for b in vis): naka += 1
        for lab, fs in outside.items(): res['issues'].append(f'セーフゾーン外「{lab}」 frames {fs[0]}–{fs[-1]} ({len(fs)}f)')
        for lab, fs in head_out.items():
            long = [r for r in runs(fs) if r[1] - r[0] + 1 > 12]
            if long: res['issues'].append(f'セーフゾーン外の顔（{lab}） frames ' + ', '.join(f'{a}–{b}' for a, b in long))
        for lab, fs in overl.items(): res['issues'].append(f'重なり {lab} frames {fs[0]}–{fs[-1]} ({len(fs)}f)')
        chk['セーフゾーン'] = {'pass': not outside and not any(r[1] - r[0] + 1 > 12 for fs in head_out.values() for r in runs(fs)), 'value': f'はみ出し {len(outside)} 件', 'need': 'テロップ・ロゴ・顔が共通安全域内'}
        chk['重なり'] = {'pass': not overl, 'value': f'{len(overl)} 件', 'need': '文字同士・文字と頭部・頭部同士 0'}
        # 読了
        reading = {}; rbad = []
        for (kind, lab), fs in spans.items():
            n = chars(lab)
            if not n: continue
            rs = runs(fs); need = n / READ_CPS
            if kind == 'telop':
                got = min(r[1] - r[0] + 1 for r in rs) / FPS
                if got + 1e-6 < need: rbad.append(f'読了不足「{lab}」 {n:g}字/{got:.2f}s（必要 {need:.2f}s）')
            else:
                cum = len({i for (k2, l2), f2 in spans.items() if lab in l2 for i in f2}) / FPS
                got = cum; shortest = min(r[1] - r[0] + 1 for r in rs) / FPS
                if cum + 1e-6 < need or shortest < 1.0 - 1e-6: rbad.append(f'読了不足（ラベル）「{lab}」 累計{cum:.2f}s・最短{shortest:.2f}s（必要 累計{need:.2f}s・1回1.00s）')
            reading[lab] = {'kind': kind, 'chars': n, 'shown_s': round(got, 2), 'need_s': round(need, 2), 'cps': round(n / got, 2) if got else None}
        res['issues'] += rbad
        chk['読了（4.8字/秒）'] = {'pass': not rbad, 'value': f'不足 {len(rbad)} 件', 'need': '台詞は1回ごと・ラベルは累計'}
        res['reading'] = reading
        # ABCD
        f0 = B['frames'][0]
        check('0フレーム目に顔', any(b['kind'] in ('face', 'head') for b in f0), 'あり' if any(b['kind'] in ('face', 'head') for b in f0) else 'なし', 'あり（ABCD: Attract）')
        check('ブランド初出', brand_t is not None and brand_t <= 4.5, f'{brand_t}s', '≤4.5s（ABCD: Brand）')
        # 相方保護
        check('中塚の顔が見えるフレーム', naka >= 180, f'{naka}/{len(B["frames"])}（{naka / len(B["frames"]):.0%}）', '≥180（40%）')
        dl = {lab: s for lab, s in spk.items()}
        tot = sum(chars(l) for l in dl); nk = sum(chars(l) for l, s in dl.items() if s == 'nakatsuka')
        check('台詞の字数の中塚比率', tot and nk / tot >= .40, f'{nk:g}/{tot:g}字（{(nk / tot if tot else 0):.0%}）', '≥40%')
        check('頭部の大きさ 中塚≥リッチャン☆', not size_bad, f'逆転 {len(size_bad)} フレーム', '0')
        last = max((first_seen[l], l) for l in dl if chars(l)) if dl else (None, None)
        check('最後の台詞', dl.get(last[1]) == 'nakatsuka', f'{last[1]}（{dl.get(last[1])}）', '中塚')
        # 点滅
        worst, ev, red = flashes(p, W, H)
        check('一般閃光（任意の1秒間）', worst <= 3, f'最大 {worst} 回/秒（検出フレーム {ev}）', '≤3回')
        chk['飽和赤の最大面積'] = {'pass': True, 'value': f'{red:.1%}', 'need': '参考値'}
        res['nakatsuka_face_frames'] = naka; res['brand_first_s'] = brand_t
        res['issues'] = sorted(set(res['issues']), key=res['issues'].index)
        ok &= not res['issues']; report.append(res)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
