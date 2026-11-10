#!/bin/sh
# G100's analog copper and GND fill against Rev G's, untransformed (G100 keeps Rev G's frame above y 107; the moves
# are the power entry, the switcher block and the digital south).  copper_shift_delta.py with LCR_SHIFT=0.
#   sh validation/rev-g100/copper_delta_vs_g.sh [REV_G_GIT_REV]      (default study/lcr-rev-g)
set -eu
cd "$(dirname "$0")/../.."
: "${KICAD_PYTHON:=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
REV=${1:-study/lcr-rev-g}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
git show "$REV:./cad/temper-lcr.kicad_pcb" > "$TMP/ref.kicad_pcb"
ANALOG=$(python3 -c "import sys; sys.path.insert(0, 'cad/tools'); import pour; print(','.join(sorted(pour.ANALOG)))")
ANALOG="$ANALOG" "$KICAD_PYTHON" validation/rev-g/copper_shift_delta.py dump "$TMP/ref.kicad_pcb" cad/temper-lcr.kicad_pcb "$TMP/dump.json" 2>/dev/null
LCR_SHIFT=0 uv run --no-project --quiet --with shapely python validation/rev-g/copper_shift_delta.py compare "$TMP/dump.json" \
  "$(git rev-parse --short "$REV")" > validation/rev-g100/copper-delta-vs-g.json
cat validation/rev-g100/copper-delta-vs-g.json
