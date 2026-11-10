#!/bin/sh
# Rev G100 board gates, rerunnable.  From instruments/lcr-meter on study/lcr-rev-g100:
#     sh validation/rev-g100/gates.sh
# Builds the board from cad/tools/rev_g100.py, runs the KiCad pipeline and every screen, copies each output that
# lives at a shared path into validation/rev-g100/, then restores those shared paths: manufacturing/, previews/
# and the top-level validation reports stay Rev F on this branch until the review passes (as Rev G did).
set -eu
cd "$(dirname "$0")/../.."
: "${KICAD_PYTHON:=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
: "${RENDER_PYTHON:=$HOME/.local/share/temper/renderenv/bin/python3}"
D=validation/rev-g100
SHARED="manufacturing previews manifest-sha256.json validation/cad-bom-parity.json validation/drc.json validation/erc.json
  validation/fab-check.json validation/via-in-pad-process.json validation/power-spurs/current_check.json
  validation/usb-fs/usb-fs-check.json validation/assembly-paste/paste-check.json
  validation/passive-ratings/passive-ratings-check.json validation/gerber-netlist/gerber-netlist-check.json
  validation/firmware-pins/firmware-pins-check.json"
restore() { git checkout -- $SHARED; }
trap restore EXIT

python3 cad/tools/rev_g100.py --check | tail -1
RENDER_PYTHON="$RENDER_PYTHON" sh cad/rebuild.sh > build/rev-g100-rebuild.log 2>&1 || { tail -20 build/rev-g100-rebuild.log; exit 1; }
cp validation/erc.json validation/drc.json validation/fab-check.json validation/via-in-pad-process.json \
   validation/cad-bom-parity.json $D/
cp manufacturing/drill-report.txt manufacturing/bom-complete.csv manufacturing/bom-jlcpcb.csv \
   manufacturing/cpl-jlcpcb.csv manufacturing/orientation-audit.csv $D/
cp previews/pcb-front.svg previews/pcb-front.png previews/assembly-top.png previews/schematic.pdf $D/
mv previews/schematic-page-8.png $D/          # the protect sheet: untracked in previews/ while that stays Rev F
cp manufacturing/temper-lcr-gerbers.zip build/rev-g100-gerbers.zip

uv run --script validation/gerber-netlist/gerber_netlist_check.py --zip build/rev-g100-gerbers.zip --self-test \
  --out $D/gerber-netlist-check.json | tail -2
python3 validation/power-spurs/current_check.py | tail -1 && cp validation/power-spurs/current_check.json $D/
"$KICAD_PYTHON" validation/usb-fs/usb_fs_check.py | tail -1 && cp validation/usb-fs/usb-fs-check.json $D/
"$KICAD_PYTHON" validation/assembly-paste/paste_check.py | tail -1 && cp validation/assembly-paste/paste-check.json $D/
python3 validation/passive-ratings/passive_ratings_check.py | tail -1 && \
  cp validation/passive-ratings/passive-ratings-check.json $D/
"$KICAD_PYTHON" validation/independent_check.py g100 2>/dev/null | tail -2
"$KICAD_PYTHON" cad/tools/edge_clearance.py $D/edge-clearance.json 2>/dev/null | tail -1
"$KICAD_PYTHON" cad/tools/pour_report.py -o $D/pour-report.json 2>/dev/null | tail -1
LCR_REV=g100 "$KICAD_PYTHON" cad/tools/audit_layout.py validation/layout-audit-rev-g100.json 2>/dev/null | tail -1
python3 validation/firmware-pins/firmware_pins_check.py | tail -1 && cp validation/firmware-pins/firmware-pins-check.json $D/
"$KICAD_PYTHON" validation/pinout-ledger/pinout_check.py --ledger validation/pinout-ledger/ledger-rev-g100.json \
  --package $D 2>/dev/null | tail -1
"$HOME/.local/share/temper/cadenv/bin/python" -c 1 2>/dev/null && LCR_OUT=$D/board-envelope.json \
  "$HOME/.local/share/temper/cadenv/bin/python" validation/enclosure-envelope/board_envelope.py > /dev/null && echo "envelope -> $D/board-envelope.json"
PRICES=$(ls validation/rev-g/prices/jlc-parts-*.json | tail -1)
LCR_MFG_DIR=$D LCR_FAB_QUOTE=$D/fab-quote.json LCR_PRICES="$PRICES" "$KICAD_PYTHON" manufacturing/order_estimate.py 5 \
  2>/dev/null | grep -A0 TOTAL | head -1
# power entry and switcher moved: 5 V trunk / regulators, switcher near-field pickup (vs Rev E, as Rev F's), analog copper
LCR_CPL=$D/cpl-jlcpcb.csv LCR_OUT=$D/regulator-check.json python3 validation/power-spurs/regulator_check.py | tail -1
python3 validation/power-spurs/switcher_pickup.py --rev-f . --out $D/switcher-pickup.json | tail -1
LCR_OUT=$D/drive-budget.json python3 validation/rev-g-protection/drive_budget.py | grep -v '^PASS' || true   # FAIL rows print
sh validation/rev-g100/copper_delta_vs_g.sh > /dev/null && echo "copper delta -> $D/copper-delta-vs-g.json"
# hot-plug (about 3 min on 8 jobs): LCR_L_BOARD=30e-9 LCR_OUT=$D/hotplug-spice.json python3 validation/power-spurs/hotplug_spice.py --jobs 8
echo "gates done: outputs in $D/"
