/* ユニコ15秒CM『推しが、お笑いの相方に。』篇（最終絵コンテ v2・常用版E0 準拠）— シーン定義
 * 120BPM・1小節=2.0秒（60フレーム）の拍グリッドに同期（音は tools/audio.py / cues.json）。
 * 文言は COPY、秒は T（フレーム番号÷30）、座標は LAY（9:16 / 16:9）で差し替え可能。
 * 人物は「頭部枠」（髪を含む外接矩形。engine.js の HEAD_PHOTO）の表示座標 [x0,y0,x1,y1] で置く。
 * 安全域 9:16: x120–780（y≤840 は x≤888）・y288–1248 / 16:9: x96–1758・y183–693（上端は x496–1443・y38–183 も可）
 * 素材は本人提供の2ショット写真1枚のみ（表情差は漫画記号とカメラワークで補う）。ロゴは図柄を改変しない（目・視線の加工なし）。
 * ?variant=SNS で TikTok・Instagram・X 通常投稿用（E0-SNS：フォローしてね／フォロー！）に切り替える。
 */
'use strict';
const f = (n) => n / 30;
const VARIANT = Q.get('variant') === 'SNS' ? 'SNS' : 'YT';
const T = {
  s1: 0, slide: f(15), land: f(27), chip: f(30),
  s2: f(60), name: f(63),
  s3: f(120), furi: f(123), tagN: f(132), q: f(150),
  s4: f(180), handle: f(180), boke: f(186), tagR: f(192), boke2: f(198), morph: f(225), morphEnd: f(238),
  s5: f(240), tsuk: f(243), tagN2: f(255), ma: f(285),
  s6: f(300), ochi: f(300), react: f(330),
  wipe: f(354), endA: f(360), kira: f(390), endB: f(405), shrinkEnd: f(409), endBpop: V ? f(409) : f(405), endN: f(420), freeze: f(435),
};
const COPY = {
  hook: ['推しが、', 'お笑いの相方に。'],
  exYT: '元YouTuber',
  name: ['吉本の芸人、', 'ユニコです！'],
  furi: ['芸人、', '向いてなくない？'],
  boke1: '向いてる！', boke2: '毎日必死！',
  tagN: ['ツッコミ', '中塚サンフラワー'], tagR: ['ボケ｜元YouTuber', 'リッチャン☆'],
  tsukkomi: ['必死って、', '才能か？'],
  ochi: ['…でも、', '芸人として', '推せる。'],
  handle: '@yy_unico', cta: VARIANT === 'SNS' ? 'フォローしてね' : 'チャンネル登録してね', channel: 'ユニコちゃんねる',
  endR: VARIANT === 'SNS' ? 'フォロー！' : '登録して！', endN: '必死か。', nameN: '中塚サンフラワー', nameR: 'リッチャン☆',
};

