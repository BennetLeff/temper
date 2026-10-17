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
FAILED=0
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
  rc=$?
  echo "solve rc=$rc"
  # Fail closed (D-9 review, P2): a failed or unconverged pair solve, a pair
  # run whose excitation differs from the mesh's port record, or a mutual that
  # misses by more than an absolute tolerance is a FAIL, not an agreement.
  python3 - "$TAG" "$i" "$j" "$rd" "$rc" <<'PY' || FAILED=1
import hashlib, json, re, sys
from pathlib import Path
tag, i, j, rd, rc = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
ABS_TOL_NH, REL_TOL = 1e-3, 1e-3
res = json.loads((Path(rd) / "result.json").read_text()) if (Path(rd) / "result.json").exists() else {}
mesh_sha = hashlib.sha256(Path(f"{tag}.msh").read_bytes()).hexdigest()
ports = {p["physical"]: [c * p["k_A_per_m"] for c in p["direction"]]
         for p in json.loads([l for l in open(f"{tag}.log") if l.startswith("RESULT ")][-1][7:])["ports"]}
sif = (Path(rd) / "case.sif").read_text() if (Path(rd) / "case.sif").exists() else ""
driven = {int(b[0]): [float(x) for x in b[1:]] for b in re.findall(
    r"Target Boundaries\(1\) = (\d+)\n  Magnetic Field Strength 1 = Real (\S+)\n"
    r"  Magnetic Field Strength 2 = Real (\S+)\n  Magnetic Field Strength 3 = Real (\S+)", sif)}
d = json.loads([l for l in open(f"{tag}.matrix.txt") if l.startswith("RESULT ")][-1][7:])
ids = [int(p) for p in d["ports"]]
reasons = []
if rc != 0 or not res.get("converged"):
    reasons.append(f"pair solve rc={rc} converged={res.get('converged')}")
if res.get("mesh_sha256") not in (None, mesh_sha):
    reasons.append("pair solve used a different mesh")
if res.get("mesh_sha256") is None:
    reasons.append("pair solve has no receipt")
if d.get("mesh_sha256") not in (None, mesh_sha):
    reasons.append("matrix was built on a different mesh")
if set(driven) != {i, j} or any(max(abs(a - b) for a, b in zip(driven[p], ports[p])) > 1e-6 for p in (i, j) if p in driven):
    reasons.append(f"pair excitation {driven} does not match mesh ports {i}, {j}")
for p in d.get("port_identity", []):
    if p["physical"] in (i, j) and max(abs(a - b) for a, b in zip(p["k_A_per_m"], ports[p["physical"]])) > 1e-6:
        reasons.append(f"matrix port {p['physical']} K differs from the mesh")
lb = res.get("inductance_nH")
L = d["L_nH"]
lii, ljj, Mx = L[ids.index(i)][ids.index(i)], L[ids.index(j)][ids.index(j)], L[ids.index(i)][ids.index(j)]
Me = (lb - lii - ljj) / 2 if lb is not None else None
err = abs(Me - Mx) if Me is not None else None
if err is None or err > ABS_TOL_NH or err > REL_TOL * max(abs(Mx), 1e-3):
    reasons.append(f"mutual error {err} nH exceeds {ABS_TOL_NH} nH or {REL_TOL:g} relative to |M|")
if Me is not None and (Me > 0) != (Mx > 0):
    reasons.append("sign differs")
out = {"tag": tag, "pair": [i, j], "L_both_nH": lb, "L_ii_nH": lii, "L_jj_nH": ljj,
       "M_energy_nH": None if Me is None else round(Me, 6), "M_matrix_nH": Mx, "abs_diff_nH": err,
       "rel_to_M": None if err is None else err / max(abs(Mx), 1e-3), "verdict": "FAIL" if reasons else "PASS",
       "reasons": reasons, "pair_result_sha256": hashlib.sha256((Path(rd) / "result.json").read_bytes()).hexdigest()
       if (Path(rd) / "result.json").exists() else None, "mesh_sha256": mesh_sha}
print("PAIR " + json.dumps(out))
sys.exit(1 if reasons else 0)
PY
done
echo PAIR_DONE
exit $FAILED
