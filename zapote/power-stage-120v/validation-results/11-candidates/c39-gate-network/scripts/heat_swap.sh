#!/bin/bash
# Separate candidate 39's copper effect from its heat effect: the B3 ratings basis (run_basis.py) on the CURRENT copper
# (run_study.GEOM) with the stage-41 c28 heat file (integration 18187575d: R_on 8.2 ohm 1206, Cgs 1 nF) in place of the
# stage-42 one. The heat file is swapped in place for the run and restored on exit (trap), so nothing committed moves.
#   bash heat_swap.sh RUNS_DIR OUT.json
set -eu
U=$(cd "$(dirname "$0")/../../../.." && pwd)
D=$U/validation-results/04-board-current-thermal/round5-native21
H=$D/b3/inputs/native21-board-heat-sources-c28.json
RUNS=$1; OUT=$2
TMP=$(mktemp -d)
cp "$H" "$TMP/s42.json"
trap 'cp "$TMP/s42.json" "$H"; rm -r "$TMP"' EXIT
git -C "$U" show 18187575d:zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21/b3/inputs/native21-board-heat-sources-c28.json > "$H"
mkdir -p "$RUNS"
cd "$D/b3-ratings" && python3 run_basis.py --workers 4 --runs "$RUNS" --out "$OUT" || true
