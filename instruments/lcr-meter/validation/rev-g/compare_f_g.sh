#!/bin/sh
# Rev F against Rev G from committed evidence (compare_f_g.py); both BOMs priced from one snapshot.
#   sh validation/rev-g/compare_f_g.sh [REV_F_GIT_REV]      (default study/lcr-in-box)
# Refresh the snapshot first if wanted: <kicad-python> validation/rev-g/prices/fetch_prices.py
set -eu
cd "$(dirname "$0")/../.."
: "${KICAD_PYTHON:=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
REV=${1:-study/lcr-in-box}
PRICES=$(ls validation/rev-g/prices/jlc-parts-*.json | tail -1)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
for f in bom-complete.csv cpl-jlcpcb.csv fab-quote.json; do git show "$REV:./manufacturing/$f" > "$TMP/$f"; done
git show "$REV:./cad/temper-lcr.kicad_pcb" > "$TMP/board.kicad_pcb"
LCR_MFG_DIR="$TMP" LCR_FAB_QUOTE="$TMP/fab-quote.json" LCR_PRICES="$PRICES" LCR_BOARD="$TMP/board.kicad_pcb" \
  "$KICAD_PYTHON" manufacturing/order_estimate.py 5 > /dev/null 2>&1
LCR_MFG_DIR=validation/rev-g LCR_FAB_QUOTE=validation/rev-g/fab-quote.json LCR_PRICES="$PRICES" \
  "$KICAD_PYTHON" manufacturing/order_estimate.py 5 > /dev/null 2>&1
python3 validation/rev-g/compare_f_g.py "$TMP" "$REV"