const LAY = V ? {
  s1: { n: [125, 590, 413, 920], r: [525, 965, 769, 1205], anchor: [450, 580], tel: [504, 410], tsz: 80, tail: [300, 574], chip: [598, 905], chipSz: 42, slide: [700, 0] },
  s2: { logo: [268, 432, 240], tel: [638, 399], tsz: 70, tails: [[300, 574], [640, 954]] },
  s3: { n: [150, 628, 517, 1048], nRot: -.07, anchor: [342, 863], r: [575, 735, 778, 935], q: [690, 690], tel: [504, 476], tsz: 80, tail: [330, 600], tag: [340, 1172], tagSz: [40, 48] },
  s4: { r: [272, 690, 638, 1050], rRot: .052, anchor: [452, 870], tel1: [470, 428], tel2: [470, 558], tsz: 88, tag: [572, 1172], tagSz: [40, 48], mini: [660, 322], spotDx: -60 },
  s5: { n: [160, 650, 544, 1090], nRot: .052, anchor: [365, 900], tel: [440, 484], tsz: 84, tail: [420, 612], dots: [672, 925], bishi: [575, 815], tag: [340, 1172], tagSz: [40, 48] },
  s6: { n: [162, 726, 529, 1146], tel: [470, 478], sizes: [72, 96, 120], tail: [372, 692], r: [610, 1040, 737, 1165] },
  handle: [240, 324], handleSz: 44, miniSz: 40,
  endA: { logo: [450, 600, 600], handle: [450, 998, 120], cta: [450, 1116, 52], ch: [450, 1195, 44] },
  endB: { logo: [450, 392, 190], handle: [450, 570, 96], cta: [450, 667, 48], ch: [450, 737, 40],
    n: [185, 1035, 317, 1185], r: [560, 1054, 692, 1184], bR: [600, 900], bRsz: 60, bN: [272, 948], bNsz: 60, mini: [620, 820],
    nameN: [298, 1219], nameR: [648, 1219], nameSz: 40 },
} : {
  s1: { n: [230, 250, 518, 580], r: [1480, 420, 1713, 649], anchor: [500, 250], tel: [1000, 367], tsz: 96, tail: [540, 420], chip: [1596, 356], chipSz: 44, slide: [350, 0] },
  s2: { logo: [1000, 300, 200], tel: [1000, 553], tsz: 92, tails: [[470, 470], [1490, 530]] },
  s3: { n: [250, 262, 599, 662], nRot: -.07, anchor: [440, 262], r: [1520, 440, 1693, 610], q: [1652, 385], tel: [1080, 380], tsz: 96, tail: [645, 430], tag: [1080, 590], tagSz: [44, 56] },
  s4: { r: [1180, 250, 1525, 590], rRot: .052, anchor: [1350, 400], tel1: [560, 326], tel2: [560, 476], tsz: 104, tail: [1150, 330], tag: [560, 618], tagSz: [44, 56], mini: [1300, 112], spotDx: -200 },
  s5: { n: [330, 262, 679, 662], nRot: .052, anchor: [530, 262], tel: [1330, 393], tsz: 100, tail: [640, 470], dots: [842, 486], bishi: [745, 470], tag: [1330, 603], tagSz: [44, 56] },
  s6: { n: [362, 225, 729, 645], tel: [1400, 416], sizes: [80, 110, 140], tail: [700, 440], r: [830, 520, 952, 640] },
  handle: [625, 112], handleSz: 48, miniSz: 44,   // 16:9 のハンドルとミニチップは上端の共通安全帯（x496–1443・y38–183）に置く
  endA: { logo: [400, 438, 500], handle: [720, 274, 140], cta: [720, 412, 60], ch: [720, 495, 48] },   // 右列は x720 起点の左揃え
  endB: { iconN: [770, 582, 96], iconR: [1230, 582, 96], bN: [990, 580], bNsz: 60, bR: [1470, 580], bRsz: 56,
    nameN: [890, 660], nameR: [1340, 660], nameSz: 40, mini: [1612, 660], miniSz: 40 },
};

function render(t0) {
  REC_MUTE = t0 >= T.wipe - 1e-6 && t0 < T.endA - 1e-6;   // ワイプ通過中の6フレームは読了・重なりの計測から外す
  let t = t0;
  if (t >= T.s6 && t < T.s6 + f(3)) t = T.s6;              // ヒットストップ（f300–302）
  if (t >= T.freeze) t = T.freeze;                         // f435–449 は完全静止の決め画面（ループ頭へつながる）
  ctx.save();
  if (t < T.s2) sceneHook(t);
  else if (t < T.s3) sceneName(t);
  else if (t < T.s4) sceneFuri(t);
  else if (t < T.s5) sceneBoke(t);
  else if (t < T.s6) sceneTsukkomi(t);
  else if (t < T.endA) sceneOchi(t);
  else sceneEnd(t);
  ctx.restore();
  // 常時ハンドル（f180–299、カットと同時にポップなしで出す）とミニチップ『毎日必死！』（f238–299）。オチでは消して見せ場を空ける
  if (t >= T.handle && t < T.s6) pill(COPY.handle, LAY.handle[0], LAY.handle[1], LAY.handleSz, { font: F.latin, weight: '', bg: C.white, edge: C.purple });
  if (t >= T.morphEnd && t < T.s6) pill(COPY.boke2, LAY.s4.mini[0], LAY.s4.mini[1], LAY.miniSz);
  // エンドカードへの3色ワイプ（f354–359、180°シャッター相当のブラー）。通過済み側にエンドカードAを出す
  if (t0 >= T.wipe && t0 < T.endA) {
    const k1 = (t0 - T.wipe) / (T.endA - T.wipe) + 1 / 12;
    wipeBlur(k1 - 1 / 12, k1, () => sceneEnd(T.endA), [C.purple, C.yellow, C.pink]);   // 先頭=ピンク（オチの地に近い輝度）→黄→紫（エンドカードに近い輝度）で明暗の往復を減らす
  }
  grain();
}

