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

The self-test checks two analytic cases (single strip; two stacked strips
joined by one via at each end). Do not trust board results unless it passes.
"""
from __future__ import annotations

import math
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from shapely import contains_xy
from shapely.geometry import Polygon
from shapely.ops import unary_union

RHO_CU = 1.68e-8          # ohm*m at 20 C
ALPHA_CU = 0.00393         # per K


class Net:
    def __init__(self, pitch_mm: float = 0.25, temp_c: float = 20.0):
        self.h = pitch_mm
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
        r_in = drill_mm / 2 * 1e-3
        area = math.pi * ((r_in + plating_um * 1e-6) ** 2 - r_in ** 2)
        self.vias.append({"xy": xy, "layers": tuple(layers),
                          "r_ohm": self.rho * (length_mm * 1e-3) / area})

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
            for a, b in zip(nodes, nodes[1:]):
                g(a, b, 1.0 / v["r_ohm"])
                via_edges.append((v, a, b))
        G = coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
        inj = np.zeros(n)
        total = 0.0
        for layer, x, y, amps in sources:
            inj[self._cell(idx, layer, x, y)] += amps
            total += amps
        sink_nodes = [self._cell(idx, layer, x, y) for layer, x, y in sinks]
        # Ground the sinks: remove their rows/cols (V = 0), current exits there.
        keep = np.ones(n, dtype=bool)
        keep[sink_nodes] = False
        Gk = G[keep][:, keep]
        v = np.zeros(n)
        v[keep] = spsolve(Gk.tocsc(), inj[keep])
        src_v = max(v[self._cell(idx, l, x, y)] for l, x, y, _ in sources)
        via_currents = [{"xy": e[0]["xy"], "amps": (v[e[1]] - v[e[2]]) / e[0]["r_ohm"]} for e in via_edges]
        dens = {}
        for name, L in self.layers.items():
            ids = idx[name]
            vv = np.where(ids >= 0, v[np.clip(ids, 0, None)], np.nan)
            gx, gy = np.gradient(vv, self.h * 1e-3)
            j = np.hypot(gx, gy) / self.rho                # A/m^2
            dens[name] = j * L["t"] / 1e3                  # A per mm of width
        return {"r_ohm": src_v / total if total else float("nan"), "v": v,
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
    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    print(__doc__)
