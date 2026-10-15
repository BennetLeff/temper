#!/bin/zsh
# phase 4 (after phase 3): long-window slow-gate check of the finalists
S=$(cd "$(dirname "$0")" && pwd)
until grep -q PHASE3DONE $S/../sims/log_phase3.txt; do sleep 20; done
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/gn.py $1 --cfg $2 --workers 4 || echo "FAIL $1 $2"; }
for c in asbuilt split39_1 split47_1 split33_1_cgs2p2 c8_asbuilt c8_split27_1 cm8_asbuilt cm8_split27_1; do run slowgate $c; done
echo PHASE4DONE
