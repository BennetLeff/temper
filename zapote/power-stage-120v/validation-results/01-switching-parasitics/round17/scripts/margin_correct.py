#!/usr/bin/env python3
"""Apply the per-entry crop-margin correction to a port matrix (round 17).

The campaign crops the board 10 mm around the leg; planes truncated at the
crop edge lose return paths, so L is high (README section 10). The margin
effect converged by 20 mm, so the correction is, entry by entry,

    dL_ij = L_ij(margin 20) - L_ij(margin 10)

measured on the coarse mesh (h = 1 mm, 1.0 mm edges) and added to the target
matrix (fine mesh, extrapolated to h = 0). That transfer is an ASSUMPTION
(D-4 review, P2): it is only tested if a second (mesh, height) pair gives the
same dL. The output must stay symmetric positive definite.

    margin_correct.py --m10 A.matrix.txt --m20 B.matrix.txt --target C.matrix.txt --out D.matrix.txt
"""
from __future__ import annotations

import argparse
import json

import numpy as np

import matrix_gate


def main() -> None:
    ap = argparse.ArgumentParser()
    for k in ("m10", "m20", "target", "out"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    (l10, d10), (l20, d20), (lt, dt) = (matrix_gate.read(f) for f in (a.m10, a.m20, a.target))
    ports = matrix_gate.common_identity({a.m10: d10, a.m20: d20, a.target: dt})
    for L, f in ((l10, a.m10), (l20, a.m20), (lt, a.target)):
        matrix_gate.check(L, f)
    if not (l10.shape == l20.shape == lt.shape):
        raise SystemExit(f"shapes differ: {l10.shape} {l20.shape} {lt.shape}")
    dL = l20 - l10
    out = lt + dL
    eig = matrix_gate.check(out, "corrected matrix")           # gates before anything is written
    res = {"names": [p["name"] for p in ports], "port_identity": ports, "L0_nH": out.round(4).tolist(),
           "margin_correction_nH": dL.round(4).tolist(),
           "margin_correction_rel": (dL / np.abs(l10)).round(5).tolist(), "min_eigenvalue_nH": eig,
           "sources": {"m10": a.m10, "m20": a.m20, "target": a.target},
           "note": "additive per-entry crop correction from the coarse h=1 mesh; transfer to the target is assumed"}
    open(a.out, "w").write("RESULT " + json.dumps(res) + "\n")
    print("RESULT " + json.dumps(res))


if __name__ == "__main__":
    main()
