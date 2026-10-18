#!/bin/sh
# Download a YouTube video (<=2160p), its English auto-captions and metadata.
# Usage: fetch.sh <video-id>
set -eu
VID=$1
OUT=${MEDIA_ROOT:-$HOME/temper-media}/$VID
mkdir -p "$OUT"
cd "$OUT"
uvx yt-dlp -f "bv*[height<=2160]+ba/b" --merge-output-format mkv \
    --write-auto-subs --sub-langs en --sub-format "json3/vtt" \
    --write-info-json -o "video.%(ext)s" \
    "https://www.youtube.com/watch?v=$VID"
# 1080p H.264 proxy: hardware-decodable, used for scene detection and dedupe.
uvx yt-dlp -f "bv*[height<=1080][vcodec^=avc1]" -o "proxy.%(ext)s" \
    "https://www.youtube.com/watch?v=$VID"
