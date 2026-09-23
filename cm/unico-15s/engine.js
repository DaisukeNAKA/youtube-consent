/* ユニコ15秒CM — 描画エンジン（依存なし・Canvas 2D・フレーム決定的）
 * render(t) は t 秒の1フレームを必ず同じ絵で描く（乱数は固定シード）。
 * 書き出しは tools/render.mjs が window.__frame(i) を呼んで PNG を受け取る。
 */
'use strict';
const FPS = 30, DUR = 15.0, NFRAMES = Math.round(FPS * DUR);
const Q = new URLSearchParams(location.search);
const FMT = Q.get('fmt') === '169' ? '169' : '916';
const W = FMT === '169' ? 1920 : 1080, H = FMT === '169' ? 1080 : 1920;
const V = FMT === '916';          // vertical?
const U = V ? W / 1080 : H / 1080; // 基準単位（短辺1080基準）
const C = {
  pink: '#FF4FA3', purple: '#7C4DFF', white: '#FFFFFF', ink: '#1B1033', yellow: '#FFE45C',
  sky1: '#27D3F5', sky2: '#BFF6FF', lime: '#5BE35B', deep: '#2A0E5C', hot: '#FF2E8B',
};

const canvas = document.getElementById('c');
canvas.width = W; canvas.height = H;
const ctx = canvas.getContext('2d');

// ---------- math / easing ----------
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const lerp = (a, b, k) => a + (b - a) * k;
const prog = (t, t0, t1) => clamp((t - t0) / (t1 - t0));
const E = {
  lin: k => k,
  outCubic: k => 1 - Math.pow(1 - k, 3),
  inCubic: k => k * k * k,
  inOutCubic: k => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2,
  outBack: (k, s = 1.70158) => 1 + (s + 1) * Math.pow(k - 1, 3) + s * Math.pow(k - 1, 2),
  outElastic: k => k === 0 ? 0 : k === 1 ? 1 : Math.pow(2, -10 * k) * Math.sin((k * 10 - .75) * (2 * Math.PI / 3)) + 1,
  outQuint: k => 1 - Math.pow(1 - k, 5),
  inQuad: k => k * k,
};
// 減衰振動（着地のバウンドなど）
const wobble = (t, t0, amp = 1, freq = 9, decay = 7) => t < t0 ? 0 : amp * Math.sin((t - t0) * freq * Math.PI * 2 / 4) * Math.exp(-(t - t0) * decay);
function rngFactory(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }

// ---------- assets ----------
const IMG = {};
const ASSET_LIST = { nakatsuka: 'assets/nakatsuka.png', nakatsukaSolo: 'assets/nakatsuka_solo.png', ricchan: 'assets/ricchan.png', logo: 'assets/logo.png' };
const FONTS = [
  ['Dela Gothic One', 'fonts/Dela_Gothic_One_400.woff', '400'],
  ['M PLUS Rounded 1c', 'fonts/M_PLUS_Rounded_1c_900.woff', '900'],
  ['M PLUS Rounded 1c', 'fonts/M_PLUS_Rounded_1c_800.woff', '800'],
  ['Anton', 'fonts/Anton_400.woff', '400'],
];
const F = {
  display: '"Dela Gothic One"',
  round: '"M PLUS Rounded 1c"',
  latin: 'Anton, "Dela Gothic One"',
};

async function loadAll() {
  await Promise.all(FONTS.map(async ([fam, url, wt]) => {
    const ff = new FontFace(fam, `url(${url})`, { weight: wt });
    await ff.load(); document.fonts.add(ff);
  }));
  await Promise.all(Object.entries(ASSET_LIST).map(([k, src]) => new Promise((res, rej) => {
    const im = new Image(); im.onload = () => { IMG[k] = im; res(); }; im.onerror = rej; im.src = src;
  })));
  LAYOUT = await (await fetch('assets/layout.json')).json();
  for (const k of Object.keys(FACE_PHOTO)) {
    const [x0, y0, x1, y1] = LAYOUT[k], [a, b, c, d] = FACE_PHOTO[k];
    FACE[k] = [(a - x0) / (x1 - x0), (b - y0) / (y1 - y0), (c - x0) / (x1 - x0), (d - y0) / (y1 - y0)];
  }
  // 人物は白フチ（ステッカー）版を事前生成
  for (const k of ['nakatsuka', 'nakatsukaSolo', 'ricchan']) IMG[k + 'Sticker'] = makeSticker(IMG[k], 14);
  // バストステッカー（水平カット）: 中塚は写真y=1355（ハートの手より上）、
  // リッチャン☆は ①サムズアップ込み（y≈1984）と ②短いバスト（y=1530・親指をマスク）の2種
  for (const [k, cut, key] of [['nakatsukaSolo', BUST_CUT.nakatsuka, 'nakatsukaBust'], ['ricchan', BUST_CUT.ricchan, 'ricchanBust'], ['ricchan', BUST_CUT.ricchanShort, 'ricchanShort']]) {
    const src = IMG[k], h = Math.round(src.height * cut);
    const c = document.createElement('canvas'); c.width = src.width; c.height = h;
    const g = c.getContext('2d'); g.drawImage(src, 0, 0);
    if (key === 'ricchanShort') {   // サムズアップの親指（写真 x1860–1990・y≥1400）を消す
      const lay = LAYOUT.ricchan, sc = src.width / (lay[2] - lay[0]);
      g.clearRect(0, Math.round((1395 - lay[1]) * sc), Math.round((1995 - lay[0]) * sc), h);
    }
    // カット面をわずかに丸めて“切った紙”らしく
    g.globalCompositeOperation = 'destination-in'; g.fillStyle = '#000'; g.beginPath(); rrectOn(g, -40, -40, c.width + 80, h + 40 - 2, 28); g.fill();
    cleanAlpha(c, 4, 2);   // 細い毛束・半透明の残骸を除く（白フチがトゲにならないように）
    c.cutFrac = cut; c.layer = k === 'ricchan' ? LAYOUT.ricchan : LAYOUT.nakatsukaSolo;
    IMG[key] = c; IMG[key + 'Sticker'] = makeSticker(c, 14);
    const [a0, b0, a1, b1] = FACE[k]; FACE[key] = [a0, b0 / cut, a1, b1 / cut];
    FACE_LABEL[key] = k === 'ricchan' ? 'ricchan' : 'nakatsuka';
  }
  // グレイン（固定シード）
  IMG.grain = makeGrain(512, 7);
}

