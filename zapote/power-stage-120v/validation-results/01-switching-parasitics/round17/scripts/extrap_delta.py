#!/usr/bin/env python3
"""Transfer a closure-height extrapolation change to a target matrix (round 17).

On the coarse mesh (1.0 mm edges), estimate the zero-height matrix with the
low-height points included ("best": a parabola through 0.5 / 1 / 2 mm, or,
with --h3, a cubic through 0.5 / 1 / 2 / 3 mm), and compare it entry by entry
with the method the target used on the fine mesh (--base lin12 = straight
line through 1 and 2 mm; quad123 = parabola through 1 / 2 / 3 mm, needs --h3):

    dL = best_coarse - base_coarse

and add dL to the target matrix. The 0.5 mm point carries the curvature the
fine campaign cannot see (round-17 d2/README, extrapolation test). Like the
crop correction, the transfer from the coarse to the fine mesh is an
ASSUMPTION; on the coarse mesh the 0.5 mm closure strips (0.6 mm wide) are
narrower than the 1.0 mm edges, so part of the curvature may be mesh error.
The output must stay symmetric positive definite.

    extrap_delta.py --h05 A --h1 B --h2 C [--h3 D] [--base lin12|quad123] --target T --out OUT
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
    ap.add_argument("--h3", default=None)
    ap.add_argument("--base", choices=("lin12", "quad123"), default="lin12")
    a = ap.parse_args()
    if a.base == "quad123" and not a.h3:
        raise SystemExit("--base quad123 needs --h3")
    keys = ("h05", "h1", "h2") + (("h3",) if a.h3 else ())
    mats = {k: read(getattr(a, k)) for k in keys + ("target",)}
    known = [n for n in (names(d) for _, d in mats.values()) if n]
    if not known or any(n != known[0] for n in known):
        raise SystemExit(f"port orders differ or are missing: {[names(d) for _, d in mats.values()]}")
    hs = {"h05": 0.5, "h1": 1.0, "h2": 2.0, "h3": 3.0}
    H = np.array([hs[k] for k in keys])
    Y = np.stack([mats[k][0] for k in keys])
    n = Y.shape[1]

    def poly0(hh, yy):
        """Value at h = 0 of the polynomial of degree len(hh) - 1 through the points."""
        return np.linalg.solve(np.vander(hh, increasing=True), yy.reshape(len(hh), -1))[0].reshape(n, n)

    best = poly0(H, Y)                                        # quad(0.5,1,2) or cubic(0.5,1,2,3)
    base = 2 * Y[1] - Y[2] if a.base == "lin12" else poly0(H[1:], Y[1:])
    dL = best - base
    out = mats["target"][0] + dL
    eig = np.linalg.eigvalsh((out + out.T) / 2)
    res = {"names": known[0], "L0_nH": out.round(4).tolist(), "extrapolation_delta_nH": dL.round(4).tolist(),
           "coarse_best_nH": best.round(4).tolist(), "coarse_base_nH": base.round(4).tolist(),
           "best": f"polynomial through h = {H.tolist()} mm", "base": a.base,
           "min_eigenvalue_nH": float(eig.min()),
           "sources": {k: getattr(a, k) for k in keys + ("target",)},
           "note": "coarse-mesh best - base added to the target; transfer from coarse to fine mesh assumed"}
    open(a.out, "w").write("RESULT " + json.dumps(res) + "\n")
    print("RESULT " + json.dumps(res))
    if eig.min() <= 0:
        raise SystemExit(f"corrected matrix not positive definite (min eig {eig.min():.4g} nH)")


if __name__ == "__main__":
    main()