// ---- 共通部品 ----
// 名札: 2フレームで不透明になり、12pxだけ下から寄る（読める状態を早く作り、安全域の下端も越えない）
function nameTag(lab, name, x, y, t, t0, bg, [ls, ns]) {
  const k = E.outCubic(prog(t, t0, t0 + .4)); if (k <= 0) return;
  const a = clamp(prog(t, t0, t0 + f(2)));
  ls *= U; ns *= U;
  ctx.save(); ctx.font = `900 ${ls}px ${F.round}`; const lw = ctx.measureText(lab).width; ctx.font = `900 ${ns}px ${F.round}`; const nw = ctx.measureText(name).width; ctx.restore();
  const w = Math.max(lw, nw) + 40 * U, h = ls + ns + 26 * U;
  withT(() => {
    ctx.fillStyle = 'rgba(27,16,51,.3)'; rrect(-w / 2 + 6 * U, -h / 2 + 8 * U, w, h, 18 * U); ctx.fill();
    ctx.fillStyle = bg; ctx.strokeStyle = C.white; ctx.lineWidth = 5 * U; rrect(-w / 2, -h / 2, w, h, 18 * U); ctx.fill(); ctx.stroke();
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const fg = bg === C.pink ? C.ink : C.white;
    ctx.font = `900 ${ls}px ${F.round}`; ctx.fillStyle = fg; ctx.fillText(lab, 0, -h / 2 + 9 * U + ls / 2);
    ctx.font = `900 ${ns}px ${F.round}`; ctx.fillText(name, 0, h / 2 - 10 * U - ns / 2 + 2 * U);
    const e = 2.5 * U;
    recBox('label', lab + name, [[-w / 2 - e, -h / 2 - e], [w / 2 + e, -h / 2 - e], [-w / 2 - e, h / 2 + e], [w / 2 + e, h / 2 + e]], { px: ls / U, rd: a >= .9 });
  }, x, y + (1 - k) * 12 * U, 1, 0, a);
}

function bgPinkRadial(t) {
  const cx = W * .45, cy = H * .5, R = Math.hypot(W, H) * .65;
  const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R); g.addColorStop(0, '#FFE3F1'); g.addColorStop(1, '#FF4FA3');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  dots(C.white, 50, 6, .28, 0, -t * 20);
}

// 明るい劇場（幕 #9B7BFF〜#B89CFF、クリーム色のスポット2灯 #FFF6D6、床のライン）＝「今は舞台に立つ芸人」
function bgTheater(t, spotX, spotK = .8) {
  const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, '#B89CFF'); g.addColorStop(1, '#9B7BFF');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  ctx.save(); ctx.globalAlpha = .18; ctx.strokeStyle = '#6B45E0'; ctx.lineWidth = 12 * U;
  for (let i = 0; i < 14; i++) { const x = (i + .5) * W / 14; ctx.beginPath(); ctx.moveTo(x, 0); ctx.bezierCurveTo(x + 18 * U, H * .3, x - 18 * U, H * .6, x + 8 * U, H); ctx.stroke(); }
  ctx.restore();
  for (const [sx, a] of [[spotX, spotK], [spotX + (V ? 260 : 420) * U, spotK * .55]]) {
    const r = (V ? 620 : 560) * U, sy = H * (V ? .5 : .45);
    const sg = ctx.createRadialGradient(sx, sy, 0, sx, sy, r);
    sg.addColorStop(0, `rgba(255,246,214,${a})`); sg.addColorStop(.6, `rgba(255,246,214,${a * .35})`); sg.addColorStop(1, 'rgba(255,246,214,0)');
    ctx.fillStyle = sg; ctx.fillRect(0, 0, W, H);
  }
  ctx.fillStyle = 'rgba(58,28,140,.35)'; ctx.fillRect(0, H * (V ? .82 : .86), W, 6 * U);
  ctx.fillStyle = C.pink; ctx.fillRect(0, 0, W, 34 * U);
  for (let i = 0; i < W / (70 * U) + 1; i++) { ctx.beginPath(); ctx.arc(i * 70 * U + 35 * U, 34 * U, 35 * U, 0, Math.PI); ctx.fill(); }
}
const boxC = (b) => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
const rel = (b) => { const c = boxC(b); return [b[0] - c[0], b[1] - c[1], b[2] - c[0], b[3] - c[1]]; };
const tailTo = (p, len) => p ? { x: p[0], y: p[1], len } : null;

