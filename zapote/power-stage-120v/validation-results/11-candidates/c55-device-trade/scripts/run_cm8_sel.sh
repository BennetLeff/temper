#!/bin/zsh
# CM8 representative network: R_on 100 ohm 2512, Cgs 1 nF (resistor only). It is the slowest CM8 network inside the
# adopted CFD7 network's turn-on budget (slowgate: 3.76 / 9.00 V at 1 / 2 us against 4.37 / 9.04 V); 150 ohm (the
# only one under 56 V/ns at maximum Qrr) is too slow (1.10 / 5.93 V). Full grid in the long window at maximum Qrr,
# and the loss grid. (cm8_r150_tt180 fullL was run first and is kept as the record of the 150 ohm result.)
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-4} || echo "FAIL $1 $2"; }
run energy cm8_r100
run fullL cm8_r100_tt180
echo SEL_DONE
