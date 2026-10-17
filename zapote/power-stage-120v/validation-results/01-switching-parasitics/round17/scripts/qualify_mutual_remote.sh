#!/bin/bash
# Round 17: qualify inductance_matrix.py (mutuals from single-port B fields)
# on non-uniform fields after the DG-averaging defect:
#  Q1 floating-block plate fixture (non-uniform): L from B == solver energy.
#  Q2 two-port plate section: exact L11/L22/M.
#  Q3 real board geometry (coarse leg-A mesh, P1 & P2): M12 from B fields
#     vs M12 = (L_both - L11 - L22)/2 from a pair solve's energy.
set -u
R=${R:?}; OUT=${OUT:?}; ELMER=${ELMER:?}
D=$(dirname "$0")
S="python3 $D/run_elmer.py --elmer $ELMER"
F="--hypre-ams --hypre-method 8 --ams-singular"
mkdir -p $OUT; cd $OUT
ONLY=${QUAL_ONLY:-all}
if [ "$ONLY" = all ]; then
echo "Q1"; rm -rf q1 q1.out
$S $R/f2.msh q1 --pec 2 --port 4 --k 0 0 100 $F --tol 1e-10 --maxit 5000 --np 2 --vtu --label q1 > q1.out
python3 $D/inductance_matrix.py $R/f2.msh --port 4 q1; echo "Q1 rc=$?"
echo "Q2"; for p in 4 5; do rm -rf q2p$p q2p$p.out
  $S $R/sect2.msh q2p$p --pec 2 --port $p --k 0 0 100 $F --tol 1e-10 --maxit 5000 --np 4 --vtu --label q2p$p > q2p$p.out; done
python3 $D/inductance_matrix.py $R/sect2.msh --port 4 q2p4 --port 5 q2p5; echo "Q2 rc=$?"
fi
echo "Q3"; M=$R/legA-small-thin.msh
rm -rf q3p1 q3p2 q3both q3p1.out q3p2.out q3both.out
$S $M q3p1 --pec 2 3 --port 10 --k -2500 0 0 $F --tol 1e-9 --maxit 30000 --np 12 --vtu --label q3p1 > q3p1.out
$S $M q3p2 --pec 2 3 --port 11 --k -2500 0 0 $F --tol 1e-9 --maxit 30000 --np 12 --vtu --label q3p2 > q3p2.out
$S $M q3both --pec 2 3 --port 10 --k -2500 0 0 --port2 11 --k2 -2500 0 0 $F --tol 1e-9 --maxit 30000 --np 12 --label q3both > q3both.out
python3 $D/inductance_matrix.py $R/legA-small-thin.msh --port 10 q3p1 --port 11 q3p2; echo "Q3 matrix rc=$?"
python3 - <<'PY'
import json
L = lambda f: json.loads([l for l in open(f) if l.startswith("{")][-1])["inductance_nH"]
l1, l2, lb = L("q3p1.out"), L("q3p2.out"), L("q3both.out")
print("Q3 pair-energy M12 =", (lb - l1 - l2) / 2, "nH  (L11", l1, "L22", l2, "Lboth", lb, ")")
PY
echo QUALIFY_DONE
