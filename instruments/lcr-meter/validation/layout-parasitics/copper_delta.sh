#!/bin/sh
# Analog copper between two boards: is the extraction (extracted_revf.json, run on the board named there)
# still the board's?  Step 1 (KiCad Python) dumps analog-net tracks / pads / zones and the GND fills of both
# boards; step 2 (Python + shapely) compares them.  Writes copper-delta.json here.
#   sh validation/layout-parasitics/copper_delta.sh <git rev of the reference board>
set -eu
cd "$(dirname "$0")/../.."
: "${KICAD_PYTHON:=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
REV=$1
TMP=$(mktemp -d)
git show "$REV:./cad/temper-lcr.kicad_pcb" > "$TMP/ref.kicad_pcb"
ANALOG=$(python3 -c "import sys; sys.path.insert(0, 'cad/tools'); import pour; print(','.join(sorted(pour.ANALOG)))")
ANALOG="$ANALOG" "$KICAD_PYTHON" validation/layout-parasitics/copper_delta_dump.py "$TMP/ref.kicad_pcb" cad/temper-lcr.kicad_pcb "$TMP/dump.json" 2>/dev/null
uv run --no-project --quiet --with shapely python validation/layout-parasitics/copper_delta_compare.py "$TMP/dump.json" "$REV" > validation/layout-parasitics/copper-delta.json
cat validation/layout-parasitics/copper-delta.json
rm -rf "$TMP"
