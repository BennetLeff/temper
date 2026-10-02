#!/bin/bash
# Round 17, D-4 follow-up: check signed mutuals independently of the B-field
# reciprocity formula. For a pair (i, j) driven together at 1 A each,
#   M_ij = (L_both - L_ii - L_jj) / 2
# from solver energies alone. Compared with the matrix entry from
# inductance_matrix.py. M12 was checked this way in section 5 (Q3); this does
# power-to-gate (P1+P3) and gate-to-gate (P3+P4), the latter being small and
# negative (-0.296 nH at h1, e1.0), so its sign is the thing under test.
#   DIR=<campaign dir> TAG=legA-h1-e1p0 ELMER=<prefix> NP=10 pair_check.sh 10:12 12:13
set -u
DIR=${DIR:?}; TAG=${TAG:?}; ELMER=${ELMER:?}; NP=${NP:-10}
D=$(cd "$(dirname "$0")" && pwd)
cd "$DIR"
M=$TAG.msh
for pair in "$@"; do
  i=${pair%:*}; j=${pair#*:}
  read -r ki kj < <(python3 - "$TAG.log" "$i" "$j" <<'PY'
import json, sys
p = {q["physical"]: q for q in json.loads([l for l in open(sys.argv[1]) if l.startswith("RESULT ")][-1][7:])["ports"]}
k = lambda n: ",".join(str(c * p[n]["k_A_per_m"]) for c in p[n]["direction"])
print(k(int(sys.argv[2])), k(int(sys.argv[3])))
PY
)
  rd=$TAG-pair$i-$j
  rm -rf "${rd:?}" "$rd.out"
  echo "START pair $i+$j  K $ki / $kj"
  python3 "$D/run_elmer.py" --elmer "$ELMER" "$M" "$rd" --pec 2 3 --port "$i" --k ${ki//,/ } \
    --port2 "$j" --k2 ${kj//,/ } --hypre-ams --hypre-method 8 --ams-singular --tol 1e-8 --maxit 40000 \
    --np "$NP" --label "$rd" > "$rd.out"
  echo "solve rc=$?"
  python3 - "$TAG" "$i" "$j" "$rd.out" <<'PY'
import json, sys
tag, i, j, both = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
L = lambda f: json.loads([l for l in open(f) if l.startswith("{")][-1])["inductance_nH"]
d = json.loads([l for l in open(f"{tag}.matrix.txt") if l.startswith("RESULT ")][-1][7:])
ids = [int(p) for p in d["ports"]]
Mx = d["L_nH"][ids.index(i)][ids.index(j)]
lii, ljj = d["L_nH"][ids.index(i)][ids.index(i)], d["L_nH"][ids.index(j)][ids.index(j)]
lb = L(both)
Me = (lb - lii - ljj) / 2
print("PAIR " + json.dumps({"tag": tag, "pair": [i, j], "L_both_nH": lb, "L_ii_nH": lii, "L_jj_nH": ljj,
                            "M_energy_nH": round(Me, 6), "M_matrix_nH": Mx, "abs_diff_nH": abs(Me - Mx),
                            "rel_to_L_both": abs(Me - Mx) / lb, "same_sign": (Me > 0) == (Mx > 0)}))
PY
done
echo PAIR_DONE
