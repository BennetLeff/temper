#!/bin/zsh
# S6-CMTI: maximum-Qrr (TT 260 ns) runs of the adopted gate network, writes only under ../sims
S=$(cd "$(dirname "$0")" && pwd)
python3 -I $S/gn_s6.py s4screen --cfg split47_1_tt260 --workers 4      # control: must reproduce 106.21 V/ns
python3 -I $S/gn_s6.py s4screen --cfg split68_1_cgs4p7_tt260 --workers 4
python3 -I $S/gn_s6.py s4b --cfg split68_1_cgs4p7_tt260 --workers 4
python3 -I $S/gn_s6.py s4b --cfg split56_1_cgs4p7_tt260 --workers 4
python3 -I $S/gn_s6.py s4b --cfg split100_1_tt260 --workers 4
python3 -I $S/gn_s6.py full --cfg split68_1_cgs4p7_tt260 --workers 4
echo MAXQRR_DONE
python3 -I $S/gn_s6.py s4b --cfg split68_1_cgs4p7_tt125 --workers 4   # control: typical-Qrr chord must read 49.7 on s4b; adds the instantaneous figure
