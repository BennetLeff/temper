#!/bin/sh
# Local Whisper transcript (Apple Silicon, mlx-whisper). The initial prompt
# seeds power-electronics vocabulary that YouTube auto-captions mangle.
# Usage: transcribe.sh <video-id> [model]
set -eu
VID=$1
MODEL=${2:-mlx-community/whisper-large-v3-turbo}
DIR=${MEDIA_ROOT:-$HOME/temper-media}/$VID
mkdir -p "$DIR/whisper"
ffmpeg -nostdin -loglevel error -y -i "$DIR/video.mkv" -vn -ac 1 -ar 16000 "$DIR/whisper/audio.wav"
PROMPT="Induction cooktop teardown. IGBT, MOSFET, GaN, silicon carbide, half-bridge, \
full-bridge, resonant tank, litz wire, ferrite, NTC thermistor, thermocouple, \
infrared, BMS, LFP, kilowatt-hour, inverter, gate driver, MCU, ESP32, STM32, \
pan detection, Impulse Labs, Munro, Sandy Munro."
uvx --from mlx-whisper mlx_whisper "$DIR/whisper/audio.wav" \
    --model "$MODEL" --language en --initial-prompt "$PROMPT" \
    --word-timestamps True --output-format json --output-dir "$DIR/whisper"
mv "$DIR/whisper/audio.json" "$DIR/whisper/video.json"
