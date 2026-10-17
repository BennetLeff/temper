"""Check that each driven port sheet in a mesh25d_simple.py mesh ends on PEC.

A port sheet carries a surface current K along its direction d. Along its
long sides K is tangent to the edge, so those edges may lie in air. The two
ends (edges perpendicular to d) must lie on a PEC face, otherwise the current
has nowhere to go (div K != 0 in air) and the magnetostatic source is
inconsistent. Prints, per port, the total free-edge length at the ends that
lies on PEC and the length that ends in air.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

import numpy as np


def read_msh(path):
    nodes, elems = {}, []
    with open(path) as f:
        for line in f:
            if line.startswith("$Nodes"):
                n = int(next(f))
                for _ in range(n):
                    i, x, y, z = next(f).split()
                    nodes[int(i)] = (float(x), float(y), float(z))
            elif line.startswith("$Elements"):
                n = int(next(f))
                for _ in range(n):
                    p = next(f).split()
                    t, nt = int(p[1]), int(p[2])
                    if t == 2:
                        elems.append((int(p[3]), tuple(int(v) for v in p[3 + nt:])))
    return nodes, elems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("msh")
    ap.add_argument("log", help="mesher log containing the RESULT line")
    a = ap.parse_args()
    res = next(json.loads(l[7:]) for l in open(a.log) if l.startswith("RESULT "))
    nodes, tris = read_msh(a.msh)
    pec_edges = set()
    for phys, t in tris:
        if phys == 2:
            for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                pec_edges.add((min(u, v), max(u, v)))
    out = []
    for p in res["ports"]:
        d = np.array(p["direction"])
        cnt = Counter()
        for phys, t in tris:
            if phys == p["physical"]:
                for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                    cnt[(min(u, v), max(u, v))] += 1
        on_pec = in_air = side = 0.0
        air_pts = []
        for (u, v), c in cnt.items():
            if c != 1:
                continue
            e = np.subtract(nodes[v], nodes[u])
            L = float(np.linalg.norm(e))
            if abs(e @ d) / L > 0.5:          # edge along the current: a side
                side += L
            elif (u, v) in pec_edges:
                on_pec += L
            else:
                in_air += L
                air_pts.append([round(c_, 3) for c_ in nodes[u]])
        row = {"port": p["name"], "end_on_pec_mm": round(on_pec, 4), "end_in_air_mm": round(in_air, 4),
               "side_mm": round(side, 4), "air_examples": air_pts[:4]}
        out.append(row)
        print(json.dumps(row))
    print("RESULT " + json.dumps(out))


if __name__ == "__main__":
    main()
