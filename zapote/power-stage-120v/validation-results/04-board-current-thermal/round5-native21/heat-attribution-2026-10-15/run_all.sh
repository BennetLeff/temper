#!/bin/sh
# Heat attribution on the B3 body model (s43, snapshot cb48). About 2.5 h on a loaded 12-core Mac (3 workers).
#   1. the gate's own c18@61 / c22@55 solves (reference for the superposition and gate-estimate checks)
#   2. one body-model solve per attribution term at 0.25 and 0.5 mm (+ two 0.5 mm full-case field controls)
#   3. synthesis, checks, attribution, ceilings, levers -> results.json, tables.md
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SNAP=${SNAP:-$HERE/../snap-cb48}
R5N=$SNAP/zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
mkdir -p "$HERE/gate-runs"
[ -f "$HERE/gate-runs/margins-repro.json" ] || python3 "$R5N/b3-ratings/run_basis.py" --cases c18_h10@61,c22_h10@55 \
    --runs "$HERE/gate-runs" --out "$HERE/gate-runs/margins-repro.json" --workers 3
python3 "$HERE/solve_terms.py" --snap "$SNAP" --workers 3       # cached per term in cache/; delete cache/ to re-solve
python3 "$HERE/analyze.py" --snap "$SNAP" --gate-runs "$HERE/gate-runs"
