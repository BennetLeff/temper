#!/usr/bin/env python3
"""Best (h = 0) port matrix from a coarse closure set + ONE fine run (round 17).

    best = cubic_coarse(0.5,1,2,3)(h=0) + [fine(h1) - coarse(h1)] + [coarse(h1,m20) - coarse(h1,m10)]

The h1-only fine recipe is validated against leg A's full three-height recipe in
`../scripts/fine_h1_recipe_check.py` (max 0.026 nH). --selftest rebuilds leg A
(native-17 data) and compares with the committed legA-h0-best.matrix.txt.

    compose_leg_best.py --leg B   ->  legB-h0-best-n19.matrix.txt
    compose_leg_best.py --selftest
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import run_d2

HERE = Path(__file__).resolve().parent
M = HERE.parent / "results" / "matrices"
SETS = {
    "A": {"c0.5": M / "legA-h0p5-e1p0-m10.matrix.txt", "c1": M / "legA-h1-e1p0-m10.matrix.txt",
          "c2": M / "legA-h2-e1p0-m10.matrix.txt", "c3": M / "legA-h3-e1p0-m10.matrix.txt",
          "m20": M / "legA-h1-e1p0-m20.matrix.txt", "f1": HERE / "legA-h1-e0p35.matrix.txt"},
    "B": {"c0.5": M / "legB-h0p5-e1p0-m10-n19.matrix.txt", "c1": M / "legB-h1-e1p0-m10-n19.matrix.txt",
          "c2": M / "legB-h2-e1p0-m10-n19.matrix.txt", "c3": M / "legB-h3-e1p0-m10-n19.matrix.txt",
          "m20": M / "legB-h1-e1p0-m20-n19.matrix.txt", "f1": HERE / "legB-h1-e0p35-n19.matrix.txt"},
}
NAMES = {"A": ["P1_C38", "P2_C39", "P3_gate_high", "P4_gate_low"], "B": ["P1_C40", "P2_C41", "P3_gate_high", "P4_gate_low"]}


def L(p):
    return np.array(run_d2.read_L(str(p)))


def best(leg):
    s = {k: L(p) for k, p in SETS[leg].items()}
    hs = np.array([0.5, 1, 2, 3])
    stack = np.stack([s["c0.5"], s["c1"], s["c2"], s["c3"]])
    cubic0 = np.array([[np.polyval(np.polyfit(hs, stack[:, i, j], 3), 0) for j in range(4)] for i in range(4)])
    out = cubic0 + (s["f1"] - s["c1"]) + (s["m20"] - s["c1"])
    return (out + out.T) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg", choices=["A", "B"])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        d = best("A") - L(HERE / "legA-h0-best.matrix.txt")
        print(np.round(d, 4)); print("max |d| nH", abs(d).max())
        assert abs(d).max() < 0.05
        return
    out = best(a.leg)
    eig = float(np.linalg.eigvalsh(out).min())
    assert eig > 0
    res = {"names": NAMES[a.leg], "L0_nH": np.round(out, 4).tolist(), "min_eigenvalue_nH": eig,
           "recipe": "cubic_coarse(0.5,1,2,3) + (fine_h1 - coarse_h1) + (coarse_m20 - coarse_m10)",
           "sources": {k: {"path": str(p.relative_to(HERE.parent)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                       for k, p in SETS[a.leg].items()}}
    name = f"leg{a.leg}-h0-best-n19.matrix.txt" if a.leg == "B" else "legA-h0-best-recomposed.matrix.txt"
    (HERE / name).write_text("RESULT " + json.dumps(res) + "\n")
    print(np.round(out, 3), "min eig", round(eig, 3))


if __name__ == "__main__":
    main()
