#!/usr/bin/env python3
"""Transfer a closure-height extrapolation change to a target matrix (round 17).

On the coarse mesh (1.0 mm edges, h = 0.5 / 1 / 2 mm), compare the zero-height
estimate of a parabola through 0.5, 1, 2 mm with the straight line through
1 and 2 mm (what the fine campaign uses), entry by entry:

    dL = quad(0.5, 1, 2) - lin(1, 2)

and add dL to a target matrix that was extrapolated with lin(1, 2). Like the
crop correction, the transfer from the coarse to the fine mesh is an
ASSUMPTION; on the coarse mesh the 0.5 mm closure strips (0.6 mm wide) are
narrower than the 1.0 mm edges, so part of the curvature may be mesh error.
The output must stay symmetric positive definite.

    extrap_delta.py --h05 A --h1 B --h2 C --target T --out OUT
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
    for k in ("h05", "h1", "h2", "target", "out"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    mats = {k: read(getattr(a, k)) for k in ("h05", "h1", "h2", "target")}
    known = [n for n in (names(d) for _, d in mats.values()) if n]
    if not known or any(n != known[0] for n in known):
        raise SystemExit(f"port orders differ or are missing: {[names(d) for _, d in mats.values()]}")
    H = np.array([0.5, 1.0, 2.0])
    Y = np.stack([mats[k][0] for k in ("h05", "h1", "h2")])
    n = Y.shape[1]
    quad = np.linalg.solve(np.stack([np.ones(3), H, H ** 2], 1), Y.reshape(3, -1))[0].reshape(n, n)
    lin12 = 2 * Y[1] - Y[2]
    dL = quad - lin12
    out = mats["target"][0] + dL
    eig = np.linalg.eigvalsh((out + out.T) / 2)
    res = {"names": known[0], "L0_nH": out.round(4).tolist(), "extrapolation_delta_nH": dL.round(4).tolist(),
           "coarse_quad_nH": quad.round(4).tolist(), "coarse_lin12_nH": lin12.round(4).tolist(),
           "min_eigenvalue_nH": float(eig.min()),
           "sources": {k: getattr(a, k) for k in ("h05", "h1", "h2", "target")},
           "note": "coarse-mesh quad(0.5,1,2) - lin(1,2) added to the target; transfer assumed"}
    open(a.out, "w").write("RESULT " + json.dumps(res) + "\n")
    print("RESULT " + json.dumps(res))
    if eig.min() <= 0:
        raise SystemExit(f"corrected matrix not positive definite (min eig {eig.min():.4g} nH)")


if __name__ == "__main__":
    main()
