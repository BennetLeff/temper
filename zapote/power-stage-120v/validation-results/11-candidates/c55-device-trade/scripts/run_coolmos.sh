#!/bin/zsh
# CoolMOS chain (CFD7 and CM8). Sequential; each step 8 ngspice workers. Existing results.json are kept.
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/trade.py $1 --dev $2 --workers ${W:-8} || echo "FAIL $1 $2"; }
# gate charge basis (B3 heat): CFD7 control = 382.6 nC (device study S2 worst), CM8 on the same network
run s2q cfd7_c39__q; run s2q cm8_39__q
# max-Qrr control: the adopted network at TT 260 ns must give 68.16 V/ns (S6 study) on the full grid
run full cfd7_c39_tt260
# CM8 (proxy B): vendor TT, typical (TT 90) and maximum (TT 170) Qrr; on its own 39 ohm network and on the s42 network
for c in cm8_39 cm8_39_tt90 cm8_39_tt170 cm8_c39_tt90 cm8_c39_tt170; do run full $c; done
# loss grids (long window)
for c in cfd7_c39 cfd7_8p2 cm8_39; do run energy $c; done
echo COOLMOS_DONE
