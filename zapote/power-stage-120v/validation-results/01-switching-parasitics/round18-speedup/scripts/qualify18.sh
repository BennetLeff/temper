#!/bin/bash
# Round 18: re-run round 17's mutual-inductance qualification (qualify_mutual_remote.sh,
# Q1-Q3) with a candidate solver configuration, inside the experiment budget (2 ranks).
#
#   TAG=noscale EXTRA="Linear System Scaling = False" [ELMER=...] [TOL=1e-8] qualify18.sh
#
#  Q1 floating-block plate fixture (f2.msh): L from B == solver energy (2.762936 nH, direct).
#  Q2 two-port plate section (sect2.msh): exact L11 3.141593, L22 1.884956, M 1.884956 nH.
#  Q3 board, legA-small-thin (850,640 tets, native-17 leg A, P1 & P2): L11 vs the direct solve
#     29.77092 nH, M12 by reciprocity vs round 17 (18.106446 from B, 18.106450 pair energy)
#     and vs this configuration's own pair solve.
# Runs go to runs/qual-$TAG-*; VTU is kept only until inductance_matrix.py has read it.
# Waits until none of our other variants run (one at a time).
set -u
S=$HOME/temper-fem/speedup
cd "$S" || exit 1
source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem
TAG=${TAG:?} EXTRA=${EXTRA:?}
TOL=${TOL:-1e-8}
export ELMER=${ELMER:-$HOME/temper-fem/elmer-install}
Q=$HOME/temper-fem/r17/qual/meshes
while pgrep -f "scripts/variant|scripts/battery" > /dev/null; do sleep 30; done   # no queued batteries either
v() { KEEP=1 PEC="${PEC:-2 3}" scripts/variant2.sh "qual-$TAG-$1" "$2" $3 $4 $5 $6 --hypre-method 8 --tol "$TOL" \
        --maxit 30000 --solver-line "$EXTRA" "${@:7}" < /dev/null; }
mat() { python3 r17scripts/inductance_matrix.py "$@"; }
clean() { find runs -path "runs/qual-$TAG-*" -type f \( -name "case.result*" -o -name "*.vtu" -o -name "*.pvtu" \) -delete; }
echo "== Q1"; PEC=2 v q1 $Q/f2.msh 4 0 0 100 --tol 1e-10
mat $Q/f2.msh --port 4 runs/qual-$TAG-q1; echo "Q1 rc=$?"
echo "== Q2"; PEC=2 v q2p4 $Q/sect2.msh 4 0 0 100 --tol 1e-10; PEC=2 v q2p5 $Q/sect2.msh 5 0 0 100 --tol 1e-10
mat $Q/sect2.msh --port 4 runs/qual-$TAG-q2p4 --port 5 runs/qual-$TAG-q2p5; echo "Q2 rc=$?"
clean
echo "== Q3"; M=$Q/legA-small-thin.msh
v q3p1 $M 10 -2500 0 0; v q3p2 $M 11 -2500 0 0
mat $M --port 10 runs/qual-$TAG-q3p1 --port 11 runs/qual-$TAG-q3p2; echo "Q3 matrix rc=$?"
clean
KEEP=0 scripts/variant2.sh "qual-$TAG-q3both" $M 10 -2500 0 0 --hypre-method 8 --tol "$TOL" --maxit 30000 \
  --solver-line "$EXTRA" --port2 11 --k2 -2500 0 0 < /dev/null
python3 - "$TAG" <<'PY'
import json, sys
t = sys.argv[1]
L = lambda r: json.loads([l for l in open(f"runs/qual-{t}-{r}.out") if l.startswith("{")][-1])
a, b, c = L("q3p1"), L("q3p2"), L("q3both")
print(f"Q3 L11 {a['inductance_nH']} (direct 29.77092) its {a['last_iteration']}; L22 {b['inductance_nH']} its {b['last_iteration']}; "
      f"Lboth {c['inductance_nH']} its {c['last_iteration']}")
print("Q3 pair-energy M12 =", (c["inductance_nH"] - a["inductance_nH"] - b["inductance_nH"]) / 2,
      "nH (round 17: 18.106446 from B fields, 18.106450 pair energy)")
PY
echo QUALIFY_DONE
