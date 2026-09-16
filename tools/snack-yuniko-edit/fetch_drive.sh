#!/bin/bash
# 共有リンク（閲覧者）にした Drive ファイルを gdown で取得する
set -euo pipefail
ID="$1"; OUT="$2"
python3 -m gdown --fuzzy "https://drive.google.com/uc?id=${ID}" -O "$OUT" --continue
ls -la "$OUT"