// ---------- S01 f0–59 つかみ：推しが、お笑いの相方に。 ----------
function sceneHook(t) {
  bgPinkRadial(t);
  const L = LAY.s1, z = 1 + (V ? .01 : .015) * prog(t, 0, 2);
  cam(L.anchor, z, () => {
    head('nakatsukaBust', L.n);
    if (t >= T.slide) {   // f15–27 に右から滑り込み、f27 の着地で1回だけスクワッシュ
      const e = E.outBack(prog(t, T.slide, T.land), 1.0), sq = t >= T.land && t < T.land + f(4) ? [1.05, .95] : [1, 1];   // 行き過ぎは小さく（ステッカー間隔20px以上を保つ）
      head('ricchanShort', L.r, { dx: (1 - e) * L.slide[0] * U, dy: (1 - e) * L.slide[1] * U, rot: (1 - e) * .07, sx: sq[0], sy: sq[1] });
    }
  });
  // テロップは f0 で全文表示（サムネになる1フレーム目＝中塚＋テロップ）。f0–4 に 1.08→1.00 倍で弾む
  sayBox('nakatsuka', COPY.hook, L.tel[0], L.tel[1], t, 0, { size: L.tsz, from: 1.08, back: 0, dur: f(4), tail: tailTo(L.tail, 60) });
  pill(COPY.exYT, L.chip[0], L.chip[1], L.chipSz, { tri: true, k: E.outBack(prog(t, T.chip, T.chip + f(6)), 1.4) });
}

// ---------- S02 f60–119 名乗り：吉本の芸人、ユニコです！（人物はS01の配置のまま、背景とロゴだけ切り替える） ----------
function sceneName(t) {
  const lt = t - T.s2, L = LAY.s2, S1 = LAY.s1, z = V ? 1.01 + .01 * prog(lt, 0, 2) : 1.015 + .015 * prog(lt, 0, 2);
  bgSky(t);
  cam(S1.anchor, z, () => { head('nakatsukaBust', S1.n); head('ricchanShort', S1.r); });
  const e = E.outCubic(prog(lt, 0, f(3)));   // f60–63 にハンコのように押す（1.12→1.00、−4°→0°、着地で±2°を1回）
  logo(L.logo[0], L.logo[1], L.logo[2] * U * lerp(1.12, 1, e), { rot: lerp(-.07, 0, e) + wobble(lt, f(3), .035, 10, 9) });
  sayBox('both', COPY.name, L.tel[0], L.tel[1], t, T.name, { font: 'display', size: L.tsz, tails: L.tails.map(([x, y]) => ({ x, y, len: 46 })) });
  pill(COPY.exYT, S1.chip[0], S1.chip[1], S1.chipSz, { tri: true });
}

// ---------- S03 f120–179 フリ：芸人、向いてなくない？（明るい劇場） ----------
function sceneFuri(t) {
  const lt = t - T.s3, L = LAY.s3;
  bgTheater(t, boxC(L.n)[0], clamp(lt / f(10)) * .8);
  const z = lerp(1.10, 1.0, E.outCubic(prog(lt, 0, f(7)))) * (1 + .03 * prog(lt, f(7), 2));
  head('ricchanShort', L.r);                                  // イジる相手（リッチャン☆）を小さく、中塚から離して置く
  cam(L.anchor, z, () => head('nakatsukaBust', L.n, { rot: L.nRot }));
  if (t >= T.q) text('？', L.q[0], L.q[1], { size: 76, font: F.round, weight: 900, fill: C.yellow, strokes: [[C.ink, .14]], qa: 'deco', pop: { t, t0: T.q, stagger: 0, dur: f(6) }, rot: .12 });
  sayBox('nakatsuka', COPY.furi, L.tel[0], L.tel[1], t, T.furi, { size: L.tsz, tail: tailTo(L.tail, 60) });
  nameTag(COPY.tagN[0], COPY.tagN[1], L.tag[0], L.tag[1], t, T.tagN, C.purple, L.tagSz);
}

