#!/bin/zsh
# CM8 network sweep at the datasheet maximum Qrr (TT 180 ns): the s42 network (68 ohm / 4.7 nF) gives 59.7 V/ns on
# the s4b set, over the 56 V/ns screen, so slower turn-on networks are tried (2512 R_on values, C0G 0603 Cgs values),
# then the passing ones go through the full grid at typical and maximum Qrr. Same skip-if-done rule as run_all.sh.
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-3} || echo "FAIL $1 $2"; }
for c in cm8_r68c6p8_tt180 cm8_r68c10_tt180 cm8_r82c4p7_tt180 cm8_r100c4p7_tt180 cm8_r82c6p8_tt180; do run s4b $c; done
echo NET_DONE
# Selected: 68 ohm / 6.8 nF (all 42 S4 rows commutate in the window, 50.75 V/ns at max Qrr). 82/4.7 leaves 6 rows
# without an edge in the window; 68/10, 82/6.8 and 100/4.7 leave all 42 (too slow to evaluate, as the gn study's 100 ohm).
for c in cm8_r68c6p8_tt180 cm8_r68c6p8_tt100; do run full $c; done
run energy cm8_r68c6p8
echo SEL_DONE
