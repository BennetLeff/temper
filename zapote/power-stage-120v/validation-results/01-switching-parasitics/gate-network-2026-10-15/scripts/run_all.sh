#!/bin/zsh
# Full chain of the gate-network study, sequential, 4 ngspice workers (about 5 h on a loaded 12-core Mac).
# Prerequisite: ../dl/cm8/c8_600/IFX_C8_600V.lib unzipped from
#   https://www.infineon.com/assets/row/public/documents/24/50/infineon-600-v-coolmos-8-simulationmodels-en.zip
#   (sha256 32050b46b1904af3a6e838503104d9da95d6c7058de3a710f8ce9f6415fb2f69)
# Existing results.json files are kept (delete a sims/<cfg>/<grid> folder to re-run it).
set -u
S=$(cd "$(dirname "$0")" && pwd)
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/gn.py $1 --cfg $2 --workers 4 || echo "FAIL $1 $2"; }
# controls first: the as-built deck against the committed device-study rows
run repro asbuilt; run erepro asbuilt
# phase 1: S4 screen
for c in asbuilt asbuilt_bom sym10 sym12 sym15 sym18 sym22 short24_24 short44_44 open12 open22; do run s4screen $c; done
python3 -I $S/gn.py s4screen --cfg sym12 --workers 4 --fix
for r in 10 12 15 18 22; do run s4screen rext$r; done
for ron in 15 22 27 33 39 47; do for roff in 1 4p7 8p2; do run s4screen split${ron}_${roff}; done; done
for cg in 2p2 4p7; do for ron in 8p2 22 33; do run s4screen split${ron}_1_cgs${cg}; done; done
for g in 10 22 47; do for r in 8p2 15 22; do run s4screen split${r}_1_cgd${g}; done; done
run s4screen split39_1_tt50
for t in 125 260; do for c in asbuilt split39_1 split47_1 split33_1_cgs2p2; do run s4screen ${c}_tt${t}; done; done
for c in c8_asbuilt c8_sym10 c8_sym12 c8_sym15 c8_sym18 c8_sym22 cm8_asbuilt cm8_sym10 cm8_sym12 cm8_sym15 cm8_sym18 cm8_sym22; do run s4screen $c; done
for ron in 15 22 27 33 39 47 56 68; do run s4screen c8_split${ron}_1; run s4screen cm8_split${ron}_1; done
for r in 8p2 10 12 15; do run s4screen cm8rgc_rext$r; done
# finalists: full grid (S1 ZVS, S2, S4, S5, both ESL) and the loss grid
for c in asbuilt split39_1 split47_1 split33_1_cgs2p2 c8_split27_1 cm8_split27_1 c8_asbuilt cm8_asbuilt; do run full $c; done
for c in asbuilt sym15 split39_1 split47_1 split33_1_cgs2p2 split22_1_cgs4p7 c8_asbuilt c8_split27_1 cm8_asbuilt cm8_split27_1; do run loss $c; done
for c in asbuilt split39_1 split47_1 split33_1_cgs2p2 c8_asbuilt c8_split27_1 cm8_asbuilt cm8_split27_1; do run slowgate $c; done
for c in cm8_split39_1 c8_split39_1; do run full $c; run loss $c; done
for c in cm8_split39_1 c8_split39_1 split39_1; do run slowgate $c; done
# diode TT 125 ns (Qrr ~ datasheet typical): binding S4 set (leg A, dir 0, 170/198/280 V, all corners, both ESL)
for c in split39_1 split47_1 split39_1_tt125 split47_1_tt125 asbuilt_tt125; do run s4b $c; done
for b in split56_1 split68_1 split82_1 split100_1 split47_1_cgs2p2 split56_1_cgs2p2 split39_1_cgs4p7 split47_1_cgs4p7 split56_1_cgs4p7 split33_1_cgs4p7 split22_1_cgs4p7 split68_1_cgs4p7 split120_1 split39_1_cgs2p2 split68_1_cgs2p2; do run s4b ${b}_tt125; done
python3 -I $S/qrr.py --workers 4
for tt in 60 80; do for r in 27 39 47 56 68; do run s4b c8_split${r}_1_tt${tt}; done; done
for c in c8_split27_1 c8_split39_1 cm8_split39_1 cm8_split47_1; do run s4b $c; done
for c in split56_1_cgs4p7_tt125 split100_1_tt125; do run full $c; done
for c in split56_1_cgs4p7 split100_1 split68_1_cgs4p7; do run slowgate $c; run loss $c; done
run full split68_1_cgs4p7_tt125
python3 -I $S/fit_rg.py
python3 -I $S/analyze.py
echo ALLDONE
