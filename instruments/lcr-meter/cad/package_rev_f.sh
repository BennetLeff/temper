#!/bin/sh
# Rev F manufacturing package in manufacturing/rev-f/, leaving Rev E's manufacturing/ untouched.
# Builds the Rev F board in cad/ (rebuild.sh: ERC, DRC with parity, Gerbers, drill, BOM, CPL with the
# placement-library rotation offsets, DFM audit), copies the outputs into manufacturing/rev-f/,
# restores the Rev E outputs that rebuild.sh overwrote, hashes and zips the Rev F package, and runs the
# order estimate for 2 and 5 boards against manufacturing/rev-f/fab-quote.json.
# No purchasing or uploads.
set -eu
cd "$(dirname "$0")/.."
: "${KICAD_PYTHON:=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
LCR_SKIP_ARCHIVE=1 RENDER_PYTHON="${RENDER_PYTHON:-true}" sh cad/rebuild.sh
OUT=manufacturing/rev-f
rm -rf "$OUT/gerbers"
mkdir -p "$OUT/gerbers"
cp manufacturing/gerbers/* "$OUT/gerbers/"
for f in bom-complete.csv bom-jlcpcb.csv cpl-jlcpcb.csv orientation-audit.csv drill-report.txt; do
  cp "manufacturing/$f" "$OUT/$f"
done
for f in erc.json drc.json via-in-pad-process.json; do cp "validation/$f" "$OUT/$f"; done
git checkout -- manufacturing/gerbers manufacturing/bom-complete.csv manufacturing/bom-jlcpcb.csv \
  manufacturing/cpl-jlcpcb.csv manufacturing/orientation-audit.csv manufacturing/drill-report.txt \
  previews validation/drc.json validation/erc.json validation/via-in-pad-process.json cad/temper-lcr.kicad_pro
for n in 2 5; do
  LCR_MFG_DIR="$OUT" LCR_FAB_QUOTE="$OUT/fab-quote.json" "$KICAD_PYTHON" manufacturing/order_estimate.py "$n" > /dev/null
done
python3 cad/archive_package.py --rev-f
