#!/bin/bash
# Round 17 on the Mac (in parallel with the remote campaign): qualify the Mac
# Elmer+Hypre build on the exact two-port fixture, then solve P1 alone at
# h = 1 mm, 1.0 mm edges, on four meshes differing in one setting each:
# base (margin 10, air 10, simplify 0.05), air20, margin15, simp0p1.
set -u
D=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:?}; ELMER=${ELMER:?}; MESH=${MESH:?}; FIX=${FIX:?}
S="python3 $D/run_elmer.py --elmer $ELMER"
F="--hypre-ams --hypre-method 8 --ams-singular"
mkdir -p "$OUT"; cd "$OUT"
for p in 4 5; do
  $S $FIX q2p$p --pec 2 --port $p --k 0 0 100 $F --tol 1e-10 --maxit 5000 --np 4 --vtu --label mac-q2p$p > q2p$p.out
done
python3 $D/inductance_matrix.py $FIX --port 4 q2p4 --port 5 q2p5 | tee q2.matrix.txt
grep -q '"L_nH": \[\[3.141593, 1.884956\], \[1.884956, 1.884956\]\]' q2.matrix.txt || { echo "FAIL mac qualification"; exit 1; }
echo "QUALIFIED mac"
for v in base air20 margin15 simp0p1; do
  echo "START $v"
  $S $MESH/$v.msh $v-P1 --pec 2 3 --port 10 --k -2500 0 0 $F --tol 1e-8 --maxit 40000 --np 10 --label sens-$v > $v-P1.out
  echo "DONE $v $(tail -1 $v-P1.out)"
done
echo SENS_DONE
