#!/bin/sh
# Captions + metadata only (no video) for a list of YouTube ids, then a plain
# "[mm:ss] text" transcript per id. Media stays outside the repo.
# Usage: fetch_captions.sh <video-id> [<video-id> ...]
set -eu
for VID in "$@"; do
    OUT=${MEDIA_ROOT:-$HOME/temper-media}/$VID
    mkdir -p "$OUT"
    (cd "$OUT" && uvx yt-dlp --skip-download --write-auto-subs --write-subs \
        --sub-langs "en.*,en" --sub-format json3 --write-info-json \
        -o "video.%(ext)s" "https://www.youtube.com/watch?v=$VID" > fetch_captions.log 2>&1) || echo "fail $VID"
    python3 "$(dirname "$0")/captions_to_text.py" "$OUT" || echo "no captions $VID"
done
