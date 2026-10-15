#!/bin/sh
# Pull candidate frames from the 1080p H.264 proxy (hardware-decoded; 4K AV1
# software decode runs ~0.6x realtime on this Mac): every scene cut across the
# whole video, plus one frame per second inside [START, END) seconds where the
# camera lingers on hardware. Full-resolution stills for the frames that
# survive dedupe come from stills_4k.sh.
# Usage: extract_frames.sh <video-id> <start-s> <end-s> [scene-threshold]
set -eu
VID=$1
START=$2
END=$3
THRESH=${4:-0.25}
DIR=${MEDIA_ROOT:-$HOME/temper-media}/$VID
RAW=$DIR/frames/raw
mkdir -p "$RAW"

# Scene cuts: showinfo logs pts_time per selected frame.
ffmpeg -nostdin -loglevel info -hwaccel videotoolbox -i "$DIR/proxy.mp4" \
    -vf "select='gt(scene,$THRESH)',showinfo" -fps_mode vfr -q:v 3 \
    "$RAW/scene_%05d.jpg" 2> "$RAW/scene_showinfo.log"
grep -o 'pts_time:[0-9.]*' "$RAW/scene_showinfo.log" | cut -d: -f2 > "$RAW/scene_times.txt"

# Dense window: -ss before -i seeks fast; frame N is at START + N seconds.
ffmpeg -nostdin -loglevel error -hwaccel videotoolbox -ss "$START" -to "$END" \
    -i "$DIR/proxy.mp4" -vf "fps=1" -q:v 3 -start_number 0 "$RAW/dense_%05d.jpg"
echo "$START" > "$RAW/dense_start.txt"
