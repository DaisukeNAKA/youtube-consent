#!/usr/bin/env python3
"""企画書＋絵コンテページ（単一HTML）を storyboard.json / out/qa_report.json / 書き出し動画から生成する。
usage: python3 tools/build_page.py <storyboard.json> <out.html> [--public]
- 既定は社内限定の版（残論点・表現ルール適合・置いた前提を含む）。storyboard.json は公開リポジトリに置かない（private/）。
- --public は社外向け（残論点・適合表・前提・仕様を出さない）。
- どちらの版も、旧名義・過去の番組名など出してはいけない語が含まれていたら書き出さずに終了コード1で止める。
- 絵コンテのキーフレームは out/unico_cm15_916.mp4 から抽出し、JPEG data URI で埋め込む。
- 動画は同じフォルダに置いた web 版（unico_cm15_916_web.mp4 / unico_cm15_169_web.mp4）を相対参照する。
"""
import base64, html, io, json, os, subprocess, sys
from PIL import Image
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = imageio_ffmpeg.get_ffmpeg_exe()
E = html.escape


def frame_uri(video, t, w):
    r = subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-ss', f'{t:.3f}', '-i', video, '-frames:v', '1', '-f', 'image2pipe', '-c:v', 'png', '-'], capture_output=True, check=True)
    im = Image.open(io.BytesIO(r.stdout)).convert('RGB'); im = im.resize((w, round(w * im.height / im.width)), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, 'JPEG', quality=82); return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()


