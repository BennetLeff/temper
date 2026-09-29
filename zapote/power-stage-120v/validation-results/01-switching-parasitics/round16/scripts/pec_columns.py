"""Count far-field (physical 3) triangles that are not on the outer air box.

mesh25d meshes label hole walls as physical 3; any such triangle inside the
box is a PEC column through the layers (a spurious via). Must be zero."""
from __future__ import annotations

import argparse
import json

import numpy as np

from check_ports import read_msh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("msh")
    a = ap.parse_args()
    nodes, tris = read_msh(a.msh)
    X = np.array(list(nodes.values()))
    lo, hi = X.min(0), X.max(0)
    inner = []
    for phys, t in tris:
        if phys != 3:
            continue
        P = np.array([nodes[v] for v in t])
        if not any(np.allclose(P[:, k], lo[k]) or np.allclose(P[:, k], hi[k]) for k in range(3)):
            inner.append(P.mean(0))
    xy = sorted({(round(p[0], 1), round(p[1], 1)) for p in inner})
    print("RESULT " + json.dumps({"inner_farfield_triangles": len(inner), "column_xy": xy[:10]}))


if __name__ == "__main__":
    main()
