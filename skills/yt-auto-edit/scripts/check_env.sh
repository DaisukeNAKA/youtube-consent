#!/usr/bin/env bash
# check_env.sh — yt-auto-edit の環境チェック（初回・トラブル時に実行）
# 使い方: bash "<skill>/scripts/check_env.sh"   （終了コード 0=全部そろっている / 1=不足あり）
# 判定: OS(macOS/Linux/WSL/Windows) → ffmpeg/ffprobe/python3/node/npm/whisper(mlx_whisper|faster_whisper)
#       /Remotion node_modules/フォント(Noto Sans JP) の有無を表示し、不足分のインストールコマンドをコピペ形式で出す。
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
REMOTION_DIR="${REMOTION_DIR:-$SKILL/remotion}"
FONT_FILE="$REMOTION_DIR/public/fonts/NotoSansJP[wght].ttf"
FONT_URL='https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf'

# ---------- OS 判定 ----------
UNAME_S="$(uname -s 2>/dev/null || echo unknown)"
ARCH="$(uname -m 2>/dev/null || echo unknown)"
OS="linux"
case "$UNAME_S" in
  Darwin) OS="macos" ;;
  Linux)
    if grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then OS="wsl"; else OS="linux"; fi ;;
  MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
esac
APPLE_SILICON=0
if [ "$OS" = "macos" ] && [ "$ARCH" = "arm64" ]; then APPLE_SILICON=1; fi

# パッケージマネージャ
PKG=""
case "$OS" in
  macos) PKG="brew" ;;
  linux|wsl) if command -v apt-get >/dev/null 2>&1; then PKG="apt"; elif command -v dnf >/dev/null 2>&1; then PKG="dnf"; else PKG="manual"; fi ;;
  windows) PKG="winget" ;;
esac

echo "== yt-auto-edit 環境チェック =="
echo "OS: $OS ($UNAME_S $ARCH)  パッケージ管理: $PKG  スキル: $SKILL"
echo

MISSING=()      # 表示用ラベル
INSTALL=()      # コピペ用コマンド（重複は後で除去）
WARN=()

ok()   { printf '  [OK] %-22s %s\n' "$1" "${2:-}"; }
ng()   { printf '  [NG] %-22s %s\n' "$1" "${2:-}"; MISSING+=("$1"); }
warn() { printf '  [--] %-22s %s\n' "$1" "${2:-}"; WARN+=("$1: ${2:-}"); }

add_install() { INSTALL+=("$1"); }

pkg_cmd() {
  # $1 = 論理名 (ffmpeg|node|python)
  case "$PKG:$1" in
    brew:ffmpeg) echo "brew install ffmpeg" ;;
    brew:node)   echo "brew install node" ;;
    brew:python) echo "brew install python@3.11" ;;
    apt:ffmpeg)  echo "sudo apt-get update && sudo apt-get install -y ffmpeg" ;;
    apt:node)    echo "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs" ;;
    apt:python)  echo "sudo apt-get install -y python3 python3-pip python3-venv" ;;
    dnf:ffmpeg)  echo "sudo dnf install -y ffmpeg" ;;
    dnf:node)    echo "sudo dnf install -y nodejs npm" ;;
    dnf:python)  echo "sudo dnf install -y python3 python3-pip" ;;
    winget:ffmpeg) echo "winget install --id Gyan.FFmpeg -e" ;;
    winget:node)   echo "winget install --id OpenJS.NodeJS.LTS -e" ;;
    winget:python) echo "winget install --id Python.Python.3.11 -e" ;;
    *) echo "# $1 を手動でインストールしてください" ;;
  esac
}

# ---------- 1. ffmpeg / ffprobe ----------
echo "[1] 動画処理"
if command -v ffmpeg >/dev/null 2>&1; then
  ok ffmpeg "$(ffmpeg -version 2>/dev/null | head -1 | awk '{print $3}')"
else
  ng ffmpeg "見つかりません"; add_install "$(pkg_cmd ffmpeg)"
fi
if command -v ffprobe >/dev/null 2>&1; then
  ok ffprobe "$(command -v ffprobe)"
else
  ng ffprobe "見つかりません（ffmpeg と同梱）"; add_install "$(pkg_cmd ffmpeg)"
fi

# ---------- 2. Python ----------
echo "[2] Python"
PYBIN=""
for c in "${PYTHON:-}" python3.11 python3.12 python3.13 python3; do
  [ -n "$c" ] || continue
  if command -v "$c" >/dev/null 2>&1; then
    v="$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || true)"
    case "$v" in 3.9|3.10|3.11|3.12|3.13|3.14) PYBIN="$c"; break ;; esac
  fi
done
if [ -n "$PYBIN" ]; then
  ok python3 "$PYBIN ($("$PYBIN" --version 2>&1))  → 実行時は PYTHON=$PYBIN"
else
  ng python3 "3.9 以上が見つかりません"; add_install "$(pkg_cmd python)"
fi

# ---------- 3. 音声認識 ----------
echo "[3] 音声認識 (Whisper)"
WHISPER=""
if [ -n "$PYBIN" ]; then
  if [ "$APPLE_SILICON" = 1 ] && "$PYBIN" -c 'import mlx_whisper' >/dev/null 2>&1; then WHISPER="mlx_whisper"; fi
  if [ -z "$WHISPER" ] && "$PYBIN" -c 'import faster_whisper' >/dev/null 2>&1; then WHISPER="faster_whisper"; fi
