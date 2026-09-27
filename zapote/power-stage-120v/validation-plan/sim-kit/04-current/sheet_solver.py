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
resistance); rejection of off-copper injection points; an unused copper
island (excluded and reported); a 0.2 mm copper gap that must not conduct;
and a drilled via (void drill, annulus contact, injection inside the drill). Do not trust board results unless it passes.

Corrections 2026-09-27 (validation-results/04-board-current-thermal audit):
via barrel length is split across hops by real layer spacing (it was applied
in full to every hop); resistance is loss-equivalent, sum(V*I)/I^2 (it was
max(V)/I); injection points must lie on copper (they snapped to the nearest
cell); a connectivity preflight excludes unused islands and rejects a source
without a sink (it returned NaN).

Corrections 2026-09-27, round 2: grid edges are kept only when the segment
between cell centres lies in copper (the raster bridged real gaps smaller
than the pitch); via drills are voids on every layer they pass, and each
barrel is a node per layer joined to its annulus cells; a source or sink
inside a drill attaches to the barrel node.
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

VIA_SECTORS = 8   # azimuthal columns per empty via barrel
RHO_CU = 1.68e-8          # ohm*m at 20 C
ALPHA_CU = 0.00393         # per K
# Copper-centre heights (mm from the top surface) for stackup.json
# JLC041622-7628: 70 um / 0.4355 / 61 um / 0.5 / 61 um / 0.4355 / 70 um.
LAYER_Z_MM = {"F.Cu": 0.035, "In1.Cu": 0.07 + 0.4355 + 0.0305,
              "In2.Cu": 0.07 + 0.4355 + 0.061 + 0.5 + 0.0305,
              "B.Cu": 0.07 + 0.4355 + 0.061 + 0.5 + 0.061 + 0.4355 + 0.035}


