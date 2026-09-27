#!/usr/bin/env python3
"""Multi-layer DC copper resistance network for one net (task 04).

Rasterizes a net's copper on each layer to a square grid, connects neighbouring
cells on a layer with sheet conductance sigma*t, connects layers through vias
(barrel resistance), injects current at "source" points and removes it at
"sink" points, and solves for node voltages with scipy. From the solution it
reports the path resistance, the current density per cell, and the current in
every via.

Use the Miniforge Python (numpy, scipy, shapely 2):

    /Users/bennet/Miniforge3/bin/python3 04-current/sheet_solver.py --selftest

Library use (see run_net() at the bottom for a worked call):

    net = Net(pitch_mm=0.25)
    net.add_layer("F.Cu", polygons_mm=[...], thickness_um=70)
    net.add_via((x, y), drill_mm=0.3, plating_um=18, layers=("F.Cu", "In1.Cu"))
    result = net.solve(sources=[("F.Cu", x, y, amps)], sinks=[("In1.Cu", x, y)])

The self-test checks analytic cases: a single strip; two stacked strips
joined by vias; a four-layer via barrel; unequal sources (loss-equivalent
resistance); rejection of off-copper injection points; and an unused copper
island (excluded and reported). Do not trust board results unless it passes.

Corrections 2026-09-27 (validation-results/04-board-current-thermal audit):
via barrel length is split across hops by real layer spacing (it was applied
in full to every hop); resistance is loss-equivalent, sum(V*I)/I^2 (it was
max(V)/I); injection points must lie on copper (they snapped to the nearest
cell); a connectivity preflight excludes unused islands and rejects a source
without a sink (it returned NaN).
"""
from __future__ import annotations

import math
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve
from shapely import contains_xy
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

RHO_CU = 1.68e-8          # ohm*m at 20 C
ALPHA_CU = 0.00393         # per K
# Copper-centre heights (mm from the top surface) for stackup.json
# JLC041622-7628: 70 um / 0.4355 / 61 um / 0.5 / 61 um / 0.4355 / 70 um.
LAYER_Z_MM = {"F.Cu": 0.035, "In1.Cu": 0.07 + 0.4355 + 0.0305,
              "In2.Cu": 0.07 + 0.4355 + 0.061 + 0.5 + 0.0305,
              "B.Cu": 0.07 + 0.4355 + 0.061 + 0.5 + 0.061 + 0.4355 + 0.035}


