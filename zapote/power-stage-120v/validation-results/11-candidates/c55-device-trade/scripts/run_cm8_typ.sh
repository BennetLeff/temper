#!/bin/zsh
# CM8 resistor-only networks at datasheet typical Qrr (TT 100 ns), binding S4 set in the long window: does any network
# inside the turn-on budget at least match the CFD7 status (pass at typical, 0.98 of rating at maximum)?
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-3} || echo "FAIL $1 $2"; }
for n in r68 r82 r100; do run s4bL cm8_${n}_tt100; done
run s4bL cm8_r82_tt180
echo TYP_DONE
