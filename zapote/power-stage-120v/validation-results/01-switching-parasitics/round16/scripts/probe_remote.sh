#!/bin/bash
# Round 16 bisection probe: mesh one leg-A variant and run P1 with Hypre
# BiCGStab + singular AMS on 8 ranks, capped at 400 iterations. A healthy
# model converges in well under that (fixtures: 56-81 iterations).
# usage: probe_remote.sh LABEL CLOSURES [extra mesher args...]
set -u
LABEL=$1; CL=$2; shift 2
D=$(cd "$(dirname "$0")/.." && pwd); OUT=${OUT:?}; ELMER=${ELMER:?}
X=$D/../../04-board-current-thermal/round4/reextract-b3/inputs/native17-all-copper.json.gz
M=$OUT/$LABEL.msh
python3 $D/scripts/mesh25d_hybrid.py $X $M --leg A --closures $D/$CL --arch-h 1 --h-edge 1.2 --h-far 3 \
  --dz-max 0.8 --margin 3 --air 3 --simplify 0.05 --thin 0.02 "$@" > $OUT/$LABEL.log 2>&1 || { echo "{\"label\": \"$LABEL\", \"mesh_failed\": true}"; exit 0; }
rm -rf $OUT/$LABEL-solve
python3 $D/scripts/run_elmer.py --elmer $ELMER $M $OUT/$LABEL-solve --pec 2 3 --port 10 --k -2500 0 0 \
  --hypre-ams --hypre-method 7 --ams-singular --tol 1e-10 --maxit 400 --np 8 --label $LABEL
