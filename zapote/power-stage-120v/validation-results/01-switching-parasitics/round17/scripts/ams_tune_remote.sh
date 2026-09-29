#!/bin/bash
# Round 17: AMS parameter scan on the small column-free leg-A mesh (P1),
# GMRES(100), 4 ranks, capped at 3000 iterations. Baseline needed 9356
# iterations to 5e-11 (round 16); the fixtures need ~80.
set -u
M=${M:?}; OUT=${OUT:?}; ELMER=${ELMER:?}
S="python3 $(dirname "$0")/run_elmer.py --elmer $ELMER $M"
F="--pec 2 3 --port 10 --k -2500 0 0 --hypre-ams --hypre-method 8 --ams-singular --tol 1e-8 --maxit 3000 --np 4"
run() { l=$1; shift; rm -rf $OUT/$l; $S $OUT/$l $F --label $l "$@"; }
run T-base
run T-c13  --solver-line "AMS Cycle Type = Integer 13"
run T-c14  --solver-line "AMS Cycle Type = Integer 14"
run T-thr5 --solver-line "AMS Alpha Threshold = Real 0.5" --solver-line "AMS Beta Threshold = Real 0.5"
run T-rt2  --solver-line "AMS Relax Times = Integer 2"
run T-c13-rt2-thr5 --solver-line "AMS Cycle Type = Integer 13" --solver-line "AMS Relax Times = Integer 2" \
  --solver-line "AMS Alpha Threshold = Real 0.5" --solver-line "AMS Beta Threshold = Real 0.5"
