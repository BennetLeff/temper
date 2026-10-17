#!/usr/bin/env python3
"""s51 decision matrices for F6 (OPEN-ITEMS S3), by round 17's own recipe on the s51 coarse reference.

Round 17 (round17/d2): decision matrix = native-21 coarse (h 1 mm, 1.0 mm edges, 10 mm crop)
  + [native-19 best - native-19 coarse]  (compose_leg{A,B}21_prov.py, rounded to 1e-4 nH)
  + 2 nH on both gate-port diagonals    (compose_stage9_bound.py: the 0.3 mm driver-output necks, still on s51).
Here the native-21 coarse matrix is swapped for the s51 one. Two variants:
  P (primary): exactly the committed recipe on the s51 coarse matrix:  leg{A,B}21-h0-s9b2-s51.matrix.txt
  D (control-differenced): committed s9b2 + (s51 coarse - n21 coarse re-run in this chain), so any recipe offset
    (solver scaling off, 10 ranks, mesher version, gmsh run-to-run) cancels:  leg{A,B}21-h0-s9b2d-s51.matrix.txt
Control: the recipe applied to the committed n21 coarse matrix must reproduce the committed s9b2 matrix.

    python3 -I compose_s51.py PS_ROOT MATRIX_DIR OUT_DIR
MATRIX_DIR holds legA21-h1-e1p0-s51.matrix.txt, legB21-h1-e1p0-s51.matrix.txt and (optional, for D)
legA21-h1-e1p0-n21.matrix.txt, legB21-h1-e1p0-n21.matrix.txt from chain_s3.sh.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ps, mdir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
R17 = ps / "validation-results/01-switching-parasitics/round17"
D2, M = R17 / "d2", R17 / "results/matrices"
out.mkdir(parents=True, exist_ok=True)
NAMES = {"A": ["P1_C38", "P2_C39", "P3_gate_high", "P4_gate_low"], "B": ["P1_C40", "P2_C41", "P3_gate_high", "P4_gate_low"]}


def res(p):
    t = Path(p).read_text()
    return json.loads(t[t.index("{"):])


def L(p):
    r = res(p)
    if "port_identity" in r:
        assert [x["name"][:2] for x in r["port_identity"]] == ["P1", "P2", "P3", "P4"], p
    return np.array(r.get("L_nH", r.get("L0_nH")), dtype=float)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def recipe(coarse, leg):
    corr = L(D2 / f"leg{leg}-h0-best-n19.matrix.txt") - L(M / f"leg{leg}-h1-e1p0-m10-n19.matrix.txt")
    prov = coarse + corr
    prov = np.round((prov + prov.T) / 2, 4)
    s9 = prov.copy()
    s9[2, 2] += 2.0
    s9[3, 3] += 2.0
    return np.round(s9, 4)


def par(Lm):
    l11, l22, m12 = Lm[0, 0], Lm[1, 1], Lm[0, 1]
    return (l11 * l22 - m12 ** 2) / (l11 + l22 - 2 * m12)


def write(name, Lm, status, sources):
    eig = float(np.linalg.eigvalsh(Lm).min())
    assert eig > 0, (name, eig)
    leg = name[3]
    d = {"names": NAMES[leg], "L0_nH": Lm.round(4).tolist(), "min_eigenvalue_nH": eig, "status": status,
         "parallel_loop_nH": round(float(par(Lm)), 3),
         "sources": {k: {"path": str(v), "sha256": sha(v)} for k, v in sources.items()}}
    (out / name).write_text("RESULT " + json.dumps(d) + "\n")
    return d


summary = {"control": {}, "matrices": {}}
for leg in "AB":
    committed_coarse = M / f"leg{leg}21-h1-e1p0-m10-n21.matrix.txt"
    committed_s9 = D2 / f"leg{leg}21-h0-s9b2-n21.matrix.txt"
    ctrl = recipe(L(committed_coarse), leg)
    dmax = float(np.abs(ctrl - L(committed_s9)).max())
    assert dmax < 2e-4, (leg, dmax)
    summary["control"][leg] = {"recipe_on_committed_n21_vs_committed_s9b2_max_abs_nH": dmax}
    s51 = mdir / f"leg{leg}21-h1-e1p0-s51.matrix.txt"
    srcs = {"s51_coarse": s51, "n19_best": D2 / f"leg{leg}-h0-best-n19.matrix.txt",
            "n19_coarse": M / f"leg{leg}-h1-e1p0-m10-n19.matrix.txt"}
    P = write(f"leg{leg}21-h0-s9b2-s51.matrix.txt", recipe(L(s51), leg),
              "S3: round-17 recipe (n19 best - coarse correction + 2 nH gate bound) on the s51 coarse reference", srcs)
    row = {"P": {"parallel_loop_nH": P["parallel_loop_nH"], "L0_nH": P["L0_nH"]},
           "committed_s9b2_parallel_nH": round(float(par(L(committed_s9))), 3),
           "coarse_s51_parallel_nH": round(float(par(L(s51))), 3),
           "coarse_n21_committed_parallel_nH": round(float(par(L(committed_coarse))), 3),
           "coarse_delta_s51_minus_n21_committed_nH": np.round(L(s51) - L(committed_coarse), 4).tolist()}
    n21r = mdir / f"leg{leg}21-h1-e1p0-n21.matrix.txt"
    if n21r.is_file():
        dl = L(s51) - L(n21r)
        Dm = np.round(L(committed_s9) + (dl + dl.T) / 2, 4)
        Dd = write(f"leg{leg}21-h0-s9b2d-s51.matrix.txt", Dm,
                   "S3: committed s9b2 + (s51 coarse - n21 coarse re-run, same chain)",
                   {"committed_s9b2": committed_s9, "s51_coarse": s51, "n21_coarse_rerun": n21r})
        row["D"] = {"parallel_loop_nH": Dd["parallel_loop_nH"], "L0_nH": Dd["L0_nH"]}
        row["coarse_n21_rerun_parallel_nH"] = round(float(par(L(n21r))), 3)
        row["control_rerun_minus_committed_n21_coarse_nH"] = np.round(L(n21r) - L(committed_coarse), 4).tolist()
        row["coarse_delta_s51_minus_n21_rerun_nH"] = np.round(dl, 4).tolist()
    summary["matrices"][leg] = row
(out / "compose-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
print(json.dumps(summary, indent=1))
