#!/bin/zsh
# phase 6 (after phase 4): diode TT 125 ns (Qrr ~ datasheet typical, D-24 map) - R_on / Cgs sweep on the binding S4 set;
# then the Qrr fixture (phase 7) and the common-39-ohm CM8 runs (phase 5)
S=$(cd "$(dirname "$0")" && pwd)
until grep -q PHASE4DONE $S/../sims/log_phase4.txt; do sleep 20; done
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/gn.py $1 --cfg $2 --workers 4 || echo "FAIL $1 $2"; }
for c in split39_1 split47_1 split39_1_tt125 split47_1_tt125 asbuilt_tt125; do run s4b $c; done
for b in split56_1 split68_1 split82_1 split100_1 split47_1_cgs2p2 split56_1_cgs2p2 split39_1_cgs4p7 split47_1_cgs4p7 split56_1_cgs4p7 split33_1_cgs4p7 split22_1_cgs4p7 split68_1_cgs4p7 split120_1 split39_1_cgs2p2 split68_1_cgs2p2; do run s4b ${b}_tt125; done
echo PHASE6DONE
python3 -I $S/qrr.py --workers 4
echo PHASE7DONE
for c in cm8_split39_1 c8_split39_1; do run full $c; done
for c in cm8_split39_1 c8_split39_1 split39_1; do run slowgate $c; done
for c in cm8_split39_1 c8_split39_1; do run loss $c; done
echo PHASE5DONE
