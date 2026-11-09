#!/bin/sh
# Rev G's analog copper against Rev F's moved by the Rev G transform (copper_shift_delta.py).
#   sh validation/rev-g/copper_shift_delta.sh [REV_F_GIT_REV]      (default study/lcr-in-box)
set -eu
cd "$(dirname "$0")/../.."
: "${KICAD_PYTHON:=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
REV=${1:-study/lcr-in-box}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
git show "$REV:./cad/temper-lcr.kicad_pcb" > "$TMP/ref.kicad_pcb"
ANALOG=$(python3 -c "import sys; sys.path.insert(0, 'cad/tools'); import pour; print(','.join(sorted(pour.ANALOG)))")
ANALOG="$ANALOG" "$KICAD_PYTHON" validation/rev-g/copper_shift_delta.py dump "$TMP/ref.kicad_pcb" cad/temper-lcr.kicad_pcb "$TMP/dump.json" 2>/dev/null
uv run --no-project --quiet --with shapely python validation/rev-g/copper_shift_delta.py compare "$TMP/dump.json" \
  "$(git rev-parse --short "$REV")" > validation/rev-g/copper-shift-delta.json
cat validation/rev-g/copper-shift-delta.json
