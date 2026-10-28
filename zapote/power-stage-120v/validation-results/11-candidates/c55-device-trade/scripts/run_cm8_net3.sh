#!/bin/zsh
# CM8 network sweep, round 3: turn-on resistor alone (Cgs stays the as-built 1 nF), 68 / 100 / 150 ohm, at maximum Qrr.
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-2} || echo "FAIL $1 $2"; }
for n in r100 r68 r150; do run s4b cm8_${n}_tt180; run s2q cm8_${n}_tt180; done
echo NET3_DONE