function makeSticker(img, px) {
  const pad = px * 2 + 4;
  const c = document.createElement('canvas'); c.width = img.width + pad * 2; c.height = img.height + pad * 2;
  const g = c.getContext('2d');
  // 白フチ: 円周上にずらして重ね描き → 白で塗りつぶし
  const m = document.createElement('canvas'); m.width = c.width; m.height = c.height; const mg = m.getContext('2d');
  for (let a = 0; a < 32; a++) { const th = a / 32 * Math.PI * 2; mg.drawImage(img, pad + Math.cos(th) * px, pad + Math.sin(th) * px); }
  for (let r = px * .5; r > 0; r -= px * .5) for (let a = 0; a < 16; a++) { const th = a / 16 * Math.PI * 2; mg.drawImage(img, pad + Math.cos(th) * r, pad + Math.sin(th) * r); }
  mg.globalCompositeOperation = 'source-in'; mg.fillStyle = '#fff'; mg.fillRect(0, 0, m.width, m.height);
  g.drawImage(m, 0, 0); g.drawImage(img, pad, pad);
  c.pad = pad; c.src = img;
  return c;
}

// 2値化した不透明部（α≥128）に半径 r の開閉（オープニング）をかけ、そこから grow px 以内だけを残す。
// 細い毛束や半透明の残骸（幅 2r 未満）が消え、輪郭の柔らかさは残る。
function cleanAlpha(c, r = 4, grow = 2) {
  const w = c.width, h = c.height, g = c.getContext('2d'), id = g.getImageData(0, 0, w, h), A = id.data, n = w * h;
  const fg = new Uint8Array(n); for (let i = 0; i < n; i++) fg[i] = A[i * 4 + 3] >= 128;
  const bg = new Uint8Array(n); for (let i = 0; i < n; i++) bg[i] = !fg[i];
  const dB = chamfer(bg, w, h), er = new Uint8Array(n); for (let i = 0; i < n; i++) er[i] = dB[i] > r;
  const dE = chamfer(er, w, h);
  for (let i = 0; i < n; i++) if (dE[i] > r + grow) A[i * 4 + 3] = 0;
  g.putImageData(id, 0, 0);
}
// 3-4 チャンファー距離変換（seed=1 の画素からの距離、px 近似）
function chamfer(seed, w, h) {
  const INF = 1e9, d = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) d[i] = seed[i] ? 0 : INF;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = y * w + x; let v = d[i]; if (!v) continue;
    if (x > 0) v = Math.min(v, d[i - 1] + 3);
    if (y > 0) { v = Math.min(v, d[i - w] + 3); if (x > 0) v = Math.min(v, d[i - w - 1] + 4); if (x < w - 1) v = Math.min(v, d[i - w + 1] + 4); }
    d[i] = v;
  }
  for (let y = h - 1; y >= 0; y--) for (let x = w - 1; x >= 0; x--) {
    const i = y * w + x; let v = d[i]; if (!v) continue;
    if (x < w - 1) v = Math.min(v, d[i + 1] + 3);
    if (y < h - 1) { v = Math.min(v, d[i + w] + 3); if (x < w - 1) v = Math.min(v, d[i + w + 1] + 4); if (x > 0) v = Math.min(v, d[i + w - 1] + 4); }
    d[i] = v;
  }
  for (let i = 0; i < w * h; i++) d[i] /= 3;
  return d;
}
// QA: MASKS に描かれた2人の外形（白フチ込み）の最小距離（表示px）。どちらかがいなければ null
function stickerGap() {
  if (!MASKS) return null;
  const a = MASKS.nakatsuka.getImageData(0, 0, MASKS.w, MASKS.h).data, b = MASKS.ricchan.getImageData(0, 0, MASKS.w, MASKS.h).data, n = MASKS.w * MASKS.h;
  const sa = new Uint8Array(n); let na = 0, nb = 0;
  for (let i = 0; i < n; i++) { if (a[i * 4 + 3] >= 128) { sa[i] = 1; na++; } if (b[i * 4 + 3] >= 128) nb++; }
  if (!na || !nb) return null;
  const d = chamfer(sa, MASKS.w, MASKS.h); let m = Infinity;
  for (let i = 0; i < n; i++) if (b[i * 4 + 3] >= 128 && d[i] < m) m = d[i];
  return m * 2;
}
function newMasks() {
  const mk = () => { const c = document.createElement('canvas'); c.width = W / 2; c.height = H / 2; return c.getContext('2d', { willReadFrequently: true }); };
  MASKS = { nakatsuka: mk(), ricchan: mk(), w: W / 2, h: H / 2 };
}

