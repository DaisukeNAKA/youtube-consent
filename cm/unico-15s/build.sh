#!/usr/bin/env bash
# ユニコ15秒CM 一括ビルド: 音声生成 → ラウドネス正規化 → 9:16 / 16:9 書き出し → 自動QA → 共有用の軽量版
# usage: ./build.sh            （両フォーマット）
#        ./build.sh 916        （縦のみ）
set -euo pipefail
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"
FF="${FFMPEG:-$(python3 -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')}"
FMTS="${1:-916 169}"
mkdir -p out/audio

echo "== 1/5 音声（自作ジングル＋自作SE、声WAVがあれば自動ミックス）"
python3 tools/audio.py

echo "== 2/5 マスタリング（-14 LUFS / TP -1.2 dBTP 以下 / 719,872サンプル＝AAC 703フレーム）"
python3 tools/master.py out/audio/mix_raw.wav out/audio/mix.wav

echo "== 3/5 映像書き出し"
for f in $FMTS; do
  node tools/render.mjs "$f" "out/unico_cm15_${f}.mp4" out/audio/mix.wav
done

echo "== 4/5 自動QA"
status=0
python3 tools/qa.py $(for f in $FMTS; do echo "out/unico_cm15_${f}.mp4"; done) > out/qa_report.json || status=$?
python3 -c "import json;[print(r['file'], '合格' if not r['issues'] else r['issues']) for r in json.load(open('out/qa_report.json'))]"

echo "== 5/5 共有用の軽量版（プレビュー・チャット共有向け。入稿にはマスターを使う）"
for f in $FMTS; do
  "$FF" -y -hide_banner -loglevel error -i "out/unico_cm15_${f}.mp4" -map 0 -c:v libx264 -preset slow -crf 21 -maxrate 6M -bufsize 12M \
    -profile:v high -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv -c:a copy -movflags +faststart "out/unico_cm15_${f}_web.mp4"
done
ls -la out/*.mp4
exit $status
