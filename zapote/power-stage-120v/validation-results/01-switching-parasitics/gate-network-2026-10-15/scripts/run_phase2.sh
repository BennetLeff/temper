#!/bin/zsh
# phase 2 (after phase 1): CFD7 finalists on the full grid and the loss grid, controls, Cgd and diode-TT screens
S=$(cd "$(dirname "$0")" && pwd)
L=$S/../sims/log_phase1.txt
until grep -q PHASE1DONE $L; do sleep 20; done
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/gn.py $1 --cfg $2 --workers 4 || echo "FAIL $1 $2"; }
for c in asbuilt split39_1 split47_1 split33_1_cgs2p2; do run full $c; done
for c in asbuilt sym15 split39_1 split47_1 split33_1_cgs2p2 split22_1_cgs4p7; do run loss $c; done
python3 -I $S/gn.py s4screen --cfg sym12 --workers 4 --fix
for c in open12 open22 split39_1_tt50; do run s4screen $c; done
for g in 10 22 47; do for r in 8p2 15 22; do run s4screen split${r}_1_cgd${g}; done; done
for t in 125 260; do for c in asbuilt split39_1 split47_1 split33_1_cgs2p2; do run s4screen ${c}_tt${t}; done; done
echo PHASE2DONE
