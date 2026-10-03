"""Discrete consistency of each port source in a mesh25d_simple.py mesh.

A constant sheet current K on triangles T gives, for every mesh node i, the
source moment s_i = sum_T K . grad(phi_i) A_T (phi_i the nodal hat function).
The magnetostatic source is consistent only if s_i = 0 at every node that is
not on PEC: then the load vector is orthogonal to the gradient null space of
the curl-curl operator and an ungauged iterative solve can converge. A
nonzero s_i is current leaking into the air at that node, e.g. where a
sheet side is not parallel to K. Reported in amperes (K in A/mm, lengths mm).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

import numpy as np

from check_ports import read_msh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("msh")
    ap.add_argument("log")
    a = ap.parse_args()
    res = next(json.loads(l[7:]) for l in open(a.log) if l.startswith("RESULT "))
    nodes, tris = read_msh(a.msh)
    pec_nodes = {v for phys, t in tris if phys == 2 for v in t}
    out = []
    for p in res["ports"]:
        K = np.array(p["direction"]) * p["k_A_per_m"] * 1e-3      # A/mm
        s = defaultdict(float)
        for phys, t in tris:
            if phys != p["physical"]:
                continue
            P = np.array([nodes[v] for v in t])
            n = np.cross(P[1] - P[0], P[2] - P[0])
            A2 = np.linalg.norm(n)
            for k in range(3):
                # grad phi_k = n_hat x (P[k+2]-P[k+1]) / (2A), A_T grad phi_k = n_hat x e / 2
                e = P[(k + 2) % 3] - P[(k + 1) % 3]
                s[t[k]] += float(K @ np.cross(n / A2, e)) / 2
        air = {i: v for i, v in s.items() if i not in pec_nodes}
        pec = {i: v for i, v in s.items() if i in pec_nodes}
        worst = sorted(air.items(), key=lambda kv: -abs(kv[1]))[:3]
        row = {"port": p["name"], "port_current_A": round(float(np.linalg.norm(K)) * res.get("port_w_mm", 0.6), 4),
               "air_nodes": len(air), "leak_sum_abs_A": sum(abs(v) for v in air.values()),
               "leak_max_A": max((abs(v) for v in air.values()), default=0.0),
               "pec_net_A": sum(pec.values()),
               "worst": [[[round(c, 3) for c in nodes[i]], v] for i, v in worst]}
        out.append(row)
        print(json.dumps(row))
    print("RESULT " + json.dumps(out))


if __name__ == "__main__":
    main()
