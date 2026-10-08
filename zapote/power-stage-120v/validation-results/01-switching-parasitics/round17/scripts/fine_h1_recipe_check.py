#!/usr/bin/env python3
"""Is a fine-mesh extraction at h = 1 mm alone enough? (round 17, leg A evidence)

Full recipe (leg A best):  fine quad(1,2,3) + [coarse cubic(0.5,1,2,3) - coarse quad(1,2,3)]
h1-only recipe:            coarse cubic(0.5,1,2,3) + [fine h1 - coarse h1]
(crop correction identical in both, so omitted). The two agree if the
fine-minus-coarse mesh offset does not depend on closure height, which the
round-17 README already indicated (coarse and fine 1->2->3 mm slopes agree
to ~1 %). Result on leg A: max |difference| 0.026 nH (0.23 %), far below the
accepted self-inductance mesh uncertainty (+4..6 %, FINDINGS M1). Hence
fine extractions at h = 2 and 3 mm are not needed for leg B or re-layouts.

    python3 fine_h1_recipe_check.py
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "d2"))
import run_d2  # noqa: E402

M, D = HERE.parent / "results" / "matrices", HERE.parent / "d2"


def L(p):
    return np.array(run_d2.read_L(str(p)))


def fit0(hs, Ls, deg):
    s = np.stack(Ls)
    return np.array([[np.polyval(np.polyfit(hs, s[:, i, j], deg), 0) for j in range(4)] for i in range(4)])


c = {h: L(M / f"legA-h{h}-e1p0-m10.matrix.txt") for h in ("0p5", "1", "2", "3")}
f = {h: L(D / f"legA-h{h}-e0p35.matrix.txt") for h in ("1", "2", "3")}
cub = fit0([.5, 1, 2, 3], [c["0p5"], c["1"], c["2"], c["3"]], 3)
full = fit0([1, 2, 3], [f["1"], f["2"], f["3"]], 2) + cub - fit0([1, 2, 3], [c["1"], c["2"], c["3"]], 2)
h1 = cub + f["1"] - c["1"]
d = h1 - full
print(np.round(d, 4))
print(f"max |d| = {abs(d).max():.4f} nH, max rel = {(abs(d) / abs(full)).max() * 100:.2f} %")
assert abs(d).max() < 0.05
