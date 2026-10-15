#!/bin/sh
# Fallback when YouTube rate-limits the subtitle endpoint (HTTP 429): fetch the
# audio stream only, transcribe it locally with mlx-whisper, and write the same
# "[mm:ss] text" captions.txt that captions_to_text.py produces. Media stays in
# ~/temper-media/<id>/ (outside the repo).
# Usage: audio_transcript.sh <video-id> [<video-id> ...]
set -eu
MODEL=${MODEL:-mlx-community/whisper-large-v3-turbo}
for VID in "$@"; do
    DIR=${MEDIA_ROOT:-$HOME/temper-media}/$VID
    mkdir -p "$DIR/whisper"
    (cd "$DIR" && uvx yt-dlp -f "bestaudio" --write-info-json -o "audio.%(ext)s" \
        "https://www.youtube.com/watch?v=$VID" > fetch_audio.log 2>&1) || { echo "fail $VID"; continue; }
    A=$(ls "$DIR"/audio.* | grep -v info.json | head -1)
    ffmpeg -nostdin -loglevel error -y -i "$A" -vn -ac 1 -ar 16000 "$DIR/whisper/audio.wav"
    uvx --from mlx-whisper mlx_whisper "$DIR/whisper/audio.wav" --model "$MODEL" \
        --language en --output-format json --output-dir "$DIR/whisper" > /dev/null
    python3 - "$DIR" <<'PY'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
segs = json.loads((d / "whisper" / "audio.json").read_text())["segments"]
lines = [f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}] {s['text'].strip()}" for s in segs]
(d / "captions.txt").write_text("\n".join(lines) + "\n")
print(d.name, len(lines), "segments")
PY
    rm -f "$DIR/whisper/audio.wav"
done
