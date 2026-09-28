#!/usr/bin/env bash
# render.sh <OUT/work> <out.mp4> [timeline.json 名 (既定 timeline.json)]
# OUT/work を remotion/public/work にシンボリックリンクし、npx remotion render を実行する。
# 環境変数: REMOTION_BROWSER (chromium 実行ファイル → --browser-executable), REMOTION_CONCURRENCY (--concurrency),
#           REMOTION_DIR (remotion プロジェクト, 既定: このスクリプトの ../remotion), REMOTION_EXTRA (追加引数)
#           RENDER_AUDIO=mux(既定)|remotion
#             mux: Remotion は --muted で映像だけ描き、音声は work/cut.mp4（loudnorm 済み AAC）を ffmpeg で無変換多重化する。
#                  v2 C3 の所見: Remotion(Chrome) 経由の音声は AAC プライミング 2 回分 (2048 サンプル@48k = +0.043s) 遅れて
#                  口元同期ずれになるため、既定は mux。remotion を指定すると v1 と同じ（Remotion が音声も書く）。
set -euo pipefail
WORK="$(cd "$1" && pwd)"
OUT="$2"
TL="${3:-timeline.json}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTION_DIR="${REMOTION_DIR:-$HERE/../remotion}"
REMOTION_DIR="$(cd "$REMOTION_DIR" && pwd)"
mkdir -p "$REMOTION_DIR/public"
rm -rf "$REMOTION_DIR/public/work"
ln -s "$WORK" "$REMOTION_DIR/public/work"
mkdir -p "$(dirname "$OUT")"
ARGS=()
if [ -n "${REMOTION_BROWSER:-}" ]; then ARGS+=(--browser-executable="$REMOTION_BROWSER"); fi
if [ -n "${REMOTION_CONCURRENCY:-}" ]; then ARGS+=(--concurrency="$REMOTION_CONCURRENCY"); fi
if [ -n "${REMOTION_EXTRA:-}" ]; then read -r -a EXTRA <<< "$REMOTION_EXTRA"; ARGS+=("${EXTRA[@]}"); fi
RENDER_AUDIO="${RENDER_AUDIO:-mux}"
AUDIO_SRC="$WORK/$(python3.11 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("video") or "cut.mp4")' "$WORK/$TL" 2>/dev/null || echo cut.mp4)"
if [ "$RENDER_AUDIO" = "mux" ] && [ ! -f "$AUDIO_SRC" ]; then
  echo "[render] $AUDIO_SRC が無いので RENDER_AUDIO=remotion で描画します" >&2; RENDER_AUDIO=remotion
fi
cd "$REMOTION_DIR"
if [ "$RENDER_AUDIO" = "mux" ]; then
  TMPV="${OUT%.mp4}.video_only.mp4"
  echo "[render] npx remotion render src/index.ts Main $TMPV --muted --props=public/work/$TL ${ARGS[*]:-}" >&2
  npx remotion render src/index.ts Main "$TMPV" --props="public/work/$TL" --codec=h264 --crf=18 --muted "${ARGS[@]}"
  echo "[render] mux audio from $AUDIO_SRC (copy)" >&2
  ffmpeg -y -v error -i "$TMPV" -i "$AUDIO_SRC" -map 0:v:0 -map 1:a:0 -c copy -shortest -movflags +faststart "$OUT"
  rm -f "$TMPV"
else
  echo "[render] npx remotion render src/index.ts Main $OUT --props=public/work/$TL ${ARGS[*]:-}" >&2
  npx remotion render src/index.ts Main "$OUT" --props="public/work/$TL" --codec=h264 --crf=18 "${ARGS[@]}"
fi
echo "[render] done: $OUT" >&2