fi
if [ -n "$WHISPER" ]; then
  ok whisper "$WHISPER"
  if [ "$APPLE_SILICON" = 1 ] && [ "$WHISPER" = "faster_whisper" ]; then
    warn whisper "Apple Silicon では mlx_whisper の方が速い: $PYBIN -m pip install mlx-whisper"
  fi
else
  if [ "$APPLE_SILICON" = 1 ]; then
    ng whisper "mlx_whisper も faster_whisper も入っていません"; add_install "${PYBIN:-python3} -m pip install mlx-whisper"
  else
    ng whisper "faster_whisper が入っていません"; add_install "${PYBIN:-python3} -m pip install faster-whisper"
  fi
fi
# 補助ライブラリ（sync.py / qc.py が使う numpy）
if [ -n "$PYBIN" ]; then
  if "$PYBIN" -c 'import numpy' >/dev/null 2>&1; then ok numpy ""; else ng numpy "sync.py が使います"; add_install "$PYBIN -m pip install numpy"; fi
fi

# ---------- 4. Node / npm / Remotion ----------
echo "[4] Node.js / Remotion"
if command -v node >/dev/null 2>&1; then
  NV="$(node -v 2>/dev/null)"; ok node "$NV"
  MAJ="${NV#v}"; MAJ="${MAJ%%.*}"
  if [ "${MAJ:-0}" -lt 18 ] 2>/dev/null; then warn node "18 以上を推奨（Remotion 4）"; fi
else
  ng node "見つかりません"; add_install "$(pkg_cmd node)"
fi
if command -v npm >/dev/null 2>&1; then ok npm "$(npm -v 2>/dev/null)"; else ng npm "見つかりません（node と同梱）"; add_install "$(pkg_cmd node)"; fi
if [ -d "$REMOTION_DIR" ]; then
  if [ -d "$REMOTION_DIR/node_modules/remotion" ] && [ -d "$REMOTION_DIR/node_modules/@remotion/cli" ]; then
    ok "remotion node_modules" "$REMOTION_DIR/node_modules"
  else
    ng "remotion node_modules" "未インストール"; add_install "cd \"$REMOTION_DIR\" && npm install"
  fi
else
  ng "remotion project" "$REMOTION_DIR が見つかりません（REMOTION_DIR で指定可）"
fi

# ---------- 5. フォント ----------
echo "[5] フォント"
if [ -f "$FONT_FILE" ]; then
  ok "Noto Sans JP (Remotion)" "$FONT_FILE"
else
  ng "Noto Sans JP (Remotion)" "$FONT_FILE がありません"
  add_install "mkdir -p \"$REMOTION_DIR/public/fonts\" && curl -L -o \"$FONT_FILE\" '$FONT_URL'"
fi
SYSFONT=""
if command -v fc-list >/dev/null 2>&1; then
  SYSFONT="$(fc-list 2>/dev/null | grep -iE 'Noto ?Sans ?(JP|CJK)' | head -1 | cut -d: -f1)"
elif [ "$OS" = "macos" ]; then
  for f in "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc" "/System/Library/Fonts/Hiragino Sans GB.ttc" "$HOME/Library/Fonts/NotoSansJP-Regular.ttf"; do [ -f "$f" ] && SYSFONT="$f" && break; done
fi
if [ -n "$SYSFONT" ]; then ok "日本語システムフォント" "$SYSFONT"; else warn "日本語システムフォント" "見つかりません（Remotion は上の TTF を使うので必須ではない）"; fi

# ---------- 6. 補足（ブラウザ / GPU） ----------
echo "[6] 補足"
case "$OS" in
  macos) ok "Chromium" "Remotion が初回に自動ダウンロード" ;;
  linux|wsl)
    if [ -n "${REMOTION_BROWSER:-}" ] && [ -x "$REMOTION_BROWSER" ]; then ok "Chromium" "REMOTION_BROWSER=$REMOTION_BROWSER";
    else warn "Chromium" "Remotion が自動DLします。GPU 無しコンテナでは REMOTION_BROWSER=<headless_shell> と --gl=swangle を検討"; fi ;;
  windows) warn "Windows" "ネイティブ Windows は WSL2 での実行を推奨（Git Bash でも動くが未検証）" ;;
esac
if command -v nproc >/dev/null 2>&1; then ok "CPU" "$(nproc) コア"; elif command -v sysctl >/dev/null 2>&1; then ok "CPU" "$(sysctl -n hw.ncpu 2>/dev/null) コア"; fi

# ---------- 結果 ----------
echo
if [ "${#MISSING[@]}" -eq 0 ]; then
  echo "結果: 必要なものはすべてそろっています。"
  [ "${#WARN[@]}" -gt 0 ] && { echo "注意:"; for w in "${WARN[@]}"; do echo "  - $w"; done; }
  exit 0
fi
echo "結果: 不足あり → ${MISSING[*]}"
echo
echo "----- 不足分のインストール（そのままコピペで実行） -----"
if [ "$PKG" = "brew" ] && ! command -v brew >/dev/null 2>&1; then
  echo '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
fi
printf '%s\n' "${INSTALL[@]}" | awk '!seen[$0]++'
echo "-------------------------------------------------------"
echo "インストール後にもう一度: bash \"$HERE/check_env.sh\""
exit 1
