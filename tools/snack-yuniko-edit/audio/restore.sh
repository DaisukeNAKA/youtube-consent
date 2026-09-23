#!/usr/bin/env bash
# DJI Mic Mini 2 + Osmo Pocket 3 のワイヤレス素材を、実測に基づいて補正する。
#
#   使い方: ./restore.sh 入力.mp4 出力.wav [ハイシェルフのゲイン(既定 5.0)]
#
# EQ の値は #29 素材の 1/3 オクターブ実測（16384点FFT・発話区間のみ）と
# Byrne et al. (1994) の長時間平均話声スペクトルの差を最小二乗で当てはめて導いた。
# ディエッサーは ffmpeg 内蔵のものが本素材にほぼ効かないため、
#   python3 ../deesser.py 相当（deess_ratio）を別途通すのが本来の手順。
# 本スクリプトは EQ とノイズ処理までを簡便に確認するためのもの。
set -euo pipefail
IN="${1:?入力ファイル}"; OUT="${2:?出力ファイル}"; SHELF="${3:-5.0}"

# ノイズリダクションは EQ より前。8-10 kHz の S/N が 19 dB しかないため、
# 先に EQ で持ち上げるとヒスも一緒に上がる。
# afftdn に tn/tr は付けない（tn=1 だと nr が完全に無視されることを実測で確認）。
NR="afftdn=nr=16:nf=-50"
HP="highpass=f=75:poles=2,bandreject=f=100:w=6"

EQ="bass=f=263.3:width_type=q:width=1.64:g=4.35,\
equalizer=f=828.5:t=q:w=1.53:g=-6.32,\
equalizer=f=1651.7:t=q:w=1.11:g=-7.06,\
equalizer=f=3409.7:t=q:w=2.2:g=-4.09,\
treble=f=5305.1:width_type=q:width=0.99:g=${SHELF}"

COMP="acompressor=threshold=-20dB:ratio=2.2:attack=10:release=150:makeup=1:knee=6"
MONO="pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1"

ffmpeg -y -i "$IN" -vn -ac 2 -ar 48000 \
  -af "${HP},${NR},${EQ},${COMP},${MONO},loudnorm=I=-13:TP=-1.0:LRA=9" \
  -c:a pcm_f32le "$OUT"

echo "書き出し: $OUT（ハイシェルフ ${SHELF} dB）"
echo "効果の確認: python3 ltass_eval.py \"$OUT\""
