#!/usr/bin/env bash
# ユニコ15秒CM 一括ビルド
#   1. 音声（自作ジングル＋自作SE、声WAVがあれば自動ミックス）を比率ごとに生成し、ラウドネス調整
#   2. 書き出し: E0-YT（9:16・Shorts）/ E0-169（16:9・X・会場・広告素材）/ E0-SNS（9:16・TikTok・Instagram・X 通常投稿）
#   3. 自動QA（out/qa_report.json、不合格があれば終了コード1）
#   4. 納品物: 共有用の軽量版・効果音だけの版・エンドカード静止画
# usage: ./build.sh            （全部）
#        ./build.sh 916        （縦だけ。E0-SNS も縦なので一緒に作る）
set -euo pipefail
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"
FF="${FFMPEG:-$(python3 -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')}"
FMTS="${1:-916 169}"
mkdir -p out/audio out/stills

echo "== 1/4 音声（比率ごと。-14 LUFS / TP -1.2 dBTP 以下 / 718,848サンプル）"
for f in $FMTS; do
  python3 tools/audio.py --fmt "$f"
  python3 tools/master.py "out/audio/mix_raw_${f}.wav" "out/audio/mix_${f}.wav"
  python3 tools/audio.py --fmt "$f" --se-only
  python3 tools/master.py "out/audio/mix_raw_${f}_se.wav" "out/audio/mix_${f}_se.wav" --gain-from "out/audio/mix_${f}.wav.json"
done

echo "== 2/4 映像書き出し"
MASTERS=()
for f in $FMTS; do
  node tools/render.mjs "$f" "out/unico_cm15_${f}.mp4" "out/audio/mix_${f}.wav"; MASTERS+=("out/unico_cm15_${f}.mp4")
  if [ "$f" = 916 ]; then
    VARIANT=SNS node tools/render.mjs 916 out/unico_cm15_916_sns.mp4 out/audio/mix_916.wav; MASTERS+=(out/unico_cm15_916_sns.mp4)
  fi
done

echo "== 3/4 自動QA"
status=0
python3 tools/qa.py "${MASTERS[@]}" > out/qa_report.json || status=$?
python3 -c "import json;[print(r['file'], '合格' if not r['issues'] else r['issues'], '/ 参考', len(r['warnings']), '件') for r in json.load(open('out/qa_report.json'))]"

echo "== 4/4 納品物（入稿にはマスター out/unico_cm15_*.mp4 を使う）"
for m in "${MASTERS[@]}"; do
  b="${m%.mp4}"
  # 共有用の軽量版（プレビュー・チャット・X 投稿向け、映像6Mbps上限）
  "$FF" -y -hide_banner -loglevel error -i "$m" -map 0 -c:v libx264 -preset slow -crf 21 -maxrate 6M -bufsize 12M \
    -profile:v high -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv -c:a copy -movflags +faststart "${b}_web.mp4"
done
for f in $FMTS; do
  # 効果音だけの版（BGMなし。映像はマスターをそのまま使い、音声だけ差し替え）
  "$FF" -y -hide_banner -loglevel error -i "out/unico_cm15_${f}.mp4" -i "out/audio/mix_${f}_se.wav" -map 0:v -map 1:a -c:v copy \
    -c:a aac -b:a 384k -ar 48000 -ac 2 -movflags +faststart "out/unico_cm15_${f}_se.mp4"
  # エンドカードの静止画（A: ロゴ静止の最終フレーム f404 / B: 決め画面 f449）
  FRAMES=404,449 node tools/render.mjs "$f" "out/stills/unico_cm15_${f}.png" > /dev/null
  if [ "$f" = 916 ]; then VARIANT=SNS FRAMES=449 node tools/render.mjs 916 out/stills/unico_cm15_916_sns.png > /dev/null; fi
done
ls -la out/*.mp4 out/stills/*.png
exit $status
