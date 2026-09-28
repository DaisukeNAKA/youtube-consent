#!/usr/bin/env bash
# run_pipeline.sh --camera A [--screen B] [--audio C] --out OUT [--settings settings.json] [--model medium] [--limit 40] [--plan edit_plan.json] [--vocab vocabulary.json]
# 参考: 各段を順に呼ぶ。edit_plan.json はエージェント(LLM)が cuts_auto.json と transcript.json を読んで書く想定。
# --plan を省略した場合は keep_auto から自動生成した最小限の edit_plan.json（プランA, 見出しなし）で通す。
# v2: 完成版は OUT/02_完成版/YouTube_本編_1080p.mp4（settings.resolution=4K なら YouTube_本編_4K.mp4）。
#     SRT は make_srt.py（補正後 transcript の文単位）で 02_完成版/字幕.srt（試作は 01_試作/字幕.srt）。
#     qc.py には --source/--plan を渡し、口元同期ずれ（A/V カットずれ）も検品する。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3.11}"
CAMERA=""; SCREEN=""; AUDIO=""; OUT=""; SETTINGS=""; MODEL="medium"; LIMIT=""; PLAN=""; VOCAB=""; NO_RENDER="${NO_RENDER:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --camera) CAMERA="$2"; shift 2;; --screen) SCREEN="$2"; shift 2;; --audio) AUDIO="$2"; shift 2;;
    --out) OUT="$2"; shift 2;; --settings) SETTINGS="$2"; shift 2;; --model) MODEL="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;; --plan) PLAN="$2"; shift 2;; --vocab) VOCAB="$2"; shift 2;;
    --no-render) NO_RENDER=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$CAMERA" ] && [ -n "$OUT" ] || { echo "usage: run_pipeline.sh --camera A [--screen B] [--audio C] --out OUT [...]" >&2; exit 2; }
W="$OUT/work"; mkdir -p "$W"
SET_ARGS=(); [ -n "$SETTINGS" ] && SET_ARGS=(--settings "$SETTINGS")
VOC_ARGS=(); [ -n "$VOCAB" ] && VOC_ARGS=(--vocab "$VOCAB")

FILES=("$CAMERA"); [ -n "$SCREEN" ] && FILES+=("$SCREEN"); [ -n "$AUDIO" ] && FILES+=("$AUDIO")
"$PY" "$HERE/probe.py" "${FILES[@]}" --out "$W/probe.json"
SYNC_ARGS=(--camera "$CAMERA"); [ -n "$SCREEN" ] && SYNC_ARGS+=(--screen "$SCREEN"); [ -n "$AUDIO" ] && SYNC_ARGS+=(--audio "$AUDIO")
"$PY" "$HERE/sync.py" "${SYNC_ARGS[@]}" --out "$W/sync.json"
# 別録り音声があればそちらを書き起こす（同期後の時刻はカメラ基準へ換算されないため、audio_offset を transcript に反映）
"$PY" "$HERE/transcribe.py" "$CAMERA" --out "$W/transcript.json" --model "$MODEL" "${VOC_ARGS[@]}"
"$PY" "$HERE/plan_cuts.py" --transcript "$W/transcript.json" --audio "$CAMERA" "${SET_ARGS[@]}" --out "$W/cuts_auto.json"
if [ -n "$PLAN" ]; then
  cp "$PLAN" "$W/edit_plan.json"
elif [ ! -f "$W/edit_plan.json" ]; then
  "$PY" - "$W/cuts_auto.json" "$W/edit_plan.json" <<'PYEOF'
import json, sys
c = json.load(open(sys.argv[1]))
json.dump({"plan": "A", "keep": c["keep_auto"], "headings": [], "screen": [], "broll": [], "caption_overrides": [],
           "notes": "auto: keep_auto をそのまま採用（エージェントが確定する前の仮）"}, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
PYEOF
fi
LIM_ARGS=(); [ -n "$LIMIT" ] && LIM_ARGS=(--limit-seconds "$LIMIT")
"$PY" "$HERE/captions.py" --transcript "$W/transcript.json" --plan "$W/edit_plan.json" "${SET_ARGS[@]}" --out "$W/captions.json"
# v2 B1: SRT は焼き込みキューとは別に、補正後 transcript の文単位（句読点あり）から生成する
"$PY" "$HERE/make_srt.py" --transcript "$W/transcript.json" --plan "$W/edit_plan.json" "${SET_ARGS[@]}" --out "$W/字幕.srt" "${LIM_ARGS[@]}"
"$PY" "$HERE/cut_media.py" --plan "$W/edit_plan.json" --sync "$W/sync.json" "${SET_ARGS[@]}" --workdir "$W" "${LIM_ARGS[@]}"
"$PY" "$HERE/build_timeline.py" --plan "$W/edit_plan.json" --captions "$W/captions.json" "${SET_ARGS[@]}" --probe "$W/probe.json" --sync "$W/sync.json" --out "$W/timeline.json" "${LIM_ARGS[@]}"
# v2 C1: 完成版ファイル名は解像度で決まる（common.final_name）
FINAL_NAME="$("$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); from common import load_settings, final_name; print(final_name(load_settings(sys.argv[2] or None)))' "$HERE" "$SETTINGS")"
if [ -n "$LIMIT" ]; then FINAL="$OUT/01_試作/試作_${LIMIT}秒.mp4"; else FINAL="$OUT/02_完成版/$FINAL_NAME"; fi
mkdir -p "$(dirname "$FINAL")"
cp "$W/字幕.srt" "$(dirname "$FINAL")/字幕.srt"
if [ -z "$NO_RENDER" ]; then
  bash "$HERE/render.sh" "$W" "$FINAL"
  "$PY" "$HERE/qc.py" --timeline "$W/timeline.json" --video "$FINAL" --captions "$W/captions.json" "${SET_ARGS[@]}" \
    --source "$CAMERA" --plan "$W/edit_plan.json" --cut-media "$W/cut_media.json" --sync "$W/sync.json" --out "$(dirname "$FINAL")/qc_report.md"
else
  echo "[pipeline] NO_RENDER: render/qc をスキップ。timeline: $W/timeline.json" >&2
fi
[ -n "$SETTINGS" ] && cp "$SETTINGS" "$(dirname "$FINAL")/settings.json" || true
echo "[pipeline] done -> $FINAL" >&2
