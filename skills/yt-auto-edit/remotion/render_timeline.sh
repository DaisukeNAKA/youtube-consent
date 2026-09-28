#!/usr/bin/env bash
# Usage: render_timeline.sh <timeline.json> <out.mp4> [extra remotion args...]
# The timeline's relative media paths are resolved under <remotion>/public/work/,
# so link/copy OUT/work there first (scripts/render.sh does this):
#   ln -sfn "$OUT/work" "$REMOTION/public/work"
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TL="$1"; OUT="$2"; shift 2
ARGS=(--props="$TL" --concurrency="${REMOTION_CONCURRENCY:-$(nproc 2>/dev/null || sysctl -n hw.ncpu)}" --color-space=bt709)
# Linux containers without a GPU: pass a Chromium binary + swangle. macOS: Remotion downloads its own headless shell.
if [[ -n "${REMOTION_BROWSER:-}" ]]; then ARGS+=(--browser-executable="$REMOTION_BROWSER"); fi
if [[ "$(uname -s)" == "Linux" ]]; then ARGS+=(--gl="${REMOTION_GL:-swangle}"); fi
cd "$HERE"
npx remotion render src/index.ts Main "$OUT" "${ARGS[@]}" "$@"
