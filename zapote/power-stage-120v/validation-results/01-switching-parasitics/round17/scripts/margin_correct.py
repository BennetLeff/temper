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


def read(path: str) -> tuple[np.ndarray, dict]:
    d = json.loads([line for line in open(path) if line.startswith("RESULT ")][-1][7:])
    return np.array(d.get("L0_nH") or d["L_nH"], dtype=float), d


def names(d: dict) -> list[str] | None:
    return [p["name"] for p in d.get("port_identity", [])] or d.get("names")


def main() -> None:
    ap = argparse.ArgumentParser()
    for k in ("m10", "m20", "target", "out"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    l10, d10 = read(a.m10)
    l20, d20 = read(a.m20)
    lt, dt = read(a.target)
    # Port order: recorded names must agree; a file without names (pre-identity
    # matrices) must have ascending physical ids (10..13 = P1..P4).
    order = [names(d) for d in (d10, d20, dt)]
    known = [o for o in order if o]
    if not known or any(o != known[0] for o in known):
        raise SystemExit(f"port orders differ or are missing: {order}")
    for d, o in zip((d10, d20, dt), order):
        ids = [int(x) for x in d.get("ports", []) if str(x).isdigit()]
        if not o and (not ids or ids != sorted(ids)):
            raise SystemExit(f"unnamed matrix without ascending port ids: {d.get('ports')}")
    dL = l20 - l10
    out = lt + dL
    eig = np.linalg.eigvalsh((out + out.T) / 2)
    res = {"names": known[0], "L0_nH": out.round(4).tolist(), "margin_correction_nH": dL.round(4).tolist(),
           "margin_correction_rel": (dL / np.abs(l10)).round(5).tolist(), "min_eigenvalue_nH": float(eig.min()),
           "sources": {"m10": a.m10, "m20": a.m20, "target": a.target},
           "note": "additive per-entry crop correction from the coarse h=1 mesh; transfer to the target is assumed"}
    open(a.out, "w").write("RESULT " + json.dumps(res) + "\n")
    print("RESULT " + json.dumps(res))
    if eig.min() <= 0:
        raise SystemExit(f"corrected matrix not positive definite (min eig {eig.min():.4g} nH)")


if __name__ == "__main__":
    main()