function makeGrain(n, seed) {
  const c = document.createElement('canvas'); c.width = c.height = n; const g = c.getContext('2d');
  const id = g.createImageData(n, n); const r = rngFactory(seed);
  for (let i = 0; i < n * n; i++) { const v = r() * 255; id.data[i * 4] = id.data[i * 4 + 1] = id.data[i * 4 + 2] = v; id.data[i * 4 + 3] = 22; }
  g.putImageData(id, 0, 0); return c;
}

// ---------- QA recorder（書き出し時にテロップ/顔の外接矩形を記録）----------
let REC = null, REC_MUTE = false;   // REC_MUTE: ワイプ通過中は「読めない」ので記録しない
let MASKS = null;                   // QA: 人物別の外形マスク（2人のステッカー間隔の実測用）
function recBox(kind, label, pts, extra) {
  if (!REC || REC_MUTE) return;
  const m = ctx.getTransform();
  const tp = pts.map(([x, y]) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]);
  const xs = tp.map(p => p[0]), ys = tp.map(p => p[1]);
  REC.push({ kind, label, x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys), a: ctx.globalAlpha, ...(extra || {}) });
}
// 顔枠（元写真 3434x2576 の座標、髪・口ひげ・あごを含む）。レイヤー外接矩形は assets/layout.json
const FACE_PHOTO = { nakatsuka: [1202, 390, 1733, 1108], nakatsukaSolo: [1202, 390, 1733, 1108], ricchan: [2045, 858, 2607, 1467] };
const FACE = {};
let LAYOUT = null;
const FACE_LABEL = { nakatsukaSolo: 'nakatsuka' };
// レイヤー高さに対する水平カット位置。中塚は写真y=1355（ハートの手の上端y≈1440より上。y≈1367以下の右肩に残る補完ブロックも外す）
const BUST_CUT = { nakatsuka: (1355 - 224) / 2352, ricchan: 0.68, ricchanShort: (1530 - 725) / 1851 };
// 頭部枠（髪を含む外接矩形、元写真座標）。最終絵コンテの人物座標はこの枠で指定する
const HEAD_PHOTO = { nakatsuka: [1039, 240, 1834, 1150], ricchan: [1950, 729, 2591, 1360] };
function rrectOn(g, x, y, w, h, r) { g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }

// ---------- primitives ----------
function withT(fn, x, y, s = 1, rot = 0, alpha = 1) {
  ctx.save(); ctx.translate(x, y); if (rot) ctx.rotate(rot); if (s !== 1) ctx.scale(s, s);
  ctx.globalAlpha *= alpha; fn(); ctx.restore();
}

// ロゴと同じ空色→白→黄緑のグラデ空
function bgSky(t) {
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#04ECFB'); g.addColorStop(.45, '#9AFDFC'); g.addColorStop(.72, '#9CF28A'); g.addColorStop(1, '#36E922');   // ロゴの空から採色
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  // ふわふわ雲（ロゴのエアブラシ感）。左へ約15px/秒の視差
  const r = rngFactory(11);
  for (let i = 0; i < 9; i++) {
    const span = W * 1.3, x0 = (r() * 1.4 - .2) * W - t * 15 * U * (0.5 + r());
    const cx = ((x0 + W * .15) % span + span) % span - W * .15, cy = r() * H * .55, rad = (180 + r() * 260) * U;
    const rg = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad);
    rg.addColorStop(0, 'rgba(255,255,255,.55)'); rg.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = rg; ctx.fillRect(cx - rad, cy - rad, rad * 2, rad * 2);
  }
}

// 集中線サンバースト
function bgBurst(t, c1, c2, cx = W / 2, cy = H / 2, rays = 24, spin = .15) {
  ctx.fillStyle = c1; ctx.fillRect(0, 0, W, H);
  const R = Math.hypot(W, H);
  ctx.save(); ctx.translate(cx, cy); ctx.rotate(t * spin); ctx.fillStyle = c2;
  for (let i = 0; i < rays; i++) {
    const a0 = i / rays * Math.PI * 2, a1 = a0 + Math.PI / rays;
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(Math.cos(a0) * R, Math.sin(a0) * R); ctx.lineTo(Math.cos(a1) * R, Math.sin(a1) * R); ctx.closePath(); ctx.fill();
  }
  ctx.restore();
  const vg = ctx.createRadialGradient(cx, cy, R * .1, cx, cy, R * .6);
  vg.addColorStop(0, 'rgba(255,255,255,.35)'); vg.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);
}

