#!/bin/sh
# Re-grab every kept frame (frames/index.csv) at full source resolution from
# video.mkv, into frames/keep4k/ under the same name. Input seeking lands on
# the nearest preceding keyframe and decodes forward, so each still costs a
# few seconds of AV1 decode; JOBS run in parallel.
# Usage: stills_4k.sh <video-id>
set -eu
DIR=${MEDIA_ROOT:-$HOME/temper-media}/$1
export VIDEO=$DIR/video.mkv OUT=$DIR/frames/keep4k
mkdir -p "$OUT"
# Each line "tNNNNN.N.jpg seconds" becomes $0 $1 of the inner shell.
tail -n +2 "$DIR/frames/index.csv" | cut -d, -f1,2 | tr ',' ' ' |
    xargs -P "${JOBS:-6}" -L 1 sh -c \
        '[ -s "$OUT/$0" ] || ffmpeg -nostdin -loglevel error -ss "$1" -i "$VIDEO" -frames:v 1 -q:v 2 "$OUT/$0"'
ls "$OUT" | wc -l