class Net:
    """One net's copper on several layers, solved as a resistor network.

    Geometry is kept as polygons until solve(): each via's drill is subtracted
    from the copper of every layer it joins, the copper is rasterized at
    `pitch_mm`, and a grid edge is kept only if the straight segment between
    the two cell centres lies in copper (no edges across real gaps or drills).
    Each via gets one barrel node per layer, joined to the first ring of copper
    cells around its drill (the annulus contact) and to the next layer's
    barrel node through its share of the barrel resistance. A source or sink
    point inside a drill attaches to that via's barrel node on that layer.
    """

    def __init__(self, pitch_mm: float = 0.25, temp_c: float = 20.0, layer_z_mm: dict | None = None):
        self.h = pitch_mm
        self.layer_z = dict(layer_z_mm or LAYER_Z_MM)
        self.rho = RHO_CU * (1 + ALPHA_CU * (temp_c - 20.0))
        self.layers: dict[str, dict] = {}
        self.vias: list[dict] = []
        self._built = None

    # ------------------------------------------------------------ geometry
    def add_layer(self, name: str, polygons_mm, thickness_um: float, holes_mm=()) -> None:
        """Copper polygons of this net on one layer. `holes_mm` are extra voids
        (polygons) to subtract, e.g. unplated holes. Via drills are subtracted
        automatically."""
        geom = unary_union([Polygon(p).buffer(0) for p in polygons_mm])
        if holes_mm:
            geom = geom.difference(unary_union([Polygon(p).buffer(0) for p in holes_mm]))
        self.layers[name] = {"geom0": geom, "t": thickness_um * 1e-6}
        self._built = None

    def add_via(self, xy, drill_mm: float, plating_um: float, layers, length_mm: float = 1.6,
                filled: bool = False) -> None:
        """A plated barrel joining `layers`. `length_mm` is the barrel length
        between the outermost listed layers; each hop gets its share in
        proportion to the layer spacing.

        filled=False (a via): the hole is empty, so the barrel is a thin tube.
        It is split into VIA_SECTORS azimuthal columns, each touching only the
        annulus cells in its angle, joined around the ring by the plating's
        own conductance. Current passing a via in a plane goes around the
        hole, not through it. A source or sink inside the drill is refused.

        filled=True (a through-hole pad with a soldered lead): the lead and
        solder make the hole equipotential on each layer, so the barrel is one
        node per layer and a source or sink inside the drill attaches to it.
        The vertical resistance is still the plating alone (the lead and
        solder are ignored, which is conservative)."""
        layers = tuple(sorted(layers, key=lambda n: self.layer_z[n]))
        r_in = drill_mm / 2 * 1e-3
        area = math.pi * ((r_in + plating_um * 1e-6) ** 2 - r_in ** 2)
        span = self.layer_z[layers[-1]] - self.layer_z[layers[0]]
        hops = []
        for a, b in zip(layers, layers[1:]):
            frac = (self.layer_z[b] - self.layer_z[a]) / span if span > 0 else 1.0 / (len(layers) - 1)
            hops.append(self.rho * (length_mm * 1e-3) * frac / area)
        self.vias.append({"xy": tuple(xy), "drill_mm": drill_mm, "plating_m": plating_um * 1e-6,
                          "layers": layers, "hop_ohm": hops, "r_ohm": sum(hops), "filled": filled})
        self._built = None

    # ------------------------------------------------------------ build
    def _build(self):
        if self._built is not None:
            return self._built
        from shapely import covers, linestrings, prepare
        offset = 0
        grids = {}
        rows, cols, vals = [], [], []

        def g(a, b, cond):
            rows.extend([a, b, a, b]); cols.extend([a, b, b, a]); vals.extend([cond, cond, -cond, -cond])

        for name, L in self.layers.items():
            geom = L["geom0"]
            drills = [Point(*v["xy"]).buffer(v["drill_mm"] / 2, 32) for v in self.vias if name in v["layers"]]
            if drills:
                geom = geom.difference(unary_union(drills))
            prepare(geom)
            x0, y0, x1, y1 = geom.bounds
            xs = np.arange(x0 + self.h / 2, x1, self.h)
            ys = np.arange(y0 + self.h / 2, y1, self.h)
            gx, gy = np.meshgrid(xs, ys, indexing="ij")
            inside = contains_xy(geom, gx, gy)
            ids = -np.ones(inside.shape, dtype=np.int64)
            n = int(inside.sum())
            ids[inside] = np.arange(offset, offset + n)
            offset += n
            gs = L["t"] / self.rho
            dropped = 0
            for di, dj in ((1, 0), (0, 1)):
                a = ids[: ids.shape[0] - di, : ids.shape[1] - dj]
                b = ids[di:, dj:]
                m = (a >= 0) & (b >= 0)
                if not m.any():
                    continue
                ia, ja = np.nonzero(m)
                seg = np.stack([np.stack([xs[ia], ys[ja]], axis=1),
                                np.stack([xs[ia + di], ys[ja + dj]], axis=1)], axis=1)
                ok = covers(geom, linestrings(seg))
                dropped += int((~ok).sum())
                for aa, bb in zip(a[m][ok], b[m][ok]):
                    g(int(aa), int(bb), gs)
            grids[name] = {"xs": xs, "ys": ys, "ids": ids, "geom": geom, "gs": gs, "dropped_edges": dropped}
        # Barrel nodes and annulus contacts. nodes[layer] is a list: one node
        # for a filled barrel, VIA_SECTORS nodes (by angle) for an empty one.
        via_nodes = []
        for v in self.vias:
            k = 1 if v["filled"] else VIA_SECTORS
            nodes = {}
            rd = v["drill_mm"] / 2
            cx, cy = v["xy"]
            for lyr in v["layers"]:
                G_ = grids[lyr]
                nodes[lyr] = list(range(offset, offset + k))
                offset += k
                ii = np.nonzero(abs(G_["xs"] - cx) <= rd + 1.5 * self.h)[0]
                jj = np.nonzero(abs(G_["ys"] - cy) <= rd + 1.5 * self.h)[0]
                contacts = []
                for i in ii:
                    for j in jj:
                        node = G_["ids"][i, j]
                        dx, dy = G_["xs"][i] - cx, G_["ys"][j] - cy
                        d = math.hypot(dx, dy)
                        if node >= 0 and d <= rd + 1.05 * self.h:
                            sector = int((math.atan2(dy, dx) % (2 * math.pi)) / (2 * math.pi) * k) % k
                            contacts.append((int(node), d, sector))
                if not contacts:
                    raise ValueError(f"via at {v['xy']} has no copper annulus on {lyr} at pitch {self.h} mm")
                # Radial conduction from the barrel wall to each contact cell
                # over its share of the circumference.
                arc = 2 * math.pi * rd / len(contacts)
                for node, d, sector in contacts:
                    g(nodes[lyr][sector], node, G_["gs"] * arc / max(d - rd, self.h / 2))
                if k > 1:
                    # Around the ring: the plating wall, one layer thick.
                    g_ring = v["plating_m"] * self.layers[lyr]["t"] / self.rho / (2 * math.pi * rd * 1e-3 / k)
                    for s_ in range(k):
                        g(nodes[lyr][s_], nodes[lyr][(s_ + 1) % k], g_ring)
            for (a, b), r_hop in zip(zip(v["layers"], v["layers"][1:]), v["hop_ohm"]):
                for s_ in range(k):
                    g(nodes[a][s_], nodes[b][s_], 1.0 / (r_hop * k))
            via_nodes.append(nodes)
        G = coo_matrix((vals, (rows, cols)), shape=(offset, offset)).tocsr()
        self._built = (grids, via_nodes, G, offset)
        return self._built

    def _node(self, layer, x, y):
        grids, via_nodes, _, _ = self._build()
        for v, nodes in zip(self.vias, via_nodes):
            if layer in nodes and math.hypot(x - v["xy"][0], y - v["xy"][1]) <= v["drill_mm"] / 2:
                if not v["filled"]:
                    raise ValueError(f"point ({x}, {y}) is inside the empty drill of the via at {v['xy']}; "
                                     "inject at copper, or add the barrel with filled=True if it is a lead")
                return nodes[layer][0]
        G_ = grids[layer]
        if not G_["geom"].covers(Point(x, y)):
            raise ValueError(f"point ({x}, {y}) is not on {layer} copper")
        i = int(np.argmin(abs(G_["xs"] - x)))
        j = int(np.argmin(abs(G_["ys"] - y)))
        node = G_["ids"][i, j]
        if node < 0:
            raise ValueError(f"point ({x}, {y}) on {layer} copper has no grid cell at pitch {self.h} mm")
        return int(node)

    # ------------------------------------------------------------ solve
    def solve(self, sources, sinks):
        grids, via_nodes, G, n = self._build()
        inj = np.zeros(n)
        total = 0.0
        src_nodes = []
        for layer, x, y, amps in sources:
            node = self._node(layer, x, y)
            inj[node] += amps
            total += amps
            src_nodes.append((node, amps))
        sink_nodes = [self._node(layer, x, y) for layer, x, y in sinks]
        # Connectivity preflight: every source must share a component with a
        # sink; components touching neither are unused islands (excluded).
        _, label = connected_components(G, directed=False)
        sink_comps = {int(label[s]) for s in sink_nodes}
        for node, _ in src_nodes:
            if int(label[node]) not in sink_comps:
                raise ValueError(f"source node {node} is not connected to any sink")
        used = np.isin(label, list(sink_comps))
        unused_cells = int((~used).sum())
        keep = used.copy()
        keep[sink_nodes] = False
        v = np.full(n, np.nan)
        v[used] = 0.0
        v[keep] = spsolve(G[keep][:, keep].tocsc(), inj[keep])
        loss_w = float(sum(v[node] * amps for node, amps in src_nodes))
        via_currents = []
        for via, nodes in zip(self.vias, via_nodes):
            k = len(nodes[via["layers"][0]])
            hops = [sum(v[na] - v[nb] for na, nb in zip(nodes[a], nodes[b])) / (r * k) for (a, b), r in
                    zip(zip(via["layers"], via["layers"][1:]), via["hop_ohm"])]
            via_currents.append({"xy": via["xy"], "hop_amps": hops,
                                 "amps": max(hops, key=abs) if hops else 0.0})
        dens = {}
        for name, G_ in grids.items():
            ids = G_["ids"]
            vv = np.where(ids >= 0, v[np.clip(ids, 0, None)], np.nan)
            gx, gy = np.gradient(vv, self.h * 1e-3)
            dens[name] = np.hypot(gx, gy) / self.rho * self.layers[name]["t"] / 1e3   # A per mm of width
        return {"r_ohm": loss_w / total ** 2 if total else float("nan"), "loss_w": loss_w,
                "source_volts": [float(v[node]) for node, _ in src_nodes],
                "unused_island_cells": unused_cells, "v": v, "via_currents": via_currents,
                "current_per_mm": dens,
                "dropped_edges": {k: G_["dropped_edges"] for k, G_ in grids.items()}}


