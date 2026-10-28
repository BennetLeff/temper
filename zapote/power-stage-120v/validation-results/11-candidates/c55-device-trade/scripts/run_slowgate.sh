#!/bin/zsh
# Turn-on delay (gate-network study criterion, its 16-run 'slowgate' grid): CFD7 on the s42 network is the control
# (committed 4.37 / 9.04 V at 20 A, 4.76 / 9.26 V at 37 A, 1 / 2 us); CM8 networks and SiC for comparison.
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-3} || echo "FAIL $1 $2"; }
for c in cfd7_c39 cm8_r150 cm8_r120 cm8_r100 cm8_r68 cm8_r39 cm8_r68c4p7; do run slowgate $c; done
echo SG_DONE