class Net:
    def __init__(self, pitch_mm: float = 0.25, temp_c: float = 20.0, layer_z_mm: dict | None = None):
        self.h = pitch_mm
        self.layer_z = dict(layer_z_mm or LAYER_Z_MM)
        self.rho = RHO_CU * (1 + ALPHA_CU * (temp_c - 20.0))
        self.layers: dict[str, dict] = {}
        self.vias: list[dict] = []

    # ------------------------------------------------------------ geometry
    def add_layer(self, name: str, polygons_mm, thickness_um: float) -> None:
        geom = unary_union([Polygon(p).buffer(0) for p in polygons_mm])
        x0, y0, x1, y1 = geom.bounds
        xs = np.arange(x0 + self.h / 2, x1, self.h)
        ys = np.arange(y0 + self.h / 2, y1, self.h)
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        inside = contains_xy(geom, gx, gy)
        self.layers[name] = {"xs": xs, "ys": ys, "inside": inside, "t": thickness_um * 1e-6, "geom": geom}

    def add_via(self, xy, drill_mm: float, plating_um: float, layers, length_mm: float = 1.6) -> None:
        """A plated barrel joining `layers` (listed top to bottom). `length_mm`
        is the barrel length between the first and last listed layer; each hop
        gets its share in proportion to the layer spacing."""
        layers = tuple(sorted(layers, key=lambda n: self.layer_z[n]))
        r_in = drill_mm / 2 * 1e-3
        area = math.pi * ((r_in + plating_um * 1e-6) ** 2 - r_in ** 2)
        span = self.layer_z[layers[-1]] - self.layer_z[layers[0]]
        hops = []
        for a, b in zip(layers, layers[1:]):
            frac = (self.layer_z[b] - self.layer_z[a]) / span if span > 0 else 1.0 / (len(layers) - 1)
            hops.append(self.rho * (length_mm * 1e-3) * frac / area)
        self.vias.append({"xy": xy, "layers": layers, "hop_ohm": hops, "r_ohm": sum(hops)})

    # ------------------------------------------------------------ solve
    def _index(self):
        idx, offset = {}, 0
        for name, L in self.layers.items():
            ids = -np.ones(L["inside"].shape, dtype=np.int64)
            n = int(L["inside"].sum())
            ids[L["inside"]] = np.arange(offset, offset + n)
            idx[name] = ids
            offset += n
        return idx, offset

    def _cell(self, idx, layer, x, y):
        L = self.layers[layer]
        if not L["geom"].covers(Point(x, y)):
            raise ValueError(f"point ({x}, {y}) is not on {layer} copper")
        i = int(np.argmin(abs(L["xs"] - x)))
        j = int(np.argmin(abs(L["ys"] - y)))
        node = idx[layer][i, j]
        if node < 0:
            raise ValueError(f"point ({x}, {y}) is not on {layer} copper")
        return node

    def solve(self, sources, sinks):
        idx, n = self._index()
        rows, cols, vals = [], [], []

        def g(a, b, cond):
            rows.extend([a, b, a, b]); cols.extend([a, b, b, a]); vals.extend([cond, cond, -cond, -cond])

        for name, L in self.layers.items():
            gs = L["t"] / self.rho                      # sheet conductance per square
            ids = idx[name]
            for di, dj in ((1, 0), (0, 1)):
                a = ids[: ids.shape[0] - di, : ids.shape[1] - dj]
                b = ids[di:, dj:]
                m = (a >= 0) & (b >= 0)
                for aa, bb in zip(a[m], b[m]):
                    g(int(aa), int(bb), gs)
        via_edges = []
        for v in self.vias:
            nodes = [self._cell(idx, lyr, *v["xy"]) for lyr in v["layers"]]
            for (a, b), r_hop in zip(zip(nodes, nodes[1:]), v["hop_ohm"]):
                g(a, b, 1.0 / r_hop)
                via_edges.append((v, a, b, r_hop))
        G = coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
        inj = np.zeros(n)
        total = 0.0
        src_nodes = []
        for layer, x, y, amps in sources:
            node = self._cell(idx, layer, x, y)
            inj[node] += amps
            total += amps
            src_nodes.append((node, amps))
        sink_nodes = [self._cell(idx, layer, x, y) for layer, x, y in sinks]
        # Connectivity preflight: every source must share a component with a
        # sink; components touching neither are unused islands (excluded).
        n_comp, label = connected_components(G, directed=False)
        sink_comps = {int(label[s]) for s in sink_nodes}
        for node, _ in src_nodes:
            if int(label[node]) not in sink_comps:
                raise ValueError(f"source node {node} is not connected to any sink")
        used = np.isin(label, list(sink_comps))
        unused_cells = int((~used).sum())
        # Ground the sinks (V = 0); current exits there. Solve only used cells.
        keep = used.copy()
        keep[sink_nodes] = False
        Gk = G[keep][:, keep]
        v = np.full(n, np.nan)
        v[used] = 0.0
        v[keep] = spsolve(Gk.tocsc(), inj[keep])
        loss_w = float(sum(v[node] * amps for node, amps in src_nodes))
        via_currents = [{"xy": e[0]["xy"], "amps": (v[e[1]] - v[e[2]]) / e[3]} for e in via_edges]
        dens = {}
        for name, L in self.layers.items():
            ids = idx[name]
            vv = np.where(ids >= 0, v[np.clip(ids, 0, None)], np.nan)
            gx, gy = np.gradient(vv, self.h * 1e-3)
            j = np.hypot(gx, gy) / self.rho                # A/m^2
            dens[name] = j * L["t"] / 1e3                  # A per mm of width
        return {"r_ohm": loss_w / total ** 2 if total else float("nan"), "loss_w": loss_w,
                "source_volts": [float(v[node]) for node, _ in src_nodes],
                "unused_island_cells": unused_cells, "v": v,
                "via_currents": via_currents, "current_per_mm": dens, "index": idx}


