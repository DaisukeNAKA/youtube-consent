// ユニコ15秒CM 書き出し: cm.html をヘッドレスChromiumで1フレームずつ描画し ffmpeg へ PNG を流す
// usage: [VARIANT=SNS] node tools/render.mjs <916|169> <out.mp4> [audio.wav]
//   VARIANT=SNS … TikTok・Instagram・X 通常投稿用のエンドカード（フォローしてね／フォロー！）
import { createRequire } from 'node:module';
import { spawn, execSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); }
catch { ({ chromium } = require('/opt/node22/lib/node_modules/playwright')); }

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fmt = process.argv[2] === '169' ? '169' : '916';
const out = path.resolve(process.argv[3] || path.join(ROOT, 'out', `unico_cm15_${fmt}.mp4`));
const audio = process.argv[4] ? path.resolve(process.argv[4]) : null;
const only = process.env.FRAMES ? process.env.FRAMES.split(',').map(Number) : null; // 静止画チェック用
const FFMPEG = process.env.FFMPEG || execSync(`python3 -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"`).toString().trim();

// 静的サーバ（file:// だとフォント/画像読込がCORSで失敗するため）
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png', '.woff': 'font/woff', '.wav': 'audio/wav', '.json': 'application/json' };
const server = http.createServer((req, res) => {
  const p = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(p)] || 'application/octet-stream' }); fs.createReadStream(p).pipe(res);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const port = server.address().port;

const W = fmt === '169' ? 1920 : 1080, H = fmt === '169' ? 1080 : 1920;
const browser = await chromium.launch({ args: ['--font-render-hinting=none', '--disable-gpu-vsync'] });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
page.on('pageerror', e => { console.error('PAGE ERROR', e); process.exitCode = 1; });
const variant = process.env.VARIANT === 'SNS' ? 'SNS' : 'YT';
await page.goto(`http://127.0.0.1:${port}/cm.html?fmt=${fmt}&export=1&variant=${variant}`);
await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
const N = await page.evaluate(() => NFRAMES);

if (only) {
  fs.mkdirSync(path.dirname(out), { recursive: true });
  for (const i of only) {
    const url = await page.evaluate(i => window.__frame(i), i);
    const f = out.replace(/\.(mp4|png)$/, '') + `_f${String(i).padStart(3, '0')}.png`;
    fs.writeFileSync(f, Buffer.from(url.split(',')[1], 'base64'));
    console.log('wrote', f);
  }
} else {
  const args = ['-y', '-hide_banner', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', '30', '-c:v', 'png', '-i', '-'];
  if (audio) args.push('-i', audio);
  args.push('-map', '0:v');
  if (audio) args.push('-map', '1:a', '-c:a', 'aac', '-b:a', '384k', '-ar', '48000', '-ac', '2');   // -shortest は使わない（音声14.9973秒に合わせて映像が449フレームに切られるため）
  args.push('-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-maxrate', '14M', '-bufsize', '28M', '-profile:v', 'high', '-level', fmt === '169' ? '4.1' : '4.2',
    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
    '-r', '30', '-g', '30', '-movflags', '+faststart', '-t', '15', out);
  const ff = spawn(FFMPEG, args, { stdio: ['pipe', 'inherit', 'inherit'] });
  const t0 = Date.now(); const boxes = [], gaps = [];
  for (let i = 0; i < N; i++) {
    const url = await page.evaluate(i => window.__frame(i), i);
    const buf = Buffer.from(url.split(',')[1], 'base64');
    const [bx, gp] = await page.evaluate(() => [window.__boxes, window.__gap]); boxes.push(bx); gaps.push(gp);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 60 === 0) console.log(`frame ${i}/${N} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
  }
  ff.stdin.end();
  await new Promise((r, j) => ff.on('close', c => c === 0 ? r() : j(new Error('ffmpeg exit ' + c))));
  fs.writeFileSync(out.replace(/\.mp4$/, '') + '.qa_boxes.json', JSON.stringify({ fmt, variant, W, H, fps: 30, frames: boxes, gaps }));
  console.log('wrote', out, ((Date.now() - t0) / 1000).toFixed(1) + 's');
}
await browser.close(); server.close();
