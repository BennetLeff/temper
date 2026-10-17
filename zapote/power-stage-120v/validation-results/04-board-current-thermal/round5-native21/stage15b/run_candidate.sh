#!/bin/sh
# Stage 15b candidate pipeline: KiCad edit + refill -> DRC -> copper export -> all 14 A4 cases -> B3 c28.
#   sh run_candidate.sh <name> [pitches]   (candidates/<name>.json; pitches default "1.0")
set -e
S=$(cd "$(dirname "$0")" && pwd)
U=$(cd "$(dirname "$0")/../../../.." && pwd)
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
KC=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
N=$1; P=${2:-1.0}
D=$S/kicad/$N
$KP $S/kedit.py $S/kicad/base/section.kicad_pcb $S/candidates/$N.json $D > /dev/null
if [ -z "$NODRC" ]; then $KC pcb drc --format json --severity-error --schematic-parity -o $D/drc.json $D/section.kicad_pcb > /dev/null; fi
$KP $U/tools/export_power_copper.py $D/section.kicad_pcb $D/power_copper.json.gz > /dev/null
$KP $S/extract_geometry.py $D/section.kicad_pcb $D/all-copper.json.gz > /dev/null
python3 $S/a4_cases.py $D/power_copper.json.gz $S/a4/$N
python3 $S/b3_eval.py $N $D/all-copper.json.gz $S/a4/$N $D/power_copper.json.gz "$P"
