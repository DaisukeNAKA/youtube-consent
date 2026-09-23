#!/usr/bin/env bash
# Google Fonts（SIL OFL 1.1）から使用書体を取得する。フォント本体は再配布しないためリポジトリに含めない。
set -euo pipefail
cd "$(dirname "$0")/../fonts"
UA="Mozilla/5.0 (Windows NT 6.1; WOW64; rv:25.0) Gecko/20100101 Firefox/25.0"
get() { # family weight outfile
  url=$(curl -s -A "$UA" "https://fonts.googleapis.com/css2?family=$1:wght@$2" | grep -oE "url\([^)]+\)" | head -1 | sed 's/url(//;s/)//')
  curl -s -o "$3" "$url"; echo "$3 $(wc -c < "$3") bytes"
}
get "Dela+Gothic+One" 400 Dela_Gothic_One_400.woff
get "M+PLUS+Rounded+1c" 900 M_PLUS_Rounded_1c_900.woff
get "M+PLUS+Rounded+1c" 800 M_PLUS_Rounded_1c_800.woff
get "Anton" 400 Anton_400.woff