// ドット（ハーフトーン）
function dots(col, step = 44, rad = 7, alpha = .18, ox = 0, oy = 0) {
  ctx.save(); ctx.globalAlpha *= alpha; ctx.fillStyle = col;
  for (let y = -step; y < H + step; y += step) for (let x = -step; x < W + step; x += step) {
    const xx = x + ((y / step) % 2 ? step / 2 : 0) + (ox % step), yy = y + (oy % step);
    ctx.beginPath(); ctx.arc(xx, yy, rad * U, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}

function grain() { ctx.save(); ctx.globalCompositeOperation = 'overlay'; const p = ctx.createPattern(IMG.grain, 'repeat'); ctx.fillStyle = p; ctx.fillRect(0, 0, W, H); ctx.restore(); }

// 人物ステッカー: anchor = 画像内の正規化座標(ax,ay)を (x,y) に置く。h = 表示高さ(px)
function person(key, x, y, h, { ax = .5, ay = 1, rot = 0, alpha = 1, shadow = true, sticker = true, flip = false, clip = null, noGap = false } = {}) {
  const st = IMG[key + 'Sticker'], src = IMG[key];
  const s = h / src.height;
  ctx.save(); ctx.globalAlpha *= alpha; ctx.translate(x, y); ctx.rotate(rot); ctx.scale(flip ? -s : s, s);
  if (clip) { ctx.beginPath(); clip(ctx, src.width, src.height, ax, ay); ctx.clip(); }
  const dx = -ax * src.width, dy = -ay * src.height;
  if (FACE[key]) { const [a0, b0, a1, b1] = FACE[key]; recBox('face', FACE_LABEL[key] || key, [[dx + a0 * src.width, dy + b0 * src.height], [dx + a1 * src.width, dy + b0 * src.height], [dx + a0 * src.width, dy + b1 * src.height], [dx + a1 * src.width, dy + b1 * src.height]]); }
  if (shadow) { ctx.shadowColor = 'rgba(40,10,80,.35)'; ctx.shadowBlur = 40; ctx.shadowOffsetX = 18; ctx.shadowOffsetY = 26; }
  if (sticker) ctx.drawImage(st, dx - st.pad, dy - st.pad); else ctx.drawImage(src, dx, dy);
  const who = FACE_LABEL[key] || key;
  if (MASKS && MASKS[who] && !noGap && ctx.globalAlpha >= .5) {   // QA: 白フチ込みの外形を人物別の半解像度マスクへ
    const m = ctx.getTransform(), mc = MASKS[who]; mc.setTransform(m.a * .5, m.b * .5, m.c * .5, m.d * .5, m.e * .5, m.f * .5); mc.drawImage(st, dx - st.pad, dy - st.pad);
  }
  ctx.restore();
}

// 文字: 多重フチ・影・グラデ・字間・自動縮小
function text(str, x, y, o = {}) {
  const size = (o.size || 96) * U;
  const font = `${o.weight || ''} ${size}px ${o.font || F.display}`.trim();
  ctx.save(); ctx.font = font; ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
  const ls = (o.ls || 0) * size;
  const chars = [...str];
  const widths = chars.map(ch => ctx.measureText(ch).width);
  let tw = widths.reduce((a, b) => a + b, 0) + ls * (chars.length - 1);
  let k = 1; if (o.maxW && tw > o.maxW) { k = o.maxW / tw; }
  ctx.translate(x, y); if (o.rot) ctx.rotate(o.rot); ctx.scale(k * (o.sx || 1), k * (o.sy || 1));
  const align = o.align || 'center';
  let cx = align === 'center' ? -tw / 2 : align === 'right' ? -tw : 0;
  const strokes = o.strokes || [[C.white, .2], [C.ink, .11]]; // [color, width(ratio of size)] 外側から
  { // 実際のインクの上下端（measureText）＋フチの幅で記録
    const sw = Math.max(0, ...strokes.map(s => s[1])) * size, mm = ctx.measureText(str), a0 = mm.actualBoundingBoxAscent, d0 = mm.actualBoundingBoxDescent;
    recBox(o.qa || 'telop', str, [[cx - sw, -a0 - sw], [cx + tw + sw, -a0 - sw], [cx - sw, d0 + sw], [cx + tw + sw, d0 + sw]], { px: o.size || 96, rd: true }); }
  const fill = o.fill || C.white;
  const pop = o.pop; // {t, t0, stagger, dur}
  const positions = []; let px = cx;
  for (let i = 0; i < chars.length; i++) { positions.push(px); px += widths[i] + ls; }
  const drawPass = (fn) => chars.forEach((ch, i) => {
    let sc = 1, a = 1, dy = 0, r = 0;
    if (pop) {
      const k2 = prog(pop.t, pop.t0 + i * (pop.stagger ?? .04), pop.t0 + i * (pop.stagger ?? .04) + (pop.dur ?? .28));
      sc = k2 <= 0 ? 0 : E.outBack(k2, 2.2); a = k2 > 0 ? 1 : 0; dy = (1 - E.outCubic(k2)) * size * .25;
    }
    if (o.wave) { dy += Math.sin(o.wave.t * 7 + i * .7) * size * (o.wave.amp ?? .04); }
    if (o.jitter) { const rr = rngFactory(i * 97 + (o.jitter.seed || 1)); r = (rr() - .5) * o.jitter.rot; dy += (rr() - .5) * o.jitter.y * size; }
    if (sc <= 0 || a <= 0) return;
    ctx.save(); ctx.translate(positions[i] + widths[i] / 2, dy); ctx.rotate(r); ctx.scale(sc, sc); ctx.globalAlpha *= a;
    fn(ch, -widths[i] / 2); ctx.restore();
  });
  // 影
  if (o.shadow !== false) drawPass((ch, dx) => { ctx.fillStyle = o.shadowCol || 'rgba(27,16,51,.35)'; ctx.fillText(ch, dx + size * .06, size * .09); });
  // フチ（外側から）
  ctx.lineJoin = 'round'; ctx.miterLimit = 2;
  for (const [col, wr] of strokes) drawPass((ch, dx) => { ctx.strokeStyle = col; ctx.lineWidth = size * wr * 2; ctx.strokeText(ch, dx, 0); });
  drawPass((ch, dx) => {
    if (Array.isArray(fill)) { const g = ctx.createLinearGradient(0, -size * .5, 0, size * .5); fill.forEach((c, i) => g.addColorStop(i / (fill.length - 1), c)); ctx.fillStyle = g; }
    else ctx.fillStyle = fill;
    ctx.fillText(ch, dx, 0);
  });
  ctx.restore();
  return tw * k;
}

// 角丸長方形
function rrect(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }

// 紙吹雪（固定シード）
function confetti(t, t0, n = 90, seed = 3, cols = [C.pink, C.purple, C.yellow, C.white, '#27D3F5']) {
  if (t < t0) return; const r = rngFactory(seed); const dt = t - t0;
  for (let i = 0; i < n; i++) {
    const x0 = r() * W, vy = (260 + r() * 520) * U, vx = (r() - .5) * 220 * U, sp = (r() - .5) * 14, sz = (14 + r() * 22) * U, c = cols[Math.floor(r() * cols.length)], delay = r() * .5;
    const tt = dt - delay; if (tt < 0) continue;
    const x = x0 + vx * tt + Math.sin(tt * 3 + i) * 30 * U, y = -60 * U + vy * tt;
    if (y > H + 60) continue;
    ctx.save(); ctx.translate(x, y); ctx.rotate(sp * tt); ctx.scale(1, Math.abs(Math.cos(tt * 5 + i)) + .15);
    ctx.fillStyle = c; ctx.fillRect(-sz / 2, -sz / 3, sz, sz * .66); ctx.restore();
  }
}

// キラキラ星
function sparkle(x, y, s, t, col = C.white) {
  const k = Math.max(0, Math.sin(t * Math.PI));
  if (k <= 0) return;
  ctx.save(); ctx.translate(x, y); ctx.scale(s * k * U, s * k * U); ctx.rotate(t * 1.5); ctx.fillStyle = col;
  ctx.beginPath(); for (let i = 0; i < 8; i++) { const a = i / 8 * Math.PI * 2, r = i % 2 ? 9 : 40; ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r); } ctx.closePath(); ctx.fill(); ctx.restore();
}

// ロゴ（支給PNGを無改変で使用。目・視線の加工やまばたきはしない）＋白リング＋インクの影
function logo(x, y, size, { rot = 0, alpha = 1 } = {}) {
  const im = IMG.logo;
  ctx.save(); ctx.globalAlpha *= alpha; ctx.translate(x, y); ctx.rotate(rot);
  ctx.shadowColor = 'rgba(27,16,51,.35)'; ctx.shadowBlur = 30 * U; ctx.shadowOffsetY = 16 * U;
  ctx.beginPath(); ctx.arc(0, 0, size / 2 + size * .025, 0, Math.PI * 2); ctx.fillStyle = C.white; ctx.fill();   // 白リング＝直径の2.5%
  ctx.shadowColor = 'transparent';
  ctx.drawImage(im, -size / 2, -size / 2, size, size);
  recBox('logo', 'logo', [[-size / 2, -size / 2], [size / 2, -size / 2], [-size / 2, size / 2], [size / 2, size / 2]]);
  ctx.restore();
}

// 9:16 UI セーフゾーン表示（プレビュー時のみ）
// 数値は Google広告/Meta/TikTok 公式図の実測値の共通部分（調査: research:spec）
const SAFE = V
  ? { rects: [[120, 288, 780, 1248], [780, 288, 888, 840]] }
  : { rects: [[96, 183, 1758, 693], [496, 38, 1443, 183]] };
function safeOverlay() {
  ctx.save(); ctx.fillStyle = 'rgba(255,0,0,.22)'; ctx.fillRect(0, 0, W, H);
  ctx.globalCompositeOperation = 'destination-out';
  for (const [x0, y0, x1, y1] of SAFE.rects) ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
  ctx.restore();
}

// 放射状スピードライン（オーバーレイ）
function speedLines(t, cx, cy, n = 48, alpha = .5, col = '#fff') {
  const r = rngFactory(Math.floor(t * 15) + 5), R = Math.hypot(W, H);
  ctx.save(); ctx.globalAlpha *= alpha; ctx.fillStyle = col;
  for (let i = 0; i < n; i++) {
    const a = r() * Math.PI * 2, w = (.004 + r() * .01), r0 = R * (.28 + r() * .12);
    ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
    ctx.lineTo(cx + Math.cos(a - w) * R, cy + Math.sin(a - w) * R); ctx.lineTo(cx + Math.cos(a + w) * R, cy + Math.sin(a + w) * R); ctx.closePath(); ctx.fill();
  }
  ctx.restore();
}


// 汗（しずく）
function sweat(x, y, s, t, t0) {
  const k = prog(t, t0, t0 + .5); if (k <= 0) return;
  const yy = y + E.inQuad(k) * 30 * U;
  withT(() => {
    ctx.beginPath(); ctx.moveTo(0, -40); ctx.bezierCurveTo(22, -8, 26, 18, 0, 26); ctx.bezierCurveTo(-26, 18, -22, -8, 0, -40); ctx.closePath();
    ctx.fillStyle = '#7FD6FF'; ctx.strokeStyle = C.white; ctx.lineWidth = 6; ctx.fill(); ctx.stroke();
    ctx.fillStyle = 'rgba(255,255,255,.8)'; ctx.beginPath(); ctx.ellipse(-7, 2, 5, 9, -.4, 0, Math.PI * 2); ctx.fill();
  }, x, yy, s * U * E.outBack(clamp(k * 3), 2));
}

// 顔アイコン（円形クロップ＋白リング）。d = 直径px
function faceIcon(key, x, y, d, { ring = C.white, bg = C.sky2, t = 1 } = {}) {
  const k = E.outBack(clamp(t), 1.8); if (k <= 0) return;
  const src = IMG[key]; const [a0, b0, a1, b1] = FACE[key];
  const fw = (a1 - a0) * src.width, fh = (b1 - b0) * src.height;
  const side = Math.max(fw, fh) * 1.08, cx = (a0 + a1) / 2 * src.width, cy = (b0 + b1) / 2 * src.height + fh * .03;
  withT(() => {
    ctx.fillStyle = 'rgba(27,16,51,.3)'; ctx.beginPath(); ctx.arc(4 * U, 7 * U, d / 2 + 6 * U, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = ring; ctx.beginPath(); ctx.arc(0, 0, d / 2 + 6 * U, 0, Math.PI * 2); ctx.fill();
    ctx.save(); ctx.beginPath(); ctx.arc(0, 0, d / 2, 0, Math.PI * 2); ctx.clip();
    ctx.fillStyle = bg; ctx.fillRect(-d / 2, -d / 2, d, d);
    ctx.drawImage(src, cx - side / 2, cy - side / 2, side, side, -d / 2, -d / 2, d, d);
    ctx.restore();
    recBox('face', FACE_LABEL[key] || key, [[-d / 2, -d / 2], [d / 2, -d / 2], [-d / 2, d / 2], [d / 2, d / 2]]);
  }, x, y, k);
}

// 吹き出し付きテロップ（話者色プレート）。tail: 話者の顔の方向 {x,y}
const PLATE = {
  nakatsuka: { bg: '#7C4DFF', fg: '#FFFFFF', edges: [['#1B1033', 7]] },                 // 紫地×白字 4.8:1
  ricchan: { bg: '#FF4FA3', fg: '#1B1033', edges: [['#FFFFFF', 7]] },                   // ピンク地×インク字 5.9:1
  both: { bg: '#FFFFFF', fg: '#1B1033', edges: [['#7C4DFF', 20], ['#FF4FA3', 10]] },     // 2人: 白地×インク字、紫とピンクの二重フチ
};
function sayBox(spk, lines, x, y, t, t0, o = {}) {
  if (t < t0) return;
  // 出現: 0.6→1.0倍（outBack 1.4、0.2秒）。o.from/o.dur/o.back で上書き。行ごとのサイズは o.sizes
  const P = PLATE[spk]; const disp = o.font === 'display';
  const sizes = lines.map((_, i) => ((o.sizes && o.sizes[i]) || o.size || 88) * U), smax = Math.max(...sizes);
  const fnt = (sz) => `${disp ? '' : '900 '}${sz}px ${disp ? F.display : F.round}`;
  const k = lerp(o.from ?? .6, 1, E.outBack(prog(t, t0, t0 + (o.dur ?? .2)), o.back ?? 1.4));
  ctx.save(); const ws = lines.map((l, i) => { ctx.font = fnt(sizes[i]); return ctx.measureText(l).width; }); ctx.restore();
  const lhs = sizes.map(sz => sz * (lines.length > 1 ? (o.lh ?? 1.22) : 1.0));
  let w = Math.max(...ws) + smax * .6, h = lhs.reduce((a, b) => a + b, 0) + smax * .3;
  const maxW = o.maxW ? o.maxW * U : 1e9; const sc = Math.min(1, maxW / w); w *= sc; h *= sc;
  const tails = o.tails || (o.tail ? [o.tail] : []), label = lines.join(''), ew = P.edges[0][1] * U / 2;
  // 読める状態: 枠が9割以上の大きさ・不透明度9割以上。行送り（o.lineDelay、0.1秒間隔）は前の行を読み終えるより早いので、1行目から数える
  const rd = k >= .9 && (o.alpha ?? 1) >= .9;
  // 行送り（o.lineDelay）では、枠の高さを出ている行に合わせて伸ばす（上端固定。空の枠を見せない）
  const d = o.lineDelay || 0, grow = lines.map((_, i) => !d || !i ? 1 : E.outCubic(prog(t, t0 + i * d, t0 + i * d + .1)));
  const hv = d ? lhs.reduce((a, lh, i) => a + lh * grow[i], 0) * sc + smax * .3 * sc : h;
  withT(() => {
    const L = -w / 2, T0 = -h / 2, r = Math.min(34 * U, hv / 2);
    ctx.fillStyle = 'rgba(27,16,51,.32)'; rrect(L + 8 * U, T0 + 12 * U, w, hv, r); ctx.fill();
    ctx.beginPath(); rrect(L, T0, w, hv, r);
    const kk = k * (o.scale || 1);
    for (const tl of tails) {   // しっぽ: 話者の方向を示すだけ（長さ tl.len、頭部の手前で止める）。横・上・下に対応
      const tx = (tl.x - x) / kk, ty = (tl.y - y) / kk, len = (tl.len || 60) * U, side = ty > T0 + r && ty < T0 + hv - r;
      let pts;
      if (side) {
        const bx = tx < 0 ? L : L + w, by = clamp(ty, T0 + r + 26 * U, T0 + hv - r - 26 * U), sg = tx < 0 ? -1 : 1;
        pts = [[bx, by - 22 * U], [bx + sg * Math.min(Math.abs(tx - bx), len), by + clamp((ty - by) * .55, -50 * U, 50 * U)], [bx, by + 22 * U]];
      } else {
        const bx = clamp(tx, L + r + 30 * U, L + w - r - 30 * U), by = ty > 0 ? T0 + hv : T0, sg = ty > 0 ? 1 : -1;
        pts = [[bx - 24 * U, by], [bx + clamp((tx - bx) * .55, -70 * U, 70 * U), by + sg * Math.min(Math.abs(ty - by), len)], [bx + 24 * U, by]];
      }
      ctx.moveTo(...pts[0]); ctx.lineTo(...pts[1]); ctx.lineTo(...pts[2]);
      recBox('tail', label, pts, { px: smax / U });
    }
    for (const [col, lw] of P.edges) { ctx.strokeStyle = col; ctx.lineWidth = lw * U; ctx.lineJoin = 'round'; ctx.stroke(); }
    ctx.fillStyle = P.bg; ctx.fill();
    if (P.edges.length > 1) { ctx.strokeStyle = C.ink; ctx.lineWidth = 2 * U; ctx.stroke(); ctx.fill(); }
    ctx.fillStyle = P.fg; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    let yy = T0 + smax * .15 * sc;
    lines.forEach((ln, i) => {
      const lh = lhs[i] * sc; const cy = yy + lh / 2; yy += lh;
      if (d && t < t0 + i * d) return;
      const ki = d && i ? lerp(.6, 1, E.outBack(prog(t, t0 + i * d, t0 + i * d + .2), 1.4)) : 1;
      ctx.save(); ctx.translate(0, cy); ctx.scale(ki, ki); ctx.font = fnt(sizes[i] * sc); ctx.fillText(ln, 0, sizes[i] * sc * .04); ctx.restore();
    });
    recBox(o.qa || 'telop', label, [[L - ew, T0 - ew], [L + w + ew, T0 - ew], [L - ew, T0 + hv + ew], [L + w + ew, T0 + hv + ew]], { spk, px: Math.min(...sizes) / U, rd });
  }, x, y, k * (o.scale || 1), o.rot || 0, o.alpha ?? 1);
}

// 頭部枠（HEAD_PHOTO）基準で人物ステッカーを置く。box = 表示座標の頭部枠 [x0,y0,x1,y1]（高さで拡縮、中心で位置合わせ）
function head(key, box, o = {}) {
  const img = IMG[key], who = FACE_LABEL[key], hp = HEAD_PHOTO[who], lay = img.layer, cut = img.cutFrac;
  const [x0, y0, x1, y1] = box, bh = y1 - y0, s = bh / (hp[3] - hp[1]), bw = (hp[2] - hp[0]) * s;
  const h = (lay[3] - lay[1]) * cut * s;
  const ax = ((hp[0] + hp[2]) / 2 - lay[0]) / (lay[2] - lay[0]), ay = ((hp[1] + hp[3]) / 2 - lay[1]) / ((lay[3] - lay[1]) * cut);
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  ctx.translate((x0 + x1) / 2 + (o.dx || 0), (y0 + y1) / 2 + (o.dy || 0)); if (o.rot) ctx.rotate(o.rot); if (o.sx || o.sy) ctx.scale(o.sx || 1, o.sy || 1);
  recBox('head', who, [[-bw / 2, -bh / 2], [bw / 2, -bh / 2], [-bw / 2, bh / 2], [bw / 2, bh / 2]], { h: bh });
  person(key, 0, 0, h, { ax, ay, noGap: o.noGap });
  ctx.restore();
}
// 頭部枠の中の「顔中心」（拡大の基準点）
function faceCenter(key, box) {
  const who = FACE_LABEL[key], hp = HEAD_PHOTO[who], fp = FACE_PHOTO[who], s = (box[3] - box[1]) / (hp[3] - hp[1]);
  return [box[0] + ((fp[0] + fp[2]) / 2 - hp[0]) * s, box[1] + ((fp[1] + fp[3]) / 2 - hp[1]) * s];
}
// カメラ: アンカー(ax,ay)基準で z 倍、(dx,dy) だけ揺らす
function cam(anchor, z, fn, dx = 0, dy = 0) {
  ctx.save(); ctx.translate(anchor[0] + dx, anchor[1] + dy); ctx.scale(z, z); ctx.translate(-anchor[0], -anchor[1]); fn(); ctx.restore();
}

// 小さなピル（チップ・ミニチップ）。tri: 下向き三角で指す
function pill(label, x, y, size, { bg = C.white, edge = C.pink, fg = C.ink, font = F.round, weight = '900 ', tri = false, r = null, qa = 'label', k = 1, rot = 0, padX = 34, spk = null, hMul = 1.5 } = {}) {
  if (k <= 0) return;
  withT(() => {
    ctx.font = `${weight}${size * U}px ${font}`; const w = ctx.measureText(label).width + padX * U, h = size * hMul * U, rr = r == null ? h / 2 : r;
    ctx.fillStyle = 'rgba(27,16,51,.3)'; rrect(-w / 2 + 5 * U, -h / 2 + 7 * U, w, h, rr); ctx.fill();
    ctx.beginPath(); rrect(-w / 2, -h / 2, w, h, rr);
    if (tri) { ctx.moveTo(-14 * U, h / 2); ctx.lineTo(0, h / 2 + 18 * U); ctx.lineTo(14 * U, h / 2); }
    ctx.fillStyle = bg; ctx.strokeStyle = edge; ctx.lineWidth = 5 * U; ctx.lineJoin = 'round'; ctx.stroke(); ctx.fill();
    ctx.fillStyle = fg; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(label, 0, 2 * U);
    const e = 2.5 * U;
    recBox(qa, label, [[-w / 2 - e, -h / 2 - e], [w / 2 + e, -h / 2 - e], [-w / 2 - e, h / 2 + e + (tri ? 18 * U : 0)], [w / 2 + e, h / 2 + e + (tri ? 18 * U : 0)]], { px: size, rd: k >= .9, ...(spk ? { spk } : {}) });
  }, x, y, k, rot);
}

// 3色ストライプのワイプ（最前面・等速・斜め15°・3本の合計幅=画面幅の40%）。
// 1フレームの移動量が帯幅を超えるため、露光区間 k0→k1 のモーションブラー（台形の不透明度）で描く。
// k0→k1 = このフレームの露光区間。revealFn: ストライプの後ろ（通過済み側）に次の画面を描く
function wipeBlur(k0, k1, revealFn, cols = [C.pink, C.purple, C.yellow], ang = 15 * Math.PI / 180) {
  if (k1 <= 0 || k0 >= 1) return;
  const tn = Math.tan(ang), slope = tn * H, band = W * .4 / cols.length, tot = band * cols.length, D = W + slope + tot;
  const uT = (k) => -slope - tot + D * k;       // 後端（左端）の u 座標（u = x − tan·(H−y)）
  const shear = () => ctx.setTransform(1, 0, -tn, 1, tn * H, 0);
  if (revealFn && uT(k0) > -slope) {
    ctx.save(); ctx.beginPath(); { ctx.save(); shear(); ctx.rect(-slope - 10, -10, uT(k0) + slope + 10, H + 20); ctx.restore(); } ctx.clip(); revealFn(); ctx.restore();
  }
  ctx.save(); shear();
  const d = D * (k1 - k0);
  cols.forEach((c, i) => {
    const a0 = uT(k0) + i * band, a1 = a0 + d + band;   // この区間に帯が掛かる範囲
    const g = ctx.createLinearGradient(a0, 0, a1, 0), m = Math.min(band, d) / (d + band), pk = Math.min(1, band / Math.max(d, 1e-6));
    const rgb = hexRgb(c), rgba = (a) => `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`;
    g.addColorStop(0, rgba(0)); g.addColorStop(m, rgba(pk)); g.addColorStop(1 - m, rgba(pk)); g.addColorStop(1, rgba(0));
    ctx.fillStyle = g; ctx.fillRect(a0, -10, a1 - a0, H + 20);
  });
  ctx.restore();
}
function hexRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }

// 文字の上だけを横切る光（キラッ）。text() と同じ引数で文字形状をマスクにする
function glint(str, x, y, o, k) {
  if (k <= 0 || k >= 1) return;
  const size = (o.size || 96) * U, pad = size;
  ctx.save(); ctx.font = `${o.weight || ''} ${size}px ${o.font || F.display}`; const tw = ctx.measureText(str).width; ctx.restore();
  const cw = Math.ceil(tw + pad * 2), ch = Math.ceil(size * 2);
  const c = document.createElement('canvas'); c.width = cw; c.height = ch; const g = c.getContext('2d');
  g.font = `${o.weight || ''} ${size}px ${o.font || F.display}`; g.textBaseline = 'middle'; g.textAlign = 'center';
  g.lineJoin = 'round'; g.lineWidth = size * .15; g.strokeStyle = '#fff'; g.strokeText(str, cw / 2, ch / 2); g.fillStyle = '#fff'; g.fillText(str, cw / 2, ch / 2);
  g.globalCompositeOperation = 'source-in';
  const bx = lerp(-cw * .3, cw * 1.3, k), gr = g.createLinearGradient(bx - size * .6, 0, bx + size * .6, 0);
  gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.5, 'rgba(255,255,255,.95)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.setTransform(1, 0, -.35, 1, ch * .175, 0); g.fillRect(-cw, 0, cw * 3, ch);
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha *= .8; ctx.drawImage(c, x - cw / 2, y - ch / 2); ctx.restore();
}