def main(sb_path, out, public=False):
    sb = json.load(open(sb_path, encoding='utf-8'))
    qa = json.load(open(os.path.join(ROOT, 'out', 'qa_report.json'), encoding='utf-8')) if os.path.exists(os.path.join(ROOT, 'out', 'qa_report.json')) else []
    v916 = os.path.join(ROOT, 'out', 'unico_cm15_916.mp4'); v169 = os.path.join(ROOT, 'out', 'unico_cm15_169.mp4')
    BAR = 60 / 120 * 4
    # --- timeline ruler (120BPM・1小節2.0秒 × 7.5小節 = 15.0秒) ---
    shots = sb['shots']
    ruler = ''.join(f'<div class="bar" style="left:{i * BAR / 15 * 100:.3f}%;width:{BAR / 15 * 100:.3f}%"><span>{i + 1}</span></div>' for i in range(8) if i * BAR < 15)
    segs = ''.join(f'<div class="seg s{i % 4}" style="left:{s["t_start"] / 15 * 100:.3f}%;width:{(s["t_end"] - s["t_start"]) / 15 * 100:.3f}%" title="{E(s["id"])}"><b>{E(s["id"])}</b></div>' for i, s in enumerate(shots))
    marks = ''.join(f'<div class="mk" style="left:{m["t"] / 15 * 100:.3f}%"><i></i><em>{E(m["label"])}</em></div>' for m in sb.get('marks', []))
    # --- storyboard rows ---
    rows = []
    for s in shots:
        tm = (s['t_start'] + s['t_end']) / 2 if 'thumb_t' not in s else s['thumb_t']
        img = frame_uri(v916, tm, 200) if os.path.exists(v916) else ''
        img2 = frame_uri(v169, tm, 300) if os.path.exists(v169) else ''
        tel = ''.join(f'<li><span class="who {E(x.get("speaker", ""))}">{E(x.get("speaker_label", ""))}</span>{E(x["text"])}<small>{x["t_in"]:.2f}–{x["t_out"]:.2f}s</small></li>' for x in s.get('telops', []))
        se = '、'.join(f'{E(x["name"])}@{x["t"]:.2f}s' for x in s.get('se', [])) or '—'
        rows.append(f'''<article class="shot">
  <div class="thumbs"><img src="{img}" alt="{E(s['id'])} 9:16 のフレーム" width="200"><img class="h" src="{img2}" alt="{E(s['id'])} 16:9 のフレーム" width="300"></div>
  <div class="body">
    <header><span class="tc">{s['t_start']:05.2f}–{s['t_end']:05.2f}s</span><h3>{E(s['id'])}　{E(s['title'])}</h3></header>
    <p class="vis">{E(s['visual'])}</p>
    <ul class="tel">{tel}</ul>
    <p class="meta"><span>SE</span>{se}</p>
    <p class="meta"><span>狙い</span>{E(s['intent'])}</p>
  </div>
</article>''')
    alt = ''.join(f'''<tr class="{'rec' if a.get('recommended') else ''}"><th>{E(a['key'])}</th><td><b>{E(a['name'])}</b><br>{E(a['summary'])}</td><td>{E(a['pros'])}</td><td>{E(a['cons'])}</td><td class="num">{a.get('score', '')}</td></tr>''' for a in sb['alternatives'])
    af = ''.join(f'<tr><td class="num">{x["t_in"]:.2f}–{x["t_out"]:.2f}</td><td>{E(x["speaker"])}</td><td>「{E(x["line"])}」</td><td>{E(x["direction"])}</td></tr>' for x in sb['afureco'])
    posts = ''.join(f'''<div class="post"><div class="ph"><b>{E(k)}</b><button type="button" data-copy="p{i}">コピー</button></div><pre id="p{i}">{E(v)}</pre></div>''' for i, (k, v) in enumerate(sb['post_copy'].items()))
    comp = ''.join(f'<tr><td>{E(c["item"])}</td><td class="st {E(c["status"])}">{E(c["status"])}</td><td>{E(c["note"])}</td></tr>' for c in sb['compliance'])
    qrows = ''
    names = list(qa[0]['checks'].keys()) if qa else []
    VN = {'YT': 'E0-YT 9:16', 'SNS': 'E0-SNS 9:16', '169': 'E0-169 16:9'}
    qhead = ''.join(f'<th>{E(VN.get(r.get("variant"), r["file"]))}</th>' for r in qa)
    for n in names:
        cells = ''.join(f'<td class="st {"適合" if r["checks"][n]["pass"] else "不適合"}">{"合格" if r["checks"][n]["pass"] else "不合格"}<br><small>{E(str(r["checks"][n]["value"]))}</small></td>' for r in qa)
        qrows += f'<tr><td>{E(n)}<br><small>{E(str(qa[0]["checks"][n]["need"]))}</small></td>{cells}</tr>'
    qsum = ('全項目合格（' + '・'.join(VN.get(r.get('variant'), r['file']) for r in qa) + '）') if qa and not any(r['issues'] for r in qa) else '<br>'.join(E(x) for r in qa for x in r['issues'])
    warns = sorted({w for r in qa for w in r.get('warnings', [])})
    if warns: qsum += '<br><small>参考: ' + '／'.join(E(w) for w in warns) + '</small>'
    li = lambda xs: ''.join(f'<li>{E(x)}</li>' for x in xs)
    page = TEMPLATE.format(
        title=E(sb['title']), lead=E(sb['lead']), conclusion=li(sb['conclusion']), reasons=li(sb['reasons']),
        ruler=ruler, segs=segs, marks=marks, rows='\n'.join(rows), alt=alt, af=af, posts=posts, comp=comp, qrows=qrows, qhead=qhead, qsum=qsum,
        assumptions=li(sb['assumptions']), issues=''.join(f'<li><b>{E(x["what"])}</b>　{E(x["why"])}<span class="own">{E(x["who"])}</span></li>' for x in sb['open_issues']),
        specs=li(sb['specs']), message=E(sb['key_message']))
    if public:   # 社外向け: 社内の検討事項を出さない
        import re as _re
        for sec in ('表現ルール適合', '置いた前提', '仕様 <small>'):
            page = _re.sub(r'<section[^>]*>(?:(?!</section>).)*' + _re.escape(sec) + r'.*?</section>', '', page, flags=_re.S)
    bad = [w for w in NG_WORDS + (NG_PUBLIC if public else []) if w in page]
    if bad:
        print('NG語を含むため書き出しません:', bad, file=sys.stderr); sys.exit(1)
    open(out, 'w', encoding='utf-8').write(page)
    print('wrote', out, round(len(page) / 1024), 'KB')


