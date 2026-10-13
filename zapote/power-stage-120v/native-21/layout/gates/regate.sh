#!/bin/sh
# Re-run every downstream gate on a built board: $1 = build dir (section.kicad_pcb, copper-dump.json).
set -e
U=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$U"
B=$1/section.kicad_pcb
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
MP=${MP:-/Users/bennet/Miniforge3/bin/python3}
R=validation-results/04-board-current-thermal/round5-native21
$KP tools/copper_dump.py $B $1/evidence.json >/dev/null 2>&1
ZAPOTE_POWER_BARRIER_BIN=${ZAPOTE_POWER_BARRIER_BIN:-/Users/bennet/Desktop/temper/target-shared/debug/zapote-power-barrier} python3 native-21/layout/barrier_gate21.py $1/evidence.json > $1/barrier-gate-rust.json
$KP tools/jlc_dfm_check.py $B > $1/jlc-dfm.json 2>/dev/null
# local bypass: every comparator / Schmitt buffer / rail monitor has its 100 nF within the stage-19 limits (fails the gate)
$KP native-21/layout/gates/bypass_check.py $B $1/bypass-check.json > $1/bypass-check.txt 2>&1 || { grep -v -i "wxapp\|Debug\|assert" $1/bypass-check.txt >&2; echo "BYPASS GATE FAILED" >&2; exit 1; }
$KP validation-results/04-board-current-thermal/round4/reextract-b3/extract_geometry.py $B $1/native21-all-copper.json.gz >/dev/null 2>&1
$KP tools/export_power_copper.py $B $R/inputs/power_copper.json.gz >/dev/null 2>&1
cd $R && rm -f outputs/*-pl*.json outputs/*.npz outputs/summary.json
$MP ../round3/scripts/kit_topology_native13.py inputs/power_copper.json.gz outputs/kit_topology_p0125.json 0.125 >/dev/null &
$MP ../round3/scripts/kit_topology_native13.py inputs/power_copper.json.gz outputs/kit_topology_p00625.json 0.0625 >/dev/null &
WORKERS=6 $MP run_cases.py > outputs/run_cases.log 2>&1
$MP run_board.py --net bus_p --source J8.1:15 --sink Q2.2 --pitch 0.25 --plating 18 --name bus-dc-q2-p025-pl18 >/dev/null
$MP run_board.py --net bus_p --source J8.1:15 --sink Q2.2 --pitch 0.0625 --plating 18 --name bus-dc-q2-p00625-pl18 >/dev/null
wait
$MP summarize.py | tail -1
python3 compare_native17.py > outputs/compare_native17.txt
