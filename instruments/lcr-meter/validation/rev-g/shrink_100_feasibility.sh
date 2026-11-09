#!/bin/sh
# Rev G back to 100 x 100 mm: density of the analog core against the rest (shrink_100_feasibility.py).
set -eu
cd "$(dirname "$0")/../.."
: "${KICAD_PYTHON:=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
"$KICAD_PYTHON" validation/rev-g/shrink_100_feasibility.py dump cad/temper-lcr.kicad_pcb "$TMP/parts.json" 2>/dev/null
uv run --no-project --quiet --with shapely python validation/rev-g/shrink_100_feasibility.py compare "$TMP/parts.json" "$PWD" \
  > validation/rev-g/shrink-100-feasibility.json
cat validation/rev-g/shrink-100-feasibility.json
