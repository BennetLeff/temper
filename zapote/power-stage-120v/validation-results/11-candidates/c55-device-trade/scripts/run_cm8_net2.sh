#!/bin/zsh
# CM8 network sweep, round 2: Cgs >= 4.7 nF fails S2 (die VDS 608-661 V, fault turn-off at 71 A, gate-loop ringing with
# the CM8's 1 ohm Rg,int) and the S4 off-gate screen at 150 C; 39 ohm / 1 nF fails S4 dv/dt at datasheet Qrr. Try
# 2.2 nF with 47 / 56 / 68 ohm: S4 binding set at typical and maximum Qrr, and the S2 rows (s2q = the full grid's S2).
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-3} || echo "FAIL $1 $2"; }
for n in r56c2p2 r68c2p2 r47c2p2 r82c2p2; do run s4b cm8_${n}_tt180; run s2q cm8_${n}_tt180; done
for n in r56c2p2 r68c2p2 r47c2p2 r82c2p2; do run s4b cm8_${n}_tt100; done
echo NET2_DONE
