#!/usr/bin/env python3
"""Native-21 s51 matrices (OPEN-ITEMS S3): leg{A,B}21-h0-best + (coarse s51 - coarse n21 control).

Both coarse matrices come from the remote s3-s51 v2 campaign (h 1 mm, 1.0 mm edges, 10 mm crop, scaling off,
gmsh HXT outer air), so the meshing recipe cancels. s52 has no copper edit vs s51; s53's edit lies outside the
leg crops (README, s51 section).

    python3 compose_s51.py          -> leg{A,B}21-h0-best-s51.matrix.txt
    python3 compose_s51.py --check  -> exit 1 if the committed files differ by > 1e-5 nH
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

import run_d2

HERE = Path(__file__).resolve().parent
M = HERE.parent.parent / "round18-speedup" / "matrices"


def compose(g):
    base = np.array(run_d2.read_L(str(HERE / f"leg{g}21-h0-best.matrix.txt")))
    s = np.array(run_d2.read_L(str(M / f"leg{g}21-h1-e1p0-m10-s51v2.matrix.txt")))
    c = np.array(run_d2.read_L(str(M / f"leg{g}21-h1-e1p0-m10-n21v2.matrix.txt")))
    return base + (s - c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = 0
    for g in "AB":
        L = compose(g)
        out = HERE / f"leg{g}21-h0-best-s51.matrix.txt"
        if a.check:
            d = np.abs(np.array(run_d2.read_L(str(out))) - L).max()
            print(g, "max |d| nH", d)
            bad |= d > 1e-5
            continue
        rec = {"names": ["P1", "P2", "P3_gate_high", "P4_gate_low"], "L0_nH": L.round(6).tolist(),
               "min_eigenvalue_nH": float(np.linalg.eigvalsh(L).min()),
               "recipe": f"leg{g}21-h0-best (n21 76ec8cca) + [coarse s51 - coarse n21], both h1 e1.0 crop 10 mm, "
                         f"gmsh HXT outer air, scaling off (remote s3-s51 v2; round18-speedup/matrices/"
                         f"leg{g}21-h1-e1p0-m10-{{s51v2,n21v2}}). s52 has no copper edit vs s51."}
        out.write_text("RESULT " + json.dumps(rec) + "\n")
        print(out.name, "min eig", round(rec["min_eigenvalue_nH"], 3))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