# ------------------------------------------------------------------ self-test
def selftest() -> bool:
    ok = True
    # 1. One strip 10 mm x 50 mm, 70 um: R = rho L / (w t), injected/extracted
    #    through the full end edges.
    w, l, t = 10.0, 50.0, 70.0
    net = Net(pitch_mm=0.25)
    net.add_layer("F.Cu", [[(0, 0), (l, 0), (l, w), (0, w)]], t)
    ys = net.layers["F.Cu"]["ys"]
    k = len(ys)
    r = net.solve([("F.Cu", 0.2, y, 1.0 / k) for y in ys], [("F.Cu", l - 0.2, y) for y in ys])["r_ohm"]
    expect = RHO_CU * (l - 0.25) * 1e-3 / (w * 1e-3 * t * 1e-6)
    err = abs(r - expect) / expect
    print(f"strip: R = {r*1e3:.4f} mohm, analytic {expect*1e3:.4f} mohm, error {err*100:.2f} %")
    ok &= err < 0.02
    # 2. Two identical stacked strips joined by one via at each end: the
    #    parallel combination (vias with near-zero resistance here).
    net2 = Net(pitch_mm=0.25)
    for name in ("F.Cu", "In1.Cu"):
        net2.add_layer(name, [[(0, 0), (l, 0), (l, w), (0, w)]], t)
    for x in (0.2, l - 0.2):
        for y in net2.layers["F.Cu"]["ys"]:
            net2.add_via((x, y), drill_mm=3.0, plating_um=500, layers=("F.Cu", "In1.Cu"), length_mm=0.01)
    ys = net2.layers["F.Cu"]["ys"]
    r2 = net2.solve([("F.Cu", 0.2, y, 1.0 / len(ys)) for y in ys], [("F.Cu", l - 0.2, y) for y in ys])["r_ohm"]
    err2 = abs(r2 - expect / 2) / (expect / 2)
    print(f"two layers: R = {r2*1e3:.4f} mohm, analytic {expect/2*1e3:.4f} mohm, error {err2*100:.2f} %")
    ok &= err2 < 0.03
    # 3. Four-layer via barrel (audit probe): full-length barrel F.Cu -> B.Cu.
    net3 = Net(pitch_mm=1.0)
    for name in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        net3.add_layer(name, [[(0, 0), (2, 0), (2, 2), (0, 2)]], 70 if name in ("F.Cu", "B.Cu") else 61)
    net3.add_via((0.5, 0.5), 0.8, 18, ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"), length_mm=1.6)
    r3 = net3.solve([("F.Cu", 0.5, 0.5, 1.0)], [("B.Cu", 0.5, 0.5)])["r_ohm"]
    ri = 0.4e-3
    expect3 = RHO_CU * 1.6e-3 / (math.pi * ((ri + 18e-6) ** 2 - ri ** 2))
    err3 = abs(r3 - expect3) / expect3
    print(f"four-layer via: R = {r3*1e3:.4f} mohm, analytic {expect3*1e3:.4f} mohm, error {err3*100:.2f} %")
    ok &= err3 < 1e-6
    # 4. Two unequal sources on a strip: loss-equivalent R = sum(V I) / I^2.
    net4 = Net(pitch_mm=0.5)
    net4.add_layer("F.Cu", [[(0, 0), (20, 0), (20, 1), (0, 1)]], 70)
    res4 = net4.solve([("F.Cu", 0.25, 0.25, 1), ("F.Cu", 10.25, 0.25, 1)],
                      [("F.Cu", 19.75, 0.25), ("F.Cu", 19.75, 0.75)])
    expect4 = sum(res4["source_volts"]) * 1.0 / 4.0
    err4 = abs(res4["r_ohm"] - expect4) / expect4
    print(f"unequal sources: R_loss = {res4['r_ohm']*1e3:.4f} mohm, sum(VI)/I^2 {expect4*1e3:.4f} mohm")
    ok &= err4 < 1e-9
    # 5. Off-copper injection must be refused.
    net5 = Net(pitch_mm=0.5)
    net5.add_layer("F.Cu", [[(0, 0), (1, 0), (1, 1), (0, 1)]], 70)
    try:
        net5.solve([("F.Cu", 1.1, 0.25, 1)], [("F.Cu", 0.75, 0.75)])
        refused = False
    except ValueError:
        refused = True
    print(f"off-copper injection refused: {refused}")
    ok &= refused
    # 6. An unused island is excluded and reported, not NaN.
    net6 = Net(pitch_mm=0.5)
    net6.add_layer("F.Cu", [[(0, 0), (1, 0), (1, 1), (0, 1)], [(3, 0), (4, 0), (4, 1), (3, 1)]], 70)
    res6 = net6.solve([("F.Cu", 0.25, 0.25, 1)], [("F.Cu", 0.75, 0.25)])
    good6 = math.isfinite(res6["r_ohm"]) and res6["unused_island_cells"] == 4
    print(f"unused island: R finite {math.isfinite(res6['r_ohm'])}, excluded cells {res6['unused_island_cells']}")
    ok &= good6
    # 7. A source on an island with no sink must be refused.
    try:
        net6.solve([("F.Cu", 3.25, 0.25, 1)], [("F.Cu", 0.75, 0.25)])
        refused7 = False
    except ValueError:
        refused7 = True
    print(f"source without sink refused: {refused7}")
    ok &= refused7
    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    print(__doc__)
