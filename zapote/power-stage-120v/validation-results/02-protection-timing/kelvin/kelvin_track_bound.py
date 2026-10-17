#!/usr/bin/env python3
"""Upper bound on the Kelvin-return resistance seen by the shunt-OCP threshold (native-20).

The OCP threshold divider bottom (R35.2), the 2.5 V reference anode and the
other HOT-side returns share net `ocp_kelvin_p`, whose only connection to the
shunt's sense terminal is R5.2. HOT-side supply current returns through that
copper to R5.2, so any resistance between R35.2 and R5.2 shifts the trip point.
Shunt-OCP algebra (power_stage_120v.ato): trip current
  I*Rs = 2.5 + e_ref - 2 e_th - 2k(2.5 + e_ref - e_th),  k = R35/(R34+R35)
so dI/de_th = -(2 - 2k)/Rs ~ -1.03 A/mV and dI/de_ref = (1 - 2k)/Rs ~ +0.03 A/mV.

Bound: by Rayleigh monotonicity, deleting copper never lowers an effective
resistance, so a network of only this net's tracks and vias (the In1 plane
omitted) bounds R_eff(pad, R5.2) from above; and for any resistor network the
potential a current injected at j raises at k (sink R5.2) is <= R_eff(k, R5.2).
Hence |e_th| <= I_HOT_total * R_eff(R35.2, R5.2) (track/via-only network).
If the track/via network does not connect the two pads, the bound is reported
as UNAVAILABLE (the plane then carries it and a plane solve is needed).

Conservative constants: copper 50 um (2 oz nominal 70 um), resistivity at 125 C,
via barrel plating 15 um.

    <KiCad python3> kelvin_track_bound.py BOARD.kicad_pcb [--net ocp_kelvin_p] [--sink R5.2]
"""
import argparse
import json
import math

import pcbnew

RHO = 1.72e-8 * (1 + 0.00393 * 100)     # ohm m at 125 C
T_CU = 50e-6                             # m, conservative
T_VIA = 15e-6                            # m, barrel plating
BOARD_T = 1.653e-3


def solve(A, b):
    """Dense Gaussian elimination with partial pivoting (KiCad's Python has no numpy)."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            if f:
                Mr, Mc = M[r], M[c]
                for k in range(c, n + 1):
                    Mr[k] -= f * Mc[k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (M[r][n] - sum(M[r][k] * x[k] for k in range(r + 1, n))) / M[r][r]
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board"); ap.add_argument("--net", default="ocp_kelvin_p"); ap.add_argument("--sink", default="R5.2")
    ap.add_argument("--json")
    a = ap.parse_args()
    b = pcbnew.LoadBoard(a.board)
    tracks = [t for t in b.GetTracks() if t.GetNetname() == a.net]
    segs = [t for t in tracks if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in tracks if t.GetClass() == "PCB_VIA"]
    pads = {f"{p.GetParentFootprint().GetReference()}.{p.GetNumber()}": p for p in b.GetPads() if p.GetNetname() == a.net}
    nodes, edges = {}, []

    def node(key):
        return nodes.setdefault(key, len(nodes))

    def pt_key(layer, pos):
        return ("pt", layer, round(pos.x / 1000), round(pos.y / 1000))   # 1 um grid

    # track segments
    for t in segs:
        L = t.GetLength() * 1e-9
        w = t.GetWidth() * 1e-9
        edges.append((node(pt_key(t.GetLayer(), t.GetStart())), node(pt_key(t.GetLayer(), t.GetEnd())), RHO * L / (w * T_CU)))
    # T-junctions: an endpoint lying on another segment of the same layer splits it conceptually;
    # connect the endpoint to both ends of that segment with the proportional resistances.
    for t in segs:
        for u in segs:
            if u is t or u.GetLayer() != t.GetLayer():
                continue
            for p in (t.GetStart(), t.GetEnd()):
                if pt_key(t.GetLayer(), p) in (pt_key(u.GetLayer(), u.GetStart()), pt_key(u.GetLayer(), u.GetEnd())):
                    continue
                if u.HitTest(p, 0):
                    s, e = u.GetStart(), u.GetEnd()
                    Lu = max(u.GetLength(), 1)
                    f = math.hypot(p.x - s.x, p.y - s.y) / Lu
                    r = RHO * u.GetLength() * 1e-9 / (u.GetWidth() * 1e-9 * T_CU)
                    k = node(pt_key(t.GetLayer(), p))
                    edges.append((k, node(pt_key(u.GetLayer(), s)), max(f * r, 1e-9)))
                    edges.append((k, node(pt_key(u.GetLayer(), e)), max((1 - f) * r, 1e-9)))
    # vias: tie every copper layer at the via position
    for v in vias:
        d = v.GetDrill() * 1e-9
        rv = RHO * BOARD_T / (math.pi * d * T_VIA)
        layers = [l for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)]
        ks = [node(pt_key(l, v.GetPosition())) for l in layers]
        for i in range(len(ks) - 1):
            edges.append((ks[i], ks[i + 1], rv / 3))
        # track ends inside the via annulus
        for t in segs:
            for p in (t.GetStart(), t.GetEnd()):
                if v.HitTest(p, 0):
                    edges.append((node(pt_key(t.GetLayer(), p)), ks[[pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu].index(t.GetLayer())], 1e-9))
    # pads: zero-resistance node tied to every track end / via inside the pad on its layers
    for name, p in pads.items():
        k = node(("pad", name))
        for t in segs:
            for q in (t.GetStart(), t.GetEnd()):
                if p.IsOnLayer(t.GetLayer()) and p.HitTest(q, 0):
                    edges.append((k, node(pt_key(t.GetLayer(), q)), 1e-9))
        for v in vias:
            if p.HitTest(v.GetPosition(), 0):
                for l in (pcbnew.F_Cu, pcbnew.B_Cu):
                    if p.IsOnLayer(l):
                        edges.append((k, node(pt_key(l, v.GetPosition())), 1e-9))
    n = len(nodes)
    adj = [[] for _ in range(n)]
    for i, j, _ in edges:
        adj[i].append(j); adj[j].append(i)
    sink = nodes[("pad", a.sink)]
    comp, stack = {sink}, [sink]
    while stack:
        for m in adj[stack.pop()]:
            if m not in comp:
                comp.add(m); stack.append(m)
    keep = sorted(k for k in comp if k != sink)
    pos = {k: i for i, k in enumerate(keep)}
    m = len(keep)
    G = [[0.0] * m for _ in range(m)]
    for i, j, r in edges:
        g = 1 / r
        for x, y in ((i, j), (j, i)):
            if x in pos:
                G[pos[x]][pos[x]] += g
                if y in pos:
                    G[pos[x]][pos[y]] -= g
    out = {"net": a.net, "sink": a.sink, "board": a.board, "constants": {"rho_ohm_m": RHO, "t_cu_m": T_CU, "t_via_m": T_VIA},
           "nodes": n, "pads": {}}
    for name in sorted(pads):
        k = nodes[("pad", name)]
        if k == sink:
            continue
        if k not in pos:
            out["pads"][name] = None
            continue
        e = [0.0] * m
        e[pos[k]] = 1.0
        out["pads"][name] = round(solve(G, e)[pos[k]] * 1e3, 4)    # mOhm effective resistance to sink
    for name, r in out["pads"].items():
        print(f"{name:8s} {'not connected by tracks/vias (plane only)' if r is None else f'{r:.3f} mOhm'}")
    if a.json:
        open(a.json, "w").write(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
