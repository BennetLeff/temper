#!/bin/zsh
# All 336 S4 rows of the full grid in the long window, for the networks whose short-window S4 rows lack an edge
# (the CFD7 on the s42 network: 144 of 336 rows at 27 C have no 20-80 % edge inside 0.75 us).
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-3} || echo "FAIL $1 $2"; }
for c in cfd7_c39_tt260 cfd7_c39_tt125; do run s4L $c; done
echo S4FL_DONE
