#!/bin/zsh
# IMW65R026M2H on the s42 network unchanged (68 ohm / 4.7 nF): if it passes, the SiC change is the four FETs plus
# R9 / R17 only. Full grid, turn-on delay, loss grid at DT 200 ns, S2 charge.
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-4} || echo "FAIL $1 $2"; }
run full sic26_15_r68c4p7
run slowgate sic26_15_r68c4p7
run eA200 sic26_15_r68c4p7
echo SICS42_DONE
