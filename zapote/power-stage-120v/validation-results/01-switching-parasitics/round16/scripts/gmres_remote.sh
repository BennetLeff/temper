#!/bin/bash
# Round 16: Hypre GMRES(100) + singular AMS. BiCGStab + AMS reached 7.5e-9 on
# the board at iteration 2000 and then broke down; GMRES residuals cannot rise.
# Fixtures first (qualification), then the board on 8 ranks.
set -u
R=${R:?}; OUT=${OUT:?}; ELMER=${ELMER:?}
S="python3 $(dirname "$0")/run_elmer.py --elmer $ELMER"
F="--hypre-ams --hypre-method 8 --ams-singular --tol 1e-10 --maxit 5000"
$S $R/sect-h0p25.msh  $OUT/G-sect-boundary --pec 2 --port 4 --k 0 0 100 $F --label G-sect-boundary
$S $R/secti-h0p25.msh $OUT/G-sect-interior --pec 2 --port 4 --k 0 0 100 $F --label G-sect-interior
$S $R/sect2.msh $OUT/G-sect2-11 --pec 2 --port 4 --k 0 0 100 $F --label G-sect2-L11
$S $R/sect2.msh $OUT/G-sect2-22 --pec 2 --port 5 --k 0 0 100 $F --label G-sect2-L22
$S $R/sect2.msh $OUT/G-sect2-12 --pec 2 --port 4 --k 0 0 100 --port2 5 --k2 0 0 100 $F --label G-sect2-both
$S $R/thick-m40-h0p35.msh $OUT/G-thick-h0p35 --pec 2 --port 4 --k 0 0 100 $F --label G-thick-h0p35
$S $R/legA-small-thin.msh $OUT/G-board-np8 --pec 2 3 --port 10 --k -2500 0 0 $F --np 8 --label G-board-np8
