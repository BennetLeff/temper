#!/bin/zsh
# CM8 network sweep, round 4: resistor-only turn-on (Cgs 1 nF) is the only family that keeps S2 (488 V) and the S4
# off-gate (< 1 V) clean; 100 / 120 / 150 ohm in the long window (their slow edges leave the 0.75 us window).
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-3} || echo "FAIL $1 $2"; }
for n in r150 r120 r100; do run s4bL cm8_${n}_tt180; done
run s2q cm8_r150_tt180
echo NET4_DONE
