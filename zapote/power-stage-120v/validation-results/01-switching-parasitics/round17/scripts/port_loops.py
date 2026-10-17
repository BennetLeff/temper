"""Check that each port closes a loop through one connected PEC body.

Current driven by a port sheet enters PEC at one end and must leave through
the other end on the same connected PEC surface. If the ends are on different
bodies (copper cut by defeaturing, a missing via or bridge), the source has a
net current into each body; the ungauged curl-curl system is then
inconsistent even though the total over all PEC sums to zero. Reports the PEC
components (by shared mesh nodes) that each port's end nodes touch, and each
component's size and bounding box.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from check_ports import read_msh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("msh")
    ap.add_argument("log")
    ap.add_argument("--closures", default=None, help="report the PEC body under each closure end")
    a = ap.parse_args()
    res = next(json.loads(l[7:]) for l in open(a.log) if l.startswith("RESULT "))
    nodes, tris = read_msh(a.msh)
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for phys, t in tris:
        if phys in (2, 3):
            for v in t:
                parent.setdefault(v, v)
            r0 = find(t[0])
            for v in t[1:]:
                r = find(v)
                if r != r0:
                    parent[r] = r0
    comp_nodes = {}
    for v in parent:
        comp_nodes.setdefault(find(v), []).append(v)
    far_roots = {find(v) for phys, t in tris if phys == 3 for v in t}
    out = []
    for p in res["ports"]:
        ends = {v for phys, t in tris if phys == p["physical"] for v in t if v in parent}
        roots = sorted({find(v) for v in ends})
        comps = []
        for r in roots:
            xyz = np.array([nodes[v] for v in comp_nodes[r]])
            comps.append({"nodes": len(comp_nodes[r]), "farfield": r in far_roots,
                          "bbox": [[round(v, 2) for v in xyz.min(0)], [round(v, 2) for v in xyz.max(0)]]})
        row = {"port": p["name"], "pec_components_touched": len(roots), "closed_loop": len(roots) == 1,
               "components": comps}
        out.append(row)
        print(json.dumps(row))
    # Which PEC body each closure end lands on: PEC nodes inside the leg
    # column from the top copper up to below the arch span (Z_TOP <= z < 2.4).
    legs = []
    if a.closures:
        ids = {r: k for k, r in enumerate(sorted(comp_nodes, key=lambda r: -len(comp_nodes[r])))}
        pts = np.array([nodes[v] for v in parent])
        keys = list(parent)
        for cl in json.load(open(a.closures)):
            ends = []
            for (px, py) in (cl["a"], cl["b"]):
                m = ((np.abs(pts[:, 0] - px) <= 0.31) & (np.abs(pts[:, 1] + py) <= 0.31)
                     & (pts[:, 2] >= 1.5625) & (pts[:, 2] < 2.4))
                ends.append(sorted({ids[find(keys[i])] for i in np.flatnonzero(m)}))
            legs.append({"closure": cl["name"], "kind": cl["kind"], "a_body": ends[0], "b_body": ends[1]})
            print(json.dumps(legs[-1]))
        sizes = {ids[r]: len(v) for r, v in comp_nodes.items()}
        print(json.dumps({"body_sizes": dict(sorted(sizes.items()))}))
    print("RESULT " + json.dumps({"pec_components": len(comp_nodes), "ports": out, "closure_ends": legs}))


if __name__ == "__main__":
    main()
