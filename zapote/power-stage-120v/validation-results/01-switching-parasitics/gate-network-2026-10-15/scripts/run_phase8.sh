#!/bin/zsh
# phase 8 (after phase 5): C8 diode TT for its datasheet Qrr; C8 at that Qrr; CFD7 typical-Qrr finalists on the full grid
S=$(cd "$(dirname "$0")" && pwd)
until grep -q PHASE5DONE $S/../sims/log_phase6.txt; do sleep 20; done
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/gn.py $1 --cfg $2 --workers 4 || echo "FAIL $1 $2"; }
python3 -I $S/qrr.py --workers 4
for tt in 60 80; do for r in 27 39 47 56 68; do run s4b c8_split${r}_1_tt${tt}; done; done
for c in c8_split27_1 c8_split39_1 cm8_split39_1 cm8_split47_1; do run s4b $c; done
for c in split56_1_cgs4p7_tt125 split100_1_tt125; do run full $c; done
for c in split56_1_cgs4p7 split100_1 split68_1_cgs4p7; do run slowgate $c; run loss $c; done
echo PHASE8DONE
