#!/bin/sh
# Stage-33 refactor proof (REFACTOR-PROOF.md): re-run every step of gates/chain.sh that comes AFTER the board build,
# with the code in this working tree, on a board that an earlier chain built (BASE). KiCad's zone refill is not
# bit-reproducible from identical inputs (regate.sh), so a fresh build differs in its fills; on the same board file
# every gate and model must reproduce BASE's outputs exactly (refactor_compare.py normalises provenance only).
#   sh refactor_same_input.sh BASE OUT TAG
#   BASE: a chain build dir (section.kicad_pcb, copper-dump.json, ... as chain.sh left it); OUT: new dir; TAG: the
#   chain tag whose kelvin pin holds BASE's board hash (chain.sh wrote it into kelvin_plane.py).
# Side effects as the chain's own: native-21/verification/TAG-all-copper.json.gz, d5-audit.json, the kelvin, task-04
# and B3 outputs in validation-results/ (the task-04 / B3 caches miss: their keys hash the refactored scripts).
set -e
set -o pipefail
BASE=$(cd "$1" && pwd); OUT=$2; TAG=$3
U=$(cd "$(dirname "$0")/../../.." && pwd)
G=$U/native-21/layout/gates
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
KC=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd); cd "$U"
# (drc.json / erc.json are kicad-cli's reports on this same board file, read by the scorecard)
for f in section.kicad_pcb section.kicad_pro section.kicad_dru section.kicad_sch native21.kicad_sym sym-lib-table fp-lib-table \
         drc.json erc.json; do
  cp "$BASE/$f" "$OUT/"
done
BP=$OUT/section.kicad_pcb
# incr_iter.sh tail: copper dump, plan-view barrier
$KP native-21/layout/plot_copper.py --dump "$BP" "$OUT/copper-dump.json" >/dev/null 2>&1
(cd native-21/layout && python3 barrier21.py "$OUT/copper-dump.json" > "$OUT/barrier.txt" 2>&1 || true)
$KP native-21/layout/dump_pads.py "$BP" "$OUT/pads-board.json" >/dev/null 2>&1
python3 native-21/verification/d5_audit.py "$OUT/copper-dump.json" "$OUT/pads-board.json" >/dev/null 2>&1
cp native-21/verification/d5-audit.json "$OUT/d5-audit.json"
# core regate: Rust barrier, DFM, bypass, all-copper extract, power-copper export
sh $G/regate.sh "$OUT" core > "$OUT/blk-core.log" 2>&1
cp "$OUT/native21-all-copper.json.gz" native-21/verification/$TAG-all-copper.json.gz
# stage-18/19 copper gates
python3 validation-results/08-manufacturing-package/native-21/stage18-res-a-creepage/res_a_creepage18.py "$OUT/copper-dump.json" --json "$OUT/res-a-creepage.json" > "$OUT/blk-copper.log" 2>&1
$KP validation-results/08-manufacturing-package/native-21/stage19-pi-si/pi_distances19.py "$BP" --json "$OUT/pi-distances.json" >> "$OUT/blk-copper.log" 2>&1
python3 $G/return_path19.py "$OUT/copper-dump.json" --json "$OUT/return-path.json" >> "$OUT/blk-copper.log" 2>&1
# Kelvin
(cd validation-results/02-protection-timing/kelvin && python3 kelvin_plane.py ../../../native-21/verification/$TAG-all-copper.json.gz $TAG | tail -1 && python3 kelvin_budget.py $TAG | tail -1) > "$OUT/blk-kelvin.log" 2>&1
cp validation-results/02-protection-timing/kelvin/plane-$TAG.json validation-results/02-protection-timing/kelvin/budget-$TAG.json "$OUT/"
# Gerbers + drill (the fab block's copper-layer list comes from layers21, as in chain.sh)
CUL=$(python3 -c "import sys; sys.path.insert(0, 'native-21/layout'); import layers21; print(','.join(layers21.CU))")
mkdir -p "$OUT/fab/gerbers"
$KC pcb export gerbers --output "$OUT/fab/gerbers/" --layers $CUL,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts --subtract-soldermask "$BP" >/dev/null 2>&1
$KC pcb export drill --output "$OUT/fab/gerbers/" --format excellon --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 --generate-report --report-path "$OUT/fab/drill-report.txt" "$BP" >/dev/null 2>&1
(cd "$OUT/fab/gerbers" && zip -X -q ../native-21-gerbers.zip $(ls))
# task 04 (cache misses: run_board.py / summarize.py changed) and B3
sh $G/regate.sh "$OUT" task04 > "$OUT/task04.log" 2>&1
(cd validation-results/04-board-current-thermal/round5-native21/b3 && python3 make_heat_sources.py >/dev/null && python3 run_study.py >/dev/null 2>&1 && python3 ceiling_sweep.py) > "$OUT/blk-thermal.log" 2>&1
# necks, OCP pickup, scorecard
TS=${TAG#native21}
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py $TS > "$OUT/necks.log" 2>&1 && cp ${TS}_necks.json "$OUT/")
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=$OUT/native21-all-copper.json.gz python3 -I run_ocp.py > "$OUT/ocp.log" 2>&1 && cp result.json "$OUT/ocp-result.json" && git restore result.json)
python3 $G/scorecard.py $TAG "$OUT" --audit PASS --json "$OUT/scorecard.json" > "$OUT/scorecard.log" 2>&1
echo SAME_INPUT_DONE