# 出してはいけない語の一覧は公開リポジトリに書かない（語そのものが情報になるため）。private/ng_words.json に置く:
#   {"all": [...どの版でも出さない語...], "public": [...社外向けで出さない語...]}
_NG = json.load(open(os.path.join(ROOT, 'private', 'ng_words.json'), encoding='utf-8')) if os.path.exists(os.path.join(ROOT, 'private', 'ng_words.json')) else {}
if not _NG: print('注意: private/ng_words.json がないため、NG語の検査をしていません', file=sys.stderr)
NG_WORDS, NG_PUBLIC = _NG.get('all', []), _NG.get('public', [])


TEMPLATE = r'''<title>ユニコ 15秒CM</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&family=Zen+Kaku+Gothic+New:wght@400;700&family=Anton&display=swap">
<style>
:root {{
  --ground:#FBF8FF; --surface:#FFFFFF; --ink:#1B1033; --muted:#6B5F86; --line:#E4DCF5;
  --pink:#FF4FA3; --purple:#7C4DFF; --sky:#BDF4FF; --lime:#A8F28A; --yellow:#FFE45C;
  --ok:#1E8E5A; --warn:#B26A00; --ng:#C62D4A;
  --display:"Dela Gothic One","Hiragino Sans","Noto Sans JP",sans-serif;
  --body:"Zen Kaku Gothic New","Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
  --num:"Anton","Dela Gothic One",sans-serif;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme:dark; --ground:#130E20; --surface:#1C1530; --ink:#F2EDFF; --muted:#A99BC9; --line:#2F2548; --ok:#5FD49A; --warn:#FFB84D; --ng:#FF7A93; }} }}
:root[data-theme="dark"] {{ color-scheme:dark; --ground:#130E20; --surface:#1C1530; --ink:#F2EDFF; --muted:#A99BC9; --line:#2F2548; --ok:#5FD49A; --warn:#FFB84D; --ng:#FF7A93; }}
* {{ box-sizing:border-box; }}
body {{ background:var(--ground); color:var(--ink); font:16px/1.75 var(--body); padding-inline:16px; padding-block:24px 64px; }}
main {{ max-width:1080px; margin:0 auto; display:grid; grid-template-columns:minmax(0,1fr); gap:56px; }}
main > *, .grid2 > *, .hero > *, .shot > * {{ min-width:0; }}
.post pre, .tel li, td {{ overflow-wrap:anywhere; }}
.qa td:first-child {{ min-width:12em; }} .qa td {{ min-width:9em; }}
.tablewrap table:not(.qa) td:first-child {{ min-width:6em; }}
h1,h2,h3 {{ text-wrap:balance; margin:0; }}
h1 {{ font:400 clamp(34px,6vw,58px)/1.1 var(--display); letter-spacing:.01em; }}
h1 .dot {{ color:var(--pink); }}
h2 {{ font:400 clamp(22px,3.2vw,30px)/1.3 var(--display); display:flex; gap:.5em; align-items:baseline; }}
h2 small {{ font:700 12px/1 var(--body); letter-spacing:.14em; color:var(--muted); text-transform:uppercase; }}
.lead {{ color:var(--muted); max-width:62ch; margin:.6em 0 0; }}
.hero {{ display:grid; grid-template-columns:minmax(0,300px) minmax(0,1fr); gap:24px; align-items:start; }}
.player {{ display:grid; gap:8px; }}
.player video {{ width:100%; border-radius:14px; background:#000; display:block; box-shadow:0 12px 40px -18px rgba(124,77,255,.6); }}
.player figcaption {{ font-size:13px; color:var(--muted); }}
.concl {{ background:var(--surface); border:2px solid var(--ink); border-radius:18px; padding:20px 22px; box-shadow:6px 6px 0 var(--pink); }}
.concl ul {{ margin:.4em 0 0; padding-left:1.2em; }}
.msg {{ font:400 20px/1.5 var(--display); color:var(--purple); margin:0 0 .3em; }}
.grid2 {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:24px; }}
section > p, section li {{ max-width:70ch; }}
.timeline {{ position:relative; height:118px; margin-top:16px; border-radius:12px; background:var(--surface); border:1px solid var(--line); overflow:hidden; }}
.bar {{ position:absolute; top:0; bottom:0; border-left:1px dashed var(--line); }}
.bar span {{ position:absolute; top:4px; left:6px; font:13px/1 var(--num); color:var(--muted); letter-spacing:.04em; }}
.bar span::before {{ content:"小節 "; font-family:var(--body); font-size:10px; }}
.seg {{ position:absolute; top:28px; height:40px; border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:12px; color:#1B1033; border:2px solid var(--ground); overflow:hidden; white-space:nowrap; }}
.seg.s0 {{ background:var(--pink); }} .seg.s1 {{ background:var(--sky); }} .seg.s2 {{ background:var(--yellow); }} .seg.s3 {{ background:var(--lime); }}
.mk {{ position:absolute; top:70px; bottom:0; }}
.mk i {{ position:absolute; top:0; bottom:18px; border-left:2px solid var(--purple); }}
.mk em {{ position:absolute; bottom:2px; left:-2px; transform:translateX(-50%); font:700 11px/1.2 var(--body); font-style:normal; color:var(--purple); white-space:nowrap; }}
.tlnote {{ font-size:13px; color:var(--muted); margin-top:6px; }}
.shots {{ display:grid; gap:18px; margin-top:16px; }}
.shot {{ display:grid; grid-template-columns:auto minmax(0,1fr); gap:18px; padding:16px; border-radius:16px; background:var(--surface); border:1px solid var(--line); }}
.thumbs {{ display:flex; gap:10px; align-items:flex-start; }}
.thumbs img {{ border-radius:10px; height:auto; max-width:100%; }}
.thumbs img:first-child {{ width:120px; }} .thumbs img.h {{ width:180px; }}
.shot header {{ display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; }}
.tc {{ font:18px/1 var(--num); letter-spacing:.03em; color:var(--pink); font-variant-numeric:tabular-nums; }}
.shot h3 {{ font:700 17px/1.4 var(--body); }}
.vis {{ margin:.4em 0; color:var(--muted); font-size:14px; }}
.tel {{ list-style:none; padding:0; margin:.2em 0; display:grid; gap:4px; }}
.tel li {{ font:400 18px/1.4 var(--display); display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }}
.tel small {{ font:12px/1 var(--body); color:var(--muted); }}
.who {{ font:700 11px/1 var(--body); padding:4px 8px; border-radius:99px; background:var(--line); color:var(--ink); }}
.who.nakatsuka {{ background:var(--pink); color:#fff; }} .who.ricchan {{ background:var(--yellow); color:#1B1033; }} .who.both {{ background:var(--purple); color:#fff; }}
.meta {{ margin:.2em 0; font-size:14px; }}
.meta span {{ display:inline-block; min-width:3.2em; font-weight:700; color:var(--muted); font-size:12px; letter-spacing:.08em; }}
.tablewrap {{ overflow-x:auto; margin-top:14px; border:1px solid var(--line); border-radius:14px; background:var(--surface); }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th,td {{ text-align:left; vertical-align:top; padding:10px 12px; border-bottom:1px solid var(--line); }}
thead th {{ font-size:12px; letter-spacing:.08em; color:var(--muted); }}
tr.rec {{ background:color-mix(in srgb, var(--pink) 12%, transparent); }}
tr.rec th::after {{ content:"推奨"; display:inline-block; margin-left:6px; font:700 10px/1 var(--body); background:var(--pink); color:#fff; padding:3px 6px; border-radius:99px; }}
td.num {{ font-variant-numeric:tabular-nums; white-space:nowrap; }}
.st {{ font-weight:700; white-space:nowrap; }} .st.適合 {{ color:var(--ok); }} .st.要確認 {{ color:var(--warn); }} .st.不適合 {{ color:var(--ng); }}
.posts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; margin-top:14px; }}
.post {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:12px 14px; display:grid; gap:6px; }}
.ph {{ display:flex; justify-content:space-between; align-items:center; }}
.ph button {{ font:700 12px/1 var(--body); border:0; border-radius:99px; padding:7px 12px; background:var(--purple); color:#fff; cursor:pointer; }}
.ph button:focus-visible {{ outline:3px solid var(--pink); outline-offset:2px; }}
.post pre {{ white-space:pre-wrap; margin:0; font:14px/1.6 var(--body); }}
ol.issues li, ul.plain li {{ margin:.4em 0; }}
.own {{ display:inline-block; margin-left:8px; font-size:12px; color:var(--muted); border:1px solid var(--line); border-radius:99px; padding:1px 8px; }}
footer {{ color:var(--muted); font-size:13px; }}
@media (max-width:760px) {{ .hero, .grid2 {{ grid-template-columns:1fr; }} .shot {{ grid-template-columns:1fr; }} .player {{ max-width:320px; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior:auto; }} }}
</style>
<main>
<header>
  <h1>ユニコ 15秒CM<span class="dot">.</span></h1>
  <p class="lead">{lead}</p>
</header>

<section class="hero" aria-label="完成動画と結論">
  <figure class="player"><video src="unico_cm15_916_web.mp4" controls playsinline preload="metadata"></video><figcaption>9:16（Shorts／Reels／TikTok）1080×1920・15.0秒</figcaption></figure>
  <div style="display:grid;gap:20px">
    <div class="concl"><p class="msg">{message}</p><ul>{conclusion}</ul></div>
    <figure class="player"><video src="unico_cm15_169_web.mp4" controls playsinline preload="metadata"></video><figcaption>16:9（YouTube広告／X／会場モニター）1920×1080・15.0秒</figcaption></figure>
  </div>
</section>

<section><h2>根拠 <small>Why</small></h2><ul>{reasons}</ul></section>

<section><h2>3案の比較 <small>A / B / C</small></h2>
<div class="tablewrap"><table><thead><tr><th>案</th><th>概要</th><th>強み</th><th>弱み</th><th>審査平均</th></tr></thead><tbody>{alt}</tbody></table></div></section>

<section><h2>秒割り <small>120BPM・1小節2.0秒</small></h2>
<div class="timeline" role="img" aria-label="15秒の秒割り。小節線、ショット、効果音の位置">{ruler}{segs}{marks}</div>
<p class="tlnote">カット・ヒット・エンドカードは小節線（2.0秒ごと）か拍（0.5秒）に同期。オチ直前の9.5〜10.0秒だけ音楽を止めて「間」を作っています。</p></section>

<section><h2>絵コンテ <small>Storyboard</small></h2><div class="shots">{rows}</div></section>

<section class="grid2">
  <div><h2>本人アフレコ台本 <small>任意</small></h2>
  <div class="tablewrap"><table><thead><tr><th>秒</th><th>話者</th><th>台詞</th><th>演出</th></tr></thead><tbody>{af}</tbody></table></div>
  <p class="tlnote">収録したWAVを voice/ に置き cues.json の voice に登録して ./build.sh を実行すると、声を優先して音楽を自動で下げた版が出力されます。合成音声で本人の声を作ることはしていません。</p></div>
  <div><h2>仕様 <small>Specs</small></h2><ul class="plain">{specs}</ul></div>
</section>

<section><h2>投稿文 <small>Post copy</small></h2><div class="posts">{posts}</div></section>

<section><h2>自動QA <small>書き出し実測値</small></h2>
<p>{qsum}</p>
<div class="tablewrap"><table class="qa"><thead><tr><th>検査（基準）</th>{qhead}</tr></thead><tbody>{qrows}</tbody></table></div></section>

<section><h2>表現ルール適合 <small>Compliance</small></h2>
<div class="tablewrap"><table><thead><tr><th>項目</th><th>状態</th><th>根拠・対応</th></tr></thead><tbody>{comp}</tbody></table></div></section>

<section class="grid2">
  <div><h2>置いた前提 <small>Assumptions</small></h2><ul>{assumptions}</ul></div>
  <div><h2>残論点 <small>Open issues</small></h2><ol class="issues">{issues}</ol></div>
</section>
<footer>素材: 本人撮影の2ショット写真・コンビロゴ（いずれも本人提供）。音: 自作ジングル・自作効果音のみ（第三者音源なし）。書体: Dela Gothic One／M PLUS Rounded 1c／Anton（SIL OFL 1.1）。</footer>
</main>
<script>
document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', async () => {{
  const el = document.getElementById(b.dataset.copy);
  try {{ await navigator.clipboard.writeText(el.textContent); b.textContent = 'コピーしました'; }}
  catch (e) {{ const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s.removeAllRanges(); s.addRange(r); b.textContent = '選択しました'; }}
  setTimeout(() => b.textContent = 'コピー', 1600);
}}));
</script>
'''

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], '--public' in sys.argv[3:])
