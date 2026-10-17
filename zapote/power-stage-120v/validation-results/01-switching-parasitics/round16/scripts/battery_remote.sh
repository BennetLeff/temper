#!/bin/bash
# Round 16 on the 24-core Linux box: qualify Hypre AMS on the exact fixtures,
# then solve the small leg-A board mesh (P1 alone) with AMS on 1 and 8 ranks
# and with the direct solver as the reference. AMS runs in singular mode
# (no conductivity anywhere), gated on Hypre's own iteration summary.
set -u
R=${R:?}; OUT=${OUT:?}; ELMER=${ELMER:?}
S="python3 $(dirname "$0")/run_elmer.py --elmer $ELMER"
F="--hypre-ams --hypre-method 7 --ams-singular --tol 1e-10 --maxit 5000"
$S $R/sect-h0p25.msh  $OUT/A-sect-boundary --pec 2 --port 4 --k 0 0 100 $F --label A-sect-boundary
$S $R/secti-h0p25.msh $OUT/A-sect-interior --pec 2 --port 4 --k 0 0 100 $F --label A-sect-interior
$S $R/sect2.msh $OUT/A-sect2-11 --pec 2 --port 4 --k 0 0 100 $F --label A-sect2-L11
$S $R/sect2.msh $OUT/A-sect2-22 --pec 2 --port 5 --k 0 0 100 $F --label A-sect2-L22
$S $R/sect2.msh $OUT/A-sect2-12 --pec 2 --port 4 --k 0 0 100 --port2 5 --k2 0 0 100 $F --label A-sect2-both
$S $R/thick-m40-h0p35.msh $OUT/A-thick-h0p35 --pec 2 --port 4 --k 0 0 100 $F --label A-thick-h0p35
B="$R/legA-small-thin.msh --pec 2 3 --port 10 --k -2500 0 0"
$S $B $OUT/A-board-np8 $F --np 8 --label A-board-np8
$S $B $OUT/A-board-np1 $F --label A-board-np1
$S $B $OUT/D-board --label D-board
