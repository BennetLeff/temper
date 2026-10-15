#!/bin/zsh
# phase 1: S4 screen (56 runs per config, 4 ngspice workers), then the controls
S=$(cd "$(dirname "$0")" && pwd)
cfgs=(asbuilt asbuilt_bom sym10 sym12 sym15 sym18 sym22 short24_24 short44_44)
for ron in 15 22 27 33 39 47; do for roff in 1 4p7 8p2; do cfgs+=(split${ron}_${roff}); done; done
cfgs+=(split8p2_1_cgs2p2 split22_1_cgs2p2 split33_1_cgs2p2 split8p2_1_cgs4p7 split22_1_cgs4p7 split33_1_cgs4p7)
cfgs+=(c8_asbuilt c8_sym10 c8_sym12 c8_sym15 c8_sym18 c8_sym22)
for ron in 15 22 27 33 39 47 56 68; do cfgs+=(c8_split${ron}_1); done
cfgs+=(cm8_asbuilt cm8_sym10 cm8_sym12 cm8_sym15 cm8_sym18 cm8_sym22 cm8rgc_sym10 cm8rgc_sym12 cm8rgc_sym15)
for ron in 15 22 27 33 39 47 56 68; do cfgs+=(cm8_split${ron}_1); done
for c in $cfgs; do
  [ -f $S/../sims/$c/s4screen/results.json ] && continue
  python3 -I $S/gn.py s4screen --cfg $c --workers 4 || echo "FAIL $c"
done
echo PHASE1DONE