// ---------- S04 f180–239 ボケ：向いてる！／毎日必死！（食い気味・自己肯定感MAX） ----------
function sceneBoke(t) {
  const lt = t - T.s4, L = LAY.s4, rc = boxC(L.r);
  bgTheater(t, rc[0] + L.spotDx * U, .8);
  const by = ctx.createRadialGradient(rc[0], rc[1], 0, rc[0], rc[1], 520 * U);
  by.addColorStop(0, 'rgba(255,228,92,.85)'); by.addColorStop(1, 'rgba(255,228,92,0)'); ctx.fillStyle = by; ctx.fillRect(0, 0, W, H);
  speedLines(t, rc[0], rc[1], 34, .35);
  const whip = 1 - E.outCubic(prog(lt, 0, f(6)));                                   // f180–185 ホイップ
  const z = (1 + .05 * E.outCubic(prog(t, T.boke, T.boke + 1))) * kSquash(t - T.boke, 0);
  const jit = t > T.boke2 && t < T.boke2 + .3 ? Math.sin(t * 90) * 6 * U : 0;       // 0.3秒・振幅6pxの揺れを1回
  if (whip > 0) for (let g = 2; g >= 1; g--) cam(L.anchor, z, () => head('ricchanBust', L.r, { rot: L.rRot, dx: whip * W * .45 + g * 70 * U * whip, alpha: .25 }));
  cam(L.anchor, z, () => head('ricchanBust', L.r, { rot: L.rRot, dx: whip * W * .45 + jit }));
  sweat(L.r[0] - 30 * U, L.r[1] + 10 * U, 1.0, t, T.boke + .3);
  sweat(L.r[2] + 30 * U, L.r[1] + 60 * U, .8, t, T.boke + .6);
  for (let i = 0; i < 3; i++) sparkle(L.r[2] + 40 * U, L.r[1] + 140 * U + i * 90 * U, .8, prog(t, T.boke + .2 + i * .15, T.boke + .8 + i * .15));
  // 『向いてる！』は f225 から4フレームで退場し、『毎日必死！』がミニチップへ移る通り道を空ける
  sayBox('ricchan', [COPY.boke1], L.tel1[0], L.tel1[1], t, T.boke, { size: L.tsz, tail: V || t >= T.morph ? null : tailTo(L.tail, 60), alpha: 1 - prog(t, T.morph, T.morph + f(4)), scale: 1 - .3 * prog(t, T.morph, T.morph + f(4)) });
  if (t < T.morph) sayBox('ricchan', [COPY.boke2], L.tel2[0], L.tel2[1], t, T.boke2, { size: L.tsz });
  else if (t < T.morphEnd) {   // f225–237: 40pxのミニチップへ縮めながら上へ（最後の天丼の前振り）
    const e = E.inOutCubic(prog(t, T.morph, T.morphEnd)), sz = lerp(L.tsz, LAY.miniSz, e);
    // 16:9 は上へふくらむ2次ベジェ（リッチャン☆の顔とハンドルの間を通る）
    const c1 = V ? [(L.tel2[0] + L.mini[0]) / 2, (L.tel2[1] + L.mini[1]) / 2] : [820, 120];
    const px = (1 - e) ** 2 * L.tel2[0] + 2 * e * (1 - e) * c1[0] + e * e * L.mini[0], py = (1 - e) ** 2 * L.tel2[1] + 2 * e * (1 - e) * c1[1] + e * e * L.mini[1];
    pill(COPY.boke2, px, py, sz, {
      bg: mixHex(C.pink, C.white, e), edge: mixHex(C.white, C.pink, e), padX: lerp(L.tsz * .6, 34, e), hMul: lerp(1.3, 1.5, e), r: lerp(34 * U, sz * .75 * U, e), ...(sz >= 56 ? { qa: 'telop', spk: 'ricchan' } : {}) });   // 縮んだ後はラベル扱い
  }
  nameTag(COPY.tagR[0], COPY.tagR[1], L.tag[0], L.tag[1], t, T.tagR, C.pink, L.tagSz);
}
function kSquash(d, at) { if (d < at) return 1; d -= at; return 1 + .05 * Math.sin(d * 30) * Math.exp(-d * 10); }
function mixHex(a, b, k) { const A = hexRgb(a), B = hexRgb(b); return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], k))).join(',')})`; }

// ---------- S05 f240–299 ツッコミ：必死って、才能か？ ＋ 無音の間（f285–299） ----------
function sceneTsukkomi(t) {
  const lt = t - T.s5, L = LAY.s5;
  bgTheater(t, boxC(L.n)[0], lerp(.8, .56, prog(t, T.ma, T.ma + f(12))));
  const z = t < T.s5 + f(6) ? lerp(1.10, 1.0, E.outCubic(prog(lt, 0, f(5)))) : t < T.ma ? lerp(1.0, 1.05, prog(t, T.s5 + f(6), T.ma)) : lerp(1.05, 1.06, prog(t, T.ma, T.s6));
  cam(L.anchor, z, () => head('nakatsukaBust', L.n, { rot: L.nRot }));
  const kb = prog(t, T.s5, T.s5 + f(15));                   // ビシッ線（白3本、f240–255）
  if (kb > 0 && kb < 1) {
    ctx.save(); ctx.globalAlpha = 1 - kb; ctx.strokeStyle = C.white; ctx.lineWidth = 12 * U; ctx.lineCap = 'round';
    const [ox, oy] = L.bishi;
    for (let i = 0; i < 3; i++) { const a = -.9 + i * .45, r0 = 30 * U + kb * 30 * U, r1 = 120 * U + kb * 40 * U; ctx.beginPath(); ctx.moveTo(ox + Math.cos(a) * r0, oy + Math.sin(a) * r0); ctx.lineTo(ox + Math.cos(a) * r1, oy + Math.sin(a) * r1); ctx.stroke(); }
    ctx.restore();
  }
  const kUp = E.inOutCubic(prog(t, T.ma, T.ma + f(10))), s = 1 - .15 * kUp, ph = (2 * 1.22 + .3) * L.tsz * U;   // 上端固定で85%へ
  sayBox('nakatsuka', COPY.tsukkomi, L.tel[0], L.tel[1] - ph / 2 * (1 - s), t, T.tsuk, { size: L.tsz, scale: s, tail: tailTo(L.tail, 60) });
  nameTag(COPY.tagN[0], COPY.tagN[1], L.tag[0], L.tag[1], t, T.tagN2, C.purple, L.tagSz);
  if (t >= T.ma) sayBox('both', ['…'], L.dots[0], L.dots[1], t, T.ma, { size: 72 });   // 無音でも「間」だと分かる
}

// ---------- S06 f300–353 オチ：…でも、芸人として推せる。（ツッコミが本音で崩れる1拍） ----------
function sceneOchi(t) {
  const L = LAY.s6, ht = t - T.s6, fc = faceCenter('nakatsukaBust', L.n);
  ctx.fillStyle = '#E86BC4'; ctx.fillRect(0, 0, W, H);
  bgBurst(t, '#F070C0', '#B67CF0', fc[0], fc[1], 26, .18);            // 低コントラスト・0.2回転/秒未満
  const z = ht < f(3) ? 1.10 : lerp(1.10, 1.04, E.outBack(prog(ht, f(3), f(18)), 1.5));   // ヒットストップ→1.04倍へ
  const sh = ht >= f(3) && ht < f(13) ? 12 * U * Math.sin((ht - f(3)) * Math.PI * 2 * 6) * Math.exp(-(ht - f(3)) * 8) : 0;   // f303–312 減衰する揺れ（最大±12px）
  cam(fc, z, () => head('nakatsukaBust', L.n, { rot: -.02 }), sh, 0);
  for (let i = 0; i < 5; i++) sparkle(fc[0] + Math.cos(i * 1.3 + .4) * 250 * U, fc[1] + 40 * U + Math.sin(i * 2.1) * 150 * U, 1.0, prog(t, T.s6 + .15 + i * .09, T.s6 + .75 + i * .09));
  // f300（最大のドンとヒットストップ）で1行目を全表示、f303・f306 に2・3行目。文末の『推せる。』が最大
  sayBox('nakatsuka', COPY.ochi, L.tel[0], L.tel[1], t, T.ochi, { sizes: L.sizes, lineDelay: f(3), from: 1, lh: 1.15, tail: tailTo(L.tail, 60) });
  const kr = E.outBack(prog(t, T.react, T.react + f(8)), 1.6);        // 反応ステッカー（無言の「でしょ？」。中塚の肩との重なりは絵コンテで許容）
  if (kr > 0) { const c = boxC(L.r); withT(() => head('ricchanBust', rel(L.r), { rot: -.07, noGap: true }), c[0], c[1], kr); }
}

// ---------- エンドカード A f360–404（ロゴ1.5秒静止）／ B f405–449（キッカー：登録して！→必死か。） ----------
function sceneEnd(t) {
  const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, C.purple); g.addColorStop(1, C.pink);
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  confetti(t, T.endA - .6, 26, 9, [C.yellow, C.white, '#BFF6FF']);
  const A = LAY.endA, B = LAY.endB;
  const k = V ? E.inOutCubic(prog(t, T.endB, T.shrinkEnd)) : 0;     // 9:16のみ f405–409 でロゴを縮めて文字を上に詰める（13.5秒の拍）
  const P = (a, b) => b ? a.map((v, i) => lerp(v, b[i], k)) : a;
  const lg = P(A.logo, B.logo), hd = P(A.handle, B.handle), ct = P(A.cta, B.cta), ch = P(A.ch, B.ch);
  logo(lg[0], lg[1], lg[2] * U);
  const al = V ? 'center' : 'left';
  const ho = { size: hd[2], font: F.latin, fill: C.white, strokes: [[C.ink, .13], [C.white, .085], [C.ink, .045]], ls: .02, align: al };
  text(COPY.handle, hd[0], hd[1], ho);
  glint(COPY.handle, V ? hd[0] : hd[0] + textW(COPY.handle, ho) / 2, hd[1], ho, prog(t, T.kira, T.kira + f(6)));   // f390–396 の光（キラッと同期）
  ctaTape(COPY.cta, ct[0], ct[1], ct[2], al);
  text(COPY.channel, ch[0], ch[1], { size: ch[2], font: F.display, fill: C.white, strokes: [[C.ink, .2]], shadow: false, align: al });
  if (t < T.endBpop) return;
  // 下段（2人・吹き出し・名前）は、9:16 ではロゴと文字の縮小が終わってから出す＝移動中の文字と重ねない
  const kp = E.outBack(prog(t, T.endBpop, T.endBpop + f(8)), 1.6), kr = E.outBack(prog(t, T.endBpop, T.endBpop + f(8)), 1.2);
  let hop = 0; for (const tb of [T.endBpop, T.endBpop + f(6), T.endBpop + f(12)]) if (t >= tb && t < tb + f(6)) hop = -8 * U * Math.sin(Math.PI * (t - tb) / f(6));   // 8pxずつ3回跳ねる
  const fr = Math.round(t * 30), f0 = Math.round(T.endBpop * 30), jig = fr >= f0 && fr <= f0 + 12 ? ((fr >> 1) & 1 ? 5 : -5) * U : 0;   // 2フレームごとに±5px
  pill(COPY.boke2, B.mini[0], B.mini[1], B.miniSz || LAY.miniSz, { k: E.outBack(prog(t, T.endBpop, T.endBpop + f(6)), 1.4) });   // S04の『毎日必死！』を再表示
  if (V) {
    if (kp > 0) {
      const cn = boxC(B.n), cr = boxC(B.r);
      withT(() => head('nakatsukaBust', rel(B.n), { rot: -.07 }), cn[0], cn[1], kr);   // 行き過ぎを抑え、名前ラベルに頭を重ねない
      withT(() => head('ricchanShort', rel(B.r), { rot: .07 }), cr[0], cr[1] + hop, kr);
      nameLabel(COPY.nameN, B.nameN[0], B.nameN[1], kp, B.nameSz); nameLabel(COPY.nameR, B.nameR[0], B.nameR[1], kp, B.nameSz, C.ink, C.white);
    }
    sweat(B.r[2] + 22 * U, B.r[1] + 40 * U + hop, .7, t, T.endBpop + f(2));
    sayBox('ricchan', [COPY.endR], B.bR[0] + jig, B.bR[1], t, T.endBpop, { size: B.bRsz, tail: { x: boxC(B.r)[0] - 10, y: B.r[1] - 10, len: 30 } });
    sayBox('nakatsuka', [COPY.endN], B.bN[0], B.bN[1], t, T.endN, { size: B.bNsz, tail: { x: boxC(B.n)[0], y: B.n[1] - 8, len: 26 } });
  } else {
    faceIcon('nakatsukaSolo', B.iconN[0], B.iconN[1], B.iconN[2] * U, { t: kp, bg: '#E9E1FF' });
    faceIcon('ricchan', B.iconR[0], B.iconR[1] + hop, B.iconR[2] * U, { t: kr, bg: '#FFE3F1' });
    sweat(B.iconR[0] + 58 * U, B.iconR[1] - 40 * U + hop, .6, t, T.endBpop + f(2));
    nameLabel(COPY.nameN, B.nameN[0], B.nameN[1], kp, B.nameSz); nameLabel(COPY.nameR, B.nameR[0], B.nameR[1], kp, B.nameSz, C.ink, C.white);
    const iN = B.iconN, iR = B.iconR;
    sayBox('ricchan', [COPY.endR], B.bR[0] + jig, B.bR[1], t, T.endBpop, { size: B.bRsz, tail: { x: iR[0] + iR[2] / 2 + 12, y: iR[1], len: 60 } });
    sayBox('nakatsuka', [COPY.endN], B.bN[0], B.bN[1], t, T.endN, { size: B.bNsz, tail: { x: iN[0] + iN[2] / 2 + 12, y: iN[1], len: 60 } });
  }
}

function textW(str, o) { ctx.save(); ctx.font = `${o.weight || ''} ${(o.size || 96) * U}px ${o.font || F.display}`; const w = [...str].reduce((a, ch) => a + ctx.measureText(ch).width, 0) + (o.ls || 0) * (o.size || 96) * U * ([...str].length - 1); ctx.restore(); return w; }

function nameLabel(s, x, y, k, size = 40, fill = C.white, edge = C.ink) {
  if (k <= 0) return;
  text(s, x, y, { size, font: F.round, weight: 900, fill, strokes: [[edge, .15]], shadow: false, sx: clamp(k), sy: clamp(k), qa: 'label' });
}

// CTAテープ（静的：ボタンの形・カーソル・押下・状態変化なし）。align='left' は x を左端として扱う
function ctaTape(label, x, y, size, align = 'center') {
  ctx.save(); ctx.font = `900 ${size * U}px ${F.round}`; const w = ctx.measureText(label).width + 60 * U, h = size * 1.45 * U; ctx.restore();
  const cx = align === 'left' ? x + w / 2 : x;
  withT(() => {
    ctx.fillStyle = 'rgba(27,16,51,.28)'; ctx.fillRect(-w / 2 + 6 * U, -h / 2 + 8 * U, w, h);
    ctx.fillStyle = C.pink; ctx.beginPath();
    const z = 9 * U; ctx.moveTo(-w / 2, -h / 2); for (let i = 0; i <= 6; i++) ctx.lineTo(-w / 2 + (i % 2 ? z : 0), -h / 2 + h * i / 6);
    for (let i = 6; i >= 0; i--) ctx.lineTo(w / 2 - (i % 2 ? z : 0), -h / 2 + h * i / 6); ctx.closePath(); ctx.fill();
    ctx.fillStyle = C.ink; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.font = `900 ${size * U}px ${F.round}`; ctx.fillText(label, 0, 3 * U);
    recBox('telop', label, [[-w / 2, -h / 2], [w / 2, -h / 2], [-w / 2, h / 2], [w / 2, h / 2]], { px: size, rd: true });
  }, cx, y, 1, 0);
}
