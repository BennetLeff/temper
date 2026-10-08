#!/usr/bin/env python3
"""Round 18, hypothesis 7 (campaign structure): which fine cases does the recipe need?

Re-does round 17's fine_h1_recipe_check.py without the ngspice import chain
(that script imports d2/run_d2.py only for its matrix reader), and adds the
mesh-offset transfer check between legs.

1. Full recipe (leg A best):  fine quad(1,2,3) + [coarse cubic(0.5,1,2,3) - coarse quad(1,2,3)]
   h1-only recipe:            coarse cubic(0.5,1,2,3) + [fine h1 - coarse h1]
   (crop correction identical in both, omitted). Difference per entry.
2. Relative mesh offset (fine h1 - coarse h1) / coarse h1 per entry, leg A
   (native-17) vs leg B (native-19): would a transferred offset replace a
   fine run? Reported, not used: the transfer error is compared with FINDINGS M1.

    python3 recipe_check.py      (run from this folder or anywhere)
"""
import json
from pathlib import Path

import numpy as np

R17 = Path(__file__).resolve().parents[2] / "round17"
M, D = R17 / "results" / "matrices", R17 / "d2"


def L(p: Path) -> np.ndarray:
    for line in open(p):
        if line.startswith("RESULT "):
            d = json.loads(line[7:])
            return np.array(d.get("L0_nH") or d["L_nH"], dtype=float)
    raise SystemExit(f"no RESULT in {p}")


def fit0(hs, Ls, deg):
    s = np.stack(Ls)
    n = s.shape[1]
    return np.array([[np.polyval(np.polyfit(hs, s[:, i, j], deg), 0) for j in range(n)] for i in range(n)])


np.set_printoptions(precision=4, suppress=True)
c = {h: L(M / f"legA-h{h}-e1p0-m10.matrix.txt") for h in ("0p5", "1", "2", "3")}
f = {h: L(D / f"legA-h{h}-e0p35.matrix.txt") for h in ("1", "2", "3")}
cub = fit0([.5, 1, 2, 3], [c["0p5"], c["1"], c["2"], c["3"]], 3)
full = fit0([1, 2, 3], [f["1"], f["2"], f["3"]], 2) + cub - fit0([1, 2, 3], [c["1"], c["2"], c["3"]], 2)
h1 = cub + f["1"] - c["1"]
d = h1 - full
print("1. leg A: h1-only recipe minus full recipe (nH)")
print(d)
print(f"   max |d| = {abs(d).max():.4f} nH, max rel = {(abs(d) / abs(full)).max() * 100:.2f} %, "
      f"max |d| / sqrt(Lii Ljj) = {(abs(d) / np.sqrt(np.outer(np.diag(full), np.diag(full)))).max() * 100:.3f} %")

offA = (f["1"] - c["1"])
cB, fB = L(M / "legB-h1-e1p0-m10-n19.matrix.txt"), L(D / "legB-h1-e0p35-n19.matrix.txt")
offB = fB - cB
norm = lambda X, ref: X / np.sqrt(np.outer(np.diag(ref), np.diag(ref)))
print("2. mesh offset fine h1 - coarse h1, normalised by sqrt(Lii Ljj) of coarse (%)")
print("   leg A (native-17):\n", 100 * norm(offA, c["1"]))
print("   leg B (native-19):\n", 100 * norm(offB, cB))
tr = norm(offA, c["1"]) - norm(offB, cB)
print(f"   transfer error A->B, max |.| = {100 * abs(tr).max():.2f} % of sqrt(Lii Ljj)")