# ------------------------------------------------------------------ self-test
def selftest() -> bool:
    ok = True
    # 1. One strip 10 mm x 50 mm, 70 um: R = rho L / (w t), injected/extracted
    #    through the full end edges.
    w, l, t = 10.0, 50.0, 70.0
    net = Net(pitch_mm=0.25)
    net.add_layer("F.Cu", [[(0, 0), (l, 0), (l, w), (0, w)]], t)
    ys = np.arange(0.125, w, 0.25)
    k = len(ys)
    r = net.solve([("F.Cu", 0.2, y, 1.0 / k) for y in ys], [("F.Cu", l - 0.2, y) for y in ys])["r_ohm"]
    expect = RHO_CU * (l - 0.25) * 1e-3 / (w * 1e-3 * t * 1e-6)
    err = abs(r - expect) / expect
    print(f"strip: R = {r*1e3:.4f} mohm, analytic {expect*1e3:.4f} mohm, error {err*100:.2f} %")
    ok &= err < 0.02
    # 2. Two identical stacked strips joined by a row of vias at each end:
    #    the parallel combination (near-zero barrel resistance here). Current
    #    enters and leaves through the barrels, so it also exercises the
    #    annulus contacts.
    net2 = Net(pitch_mm=0.25)
    for name in ("F.Cu", "In1.Cu"):
        net2.add_layer(name, [[(0, 0), (l, 0), (l, w), (0, w)]], t)
    for x in (0.125, l - 0.125):
        for y in ys:
            net2.add_via((x, y), drill_mm=0.1, plating_um=500, layers=("F.Cu", "In1.Cu"), length_mm=0.01,
                         filled=True)
    r2 = net2.solve([("F.Cu", 0.125, y, 1.0 / k) for y in ys], [("F.Cu", l - 0.125, y) for y in ys])["r_ohm"]
    expect2 = RHO_CU * (l - 0.25) * 1e-3 / (w * 1e-3 * t * 1e-6) / 2
    err2 = abs(r2 - expect2) / expect2
    print(f"two layers: R = {r2*1e3:.4f} mohm, analytic {expect2*1e3:.4f} mohm, error {err2*100:.2f} %")
    ok &= err2 < 0.03
    # 3. Four-layer via barrel (audit probe): full-length barrel F.Cu -> B.Cu.
    net3 = Net(pitch_mm=1.0)
    for name in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        net3.add_layer(name, [[(0, 0), (2, 0), (2, 2), (0, 2)]], 70 if name in ("F.Cu", "B.Cu") else 61)
    net3.add_via((0.5, 0.5), 0.8, 18, ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"), length_mm=1.6, filled=True)
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
    # 8. Two pads 0.2 mm apart (the BUS_P via pair case): a grid pitch larger
    #    than the gap puts cell centres on both sides; they must not connect.
    net8 = Net(pitch_mm=0.5)
    net8.add_layer("F.Cu", [[(0, 0), (5, 0), (5, 2), (0, 2)], [(5.2, 0), (10.2, 0), (10.2, 2), (5.2, 2)]], 70)
    try:
        net8.solve([("F.Cu", 1.0, 1.0, 1)], [("F.Cu", 9.0, 1.0)])
        refused8 = False
    except ValueError:
        refused8 = True
    print(f"0.2 mm gap does not conduct: {refused8} (dropped edges {net8._build()[0]['F.Cu']['dropped_edges']})")
    ok &= refused8
    # 9. An empty via drilled through a strip: no copper cell inside the drill,
    #    current goes around the hole (R rises, it is not shorted through the
    #    barrel), and a point inside the empty drill is refused. The same hole
    #    as a filled lead accepts a point inside the drill at its barrel.
    def strip_r(drill, filled=False, src=("F.Cu", 0.05, 1.0, 1)):
        n9 = Net(pitch_mm=0.1)
        n9.add_layer("F.Cu", [[(0, 0), (20, 0), (20, 2), (0, 2)]], 70)
        n9.add_layer("B.Cu", [[(9, 0), (11, 0), (11, 2), (9, 2)]], 70)
        if drill:
            n9.add_via((10, 1), drill, 18, ("F.Cu", "B.Cu"), filled=filled)
        return n9, n9.solve([src], [("F.Cu", 19.95, 1.0)])
    n9, res9 = strip_r(1.0)
    _, plain9 = strip_r(0)
    grid9 = n9._build()[0]["F.Cu"]
    i9 = int(np.argmin(abs(grid9["xs"] - 10))); j9 = int(np.argmin(abs(grid9["ys"] - 1)))
    void9 = grid9["ids"][i9, j9] < 0
    rise9 = res9["r_ohm"] > plain9["r_ohm"] * 1.01
    try:
        n9.solve([("F.Cu", 10.0, 1.0, 1)], [("F.Cu", 19.95, 1.0)])
        refused9 = False
    except ValueError:
        refused9 = True
    _, at9 = strip_r(1.0, filled=True, src=("B.Cu", 10.0, 1.0, 1))
    inj9 = math.isfinite(at9["r_ohm"]) and abs(abs(at9["via_currents"][0]["amps"]) - 1) < 1e-6
    print(f"drilled via: drill centre void {void9}, R {plain9['r_ohm']*1e3:.4f} -> {res9['r_ohm']*1e3:.4f} mohm, "
          f"point in empty drill refused {refused9}, filled lead carries injection {inj9}")
    ok &= void9 and rise9 and refused9 and inj9
    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    print(__doc__)
