#!/bin/bash
# スナックゆに子 #29 完パケ再現スクリプト（macOS 用）
# 使い方:  bash tools/snack-yuniko-edit/reproduce_29.sh [原本MP4のパス] [--dry-run]
#   原本のパスを省略すると Google Drive（リンク共有中）から自動取得します。
set -euo pipefail
cd "$(cd "$(dirname "$0")/../.." && pwd)"
REPO="$(pwd)"
TOOLS="$REPO/tools/snack-yuniko-edit"
WORK="${SNACK_WORK:-$HOME/Movies/snack_yuniko_29}"
RAW_NAME="DJI_20260915135827_0021_D.MP4"
OUT_NAME="スナックゆに子_29_完パケ.mp4"
RAW_ARG=""; DRY=""
for a in "$@"; do
  case "$a" in --dry-run) DRY="--dry-run";; *) RAW_ARG="$a";; esac
done
mkdir -p "$WORK/raw" "$WORK/se" "$WORK/fonts" "$WORK/work" "$WORK/out"
echo "== 作業フォルダ: $WORK"

echo "== 1/6 ffmpeg の確認"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v ffmpeg >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew（Mac 用のソフト導入ツール）を先に導入します。"
    echo "  → 途中で Mac のログインパスワードを聞かれたら入力して Enter（入力中は画面に表示されません）"
    echo "  → 「Press RETURN」と出たら Enter を押してください"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
    command -v brew >/dev/null 2>&1 || { echo "Homebrew の導入が確認できませんでした。ターミナルを開き直して再実行してください"; exit 1; }
  fi
  echo "ffmpeg を Homebrew で導入します（5〜10 分かかります）"
  brew install ffmpeg
fi
ffmpeg -hide_banner -version | head -1
FILTERS="$(ffmpeg -hide_banner -filters 2>/dev/null || true)"
if [[ "$FILTERS" != *" ass "* ]] && [[ "$FILTERS" != *$'\t'"ass"* ]]; then
  echo "この ffmpeg は libass（字幕描画）非対応の可能性があります。続行はしますが、テーマ表示が出ない場合は brew install ffmpeg で入れ直してください"
fi

echo "== 2/6 Python パッケージ（gdown）の確認"
python3 -c "import gdown" 2>/dev/null || python3 -m pip install -q --user gdown requests || python3 -m pip install -q gdown requests

echo "== 3/6 原本の用意"
if [ -n "$RAW_ARG" ]; then
  [ -f "$RAW_ARG" ] || { echo "原本が見つかりません: $RAW_ARG"; exit 1; }
  RAW="$RAW_ARG"
else
  RAW="$WORK/raw/$RAW_NAME"
  if [ ! -f "$RAW" ] || [ "$(stat -f%z "$RAW" 2>/dev/null || stat -c%s "$RAW")" -lt 10949788856 ]; then
    echo "Drive から原本（10.9GB）を取得します（回線により 10〜30 分）"
    python3 -m gdown "1Q9GAAPncgy45AG3ddC0WKv6cWl-2Bopv" -O "$RAW" --continue
  fi
fi
echo "原本: $RAW"

echo "== 4/6 SE・ED 音源の用意"
fetch_se() { local id="$1" name="$2"; [ -f "$WORK/se/$name" ] || python3 -m gdown "$id" -O "$WORK/se/$name"; }
fetch_se "1ELvLNSj0nqbciQfDf2C-JXGA9vQHCmgv" "doorbell.wav"
fetch_se "1KPPyrP6PcYdrysnPbPo4MSpiYFmHdA1T" "porunohabu-chao-gao-yin-zhi_QjjZBon.wav"
fetch_se "10Ir_0aj9MIt2H8ASsV9Nd1PeH1Mm1n7u" "ricchan_ekubo.wav"

echo "== 5/6 フォント（BIZ UDGothic Bold）の用意"
if [ ! -f "$WORK/fonts/BIZUDGothic-Bold.ttf" ]; then
  URL="$(curl -sS -A "Mozilla/4.0" "https://fonts.googleapis.com/css2?family=BIZ+UDGothic:wght@700" | grep -o 'https://[^)]*' | sed -n '1p')"
  curl -sS -L -o "$WORK/fonts/BIZUDGothic-Bold.ttf" "$URL"
fi
ls -la "$WORK/fonts/BIZUDGothic-Bold.ttf"

echo "== 6/6 レンダリング（Apple Silicon で 20〜40 分）"
python3 - "$TOOLS/plan_29.json" "$WORK/plan_29_local.json" "$RAW" "$WORK/se" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding="utf-8"))
p["source"] = sys.argv[3]; p["se_dir"] = sys.argv[4]
json.dump(p, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("plan:", sys.argv[2])
PY
SKIP=""; [ -f "$WORK/work/dialogue_processed.wav" ] && SKIP="--skip-dialogue" && echo "（整音済み音声を再利用します）"
python3 "$TOOLS/edit_pipeline.py" "$WORK/plan_29_local.json" --out "$WORK/out/$OUT_NAME" --workdir "$WORK/work" --fonts-dir "$WORK/fonts" $SKIP $DRY
if [ -z "$DRY" ]; then
  cp "$WORK/out/$OUT_NAME" "$HOME/Downloads/$OUT_NAME"
  echo "== 完成: $HOME/Downloads/$OUT_NAME"
  echo "   QA レポート: $WORK/work/qa_report.json / コンタクトシート: $WORK/work/qa_contact_sheet.jpg"
fi
