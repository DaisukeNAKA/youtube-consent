#!/bin/bash
# 実測から導いた補正チェーン。使い方: bash restore.sh 入力.MP4 出力.wav
set -euo pipefail
IN="$1"; OUT="${2:-restored.wav}"
EQ="highpass=f=85:poles=2,\
equalizer=f=300:t=q:w=1.1:g=-4.5,equalizer=f=500:t=q:w=1.0:g=-7.0,\
equalizer=f=750:t=q:w=1.2:g=-3.5,equalizer=f=2600:t=q:w=1.4:g=+2.0,\
equalizer=f=4500:t=q:w=1.2:g=+5.5,treble=f=7000:g=+5.0:width_type=q:width=0.7"
ffmpeg -y -i "$IN" -vn -af \
"${EQ},pan=mono|c0=0.5*c0+0.5*c1,afftdn=nr=12:nf=-45:tn=1:tr=1,\
deesser=i=0.5:m=0.5:f=0.5,\
acompressor=threshold=-18dB:ratio=2:attack=10:release=150:makeup=1:knee=6,\
loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 -c:a pcm_s24le "$OUT"
echo "done: $OUT"
