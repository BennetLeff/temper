#!/bin/zsh
# SiC with a shorter dead time (200 ns; R9 / R17 change), loss grid leg A, long window.
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-3} || echo "FAIL $1 $2"; }
run eA200 sic26_15_r8p2
run eA200 sic26_18_r8p2
echo SICDT_DONE
