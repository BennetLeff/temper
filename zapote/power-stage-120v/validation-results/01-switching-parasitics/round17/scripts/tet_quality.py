"""Tetrahedron quality histogram for a MSH 2.2 ASCII mesh.

Quality is the normalised radius ratio q = 3 r_in / r_circ (1 for a regular
tet, 0 for a degenerate one). Also reports the aspect ratio longest edge /
shortest altitude, the measure that governs edge-element conditioning.
"""
from __future__ import annotations

import argparse
import json

import numpy as np


def read(path):
    with open(path) as f:
        for line in f:
            if line.startswith("$Nodes"):
                n = int(next(f))
                xyz = np.loadtxt([next(f) for _ in range(n)])
            elif line.startswith("$Elements"):
                n = int(next(f))
                rows = [next(f).split() for _ in range(n)]
                tets = np.array([r[-4:] for r in rows if r[1] == "4"], dtype=np.int64)
    idx = np.zeros(int(xyz[:, 0].max()) + 1, dtype=np.int64)
    idx[xyz[:, 0].astype(np.int64)] = np.arange(len(xyz))
    return xyz[:, 1:], idx[tets]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("msh")
    a = ap.parse_args()
    X, T = read(a.msh)
    P = X[T]                                       # (n, 4, 3)
    vol = np.abs(np.einsum("ij,ij->i", P[:, 1] - P[:, 0], np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 0]))) / 6
    faces = [(1, 2, 3), (0, 2, 3), (0, 1, 3), (0, 1, 2)]
    areas = np.stack([np.linalg.norm(np.cross(P[:, j] - P[:, i], P[:, k] - P[:, i]), axis=1) / 2
                      for i, j, k in faces], 1)
    r_in = 3 * vol / areas.sum(1)
    edges = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    L = np.stack([np.linalg.norm(P[:, j] - P[:, i], axis=1) for i, j in edges], 1)
    # circumradius via products of opposite edges
    a_, b_, c_ = L[:, 0] * L[:, 5], L[:, 1] * L[:, 4], L[:, 2] * L[:, 3]
    s = (a_ + b_ + c_) / 2
    r_circ = np.sqrt(np.clip(s * (s - a_) * (s - b_) * (s - c_), 0, None)) / (6 * vol)
    q = 3 * r_in / r_circ
    alt_min = 3 * vol / areas.max(1)
    aspect = L.max(1) / alt_min
    pct = [50, 90, 99, 99.9, 100]
    res = {"tets": int(len(T)),
           "q_min": float(q.min()), "q_percentiles_low": {p: float(np.percentile(q, 100 - p)) for p in pct[:-1]},
           "q_below": {t: int((q < t).sum()) for t in (0.1, 0.05, 0.01, 0.001)},
           "aspect_percentiles": {p: float(np.percentile(aspect, p)) for p in pct},
           "aspect_above": {t: int((aspect > t).sum()) for t in (10, 30, 100, 1000)}}
    worst = np.argsort(q)[:5]
    res["worst"] = [{"q": float(q[i]), "centroid": [round(v, 3) for v in P[i].mean(0)],
                     "edges": [round(v, 4) for v in L[i]]} for i in worst]
    print("RESULT " + json.dumps(res))


if __name__ == "__main__":
    main()
