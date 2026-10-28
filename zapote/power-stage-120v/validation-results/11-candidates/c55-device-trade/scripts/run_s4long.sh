#!/bin/zsh
# S4 binding set in the long window (3.75 us) for the slow turn-on networks: rows without a 20-80 % edge in the
# 0.75 us window are re-run so their commutation edge is measured, not missed.
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-2} || echo "FAIL $1 $2"; }
for c in cm8_r68c6p8_tt180 cfd7_c39_tt260 cfd7_r68c6p8_tt260 cm8_r68c4p7_tt180 cfd7_c39_tt125; do run s4bL $c; done
echo S4L_DONE
