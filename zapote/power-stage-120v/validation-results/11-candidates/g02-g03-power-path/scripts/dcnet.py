#!/usr/bin/env python3
"""Grid DC resistance solver for one net on the stage-19c copper dump (library + validation CLI).

Model (same assumptions as task 04's kit, README of 04-board-current-thermal/round5-native21):
 * 20 C copper, sheet R = rho/t per layer, square-cell finite differences (default pitch 0.25 mm);
 * plated barrels (vias and THT pads) join the layers on which the net has copper at that centre,
   vertical conduction through the plating only (default 18 um), solder fill ignored;
 * current is injected uniformly over the source terminal's cells, sink terminal equipotential.
It is a screening solver: validate it (CLI below) against task 04's J8->Q2 and R5.4->J10 numbers.

    python3 -I dcnet.py            # validation table
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spl
import scipy.sparse.csgraph as csgraph
import shapely
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from pp_common import (CU_T, DZ, LAYERS, RHO20, RESULTS, drill_d, fix, geom, load_copper, net_layer_geom,
                       pad_centre)


class NetGrid:
    def __init__(self, prims, net, window, pitch=0.25, plating_um=18.0, extra=None, skip_idx=()):
        """prims: list of dump primitives (may be an edited copy). extra: list of extra primitives."""
        self.net, self.pitch, self.window = net, pitch, window
        x0, y0, x1, y1 = window
        self.nx = int(round((x1 - x0) / pitch))
        self.ny = int(round((y1 - y0) / pitch))
        xs = x0 + (np.arange(self.nx) + 0.5) * pitch
        ys = y0 + (np.arange(self.ny) + 0.5) * pitch
        self.X, self.Y = np.meshgrid(xs, ys)            # shape (ny, nx)
        W = box(*window)
        plist = [p for i, p in enumerate(prims) if i not in skip_idx] + list(extra or [])
        self.prims = plist
        self.mask = {}
        for L in LAYERS:
            g = net_layer_geom(plist, net, L)
            if g.is_empty or not g.intersects(W):
                self.mask[L] = np.zeros((self.ny, self.nx), bool)
            else:
                self.mask[L] = shapely.contains_xy(g.intersection(W).buffer(0), self.X, self.Y)
        # barrels
        self.barrels = {}
        for p in plist:
            if p["net"] != net:
                continue
            if p["kind"] == "via":
                self.barrels.setdefault((round(p["centre"][0], 3), round(p["centre"][1], 3)), [p["drill_mm"], set()])[1].add(p["layer"])
            elif p["kind"] == "pad" and drill_d(p) > 0:
                c = tuple(round(v, 3) for v in p["centre"])
                self.barrels.setdefault(c, [drill_d(p), set()])[1].add(p["layer"])
        self.plating = plating_um * 1e-3
        # node numbering
        self.idx = {}
        n = 0
        for L in LAYERS:
            m = self.mask[L]
            ids = -np.ones(m.shape, np.int64)
            ids[m] = np.arange(n, n + int(m.sum()))
            n += int(m.sum())
            self.idx[L] = ids
        self.n = n

    def cell_of(self, xy):
        x0, y0, _, _ = self.window
        i = int((xy[0] - x0) / self.pitch)
        j = int((xy[1] - y0) / self.pitch)
        return j, i

    def laplacian(self):
        rows, cols, vals = [], [], []
        for L in LAYERS:
            rs = RHO20 * 1e3 / CU_T[L]            # ohm/sq : rho[ohm m]*1e3 [mm/m]/t[mm]
            g = 1.0 / rs
            ids = self.idx[L]
            a = ids[:, :-1]; b = ids[:, 1:]
            ok = (a >= 0) & (b >= 0)
            rows += [a[ok], b[ok]]; cols += [b[ok], a[ok]]; vals += [np.full(ok.sum(), g)] * 2
            a = ids[:-1, :]; b = ids[1:, :]
            ok = (a >= 0) & (b >= 0)
            rows += [a[ok], b[ok]]; cols += [b[ok], a[ok]]; vals += [np.full(ok.sum(), g)] * 2
        x0, y0, x1, y1 = self.window
        for c, (d, lays) in self.barrels.items():
            if not (x0 <= c[0] < x1 and y0 <= c[1] < y1):
                continue
            ring = math.pi * ((d / 2 + self.plating) ** 2 - (d / 2) ** 2)      # mm^2
            j, i = self.cell_of(c)
            present = [L for L in LAYERS if L in lays]
            for La, Lb in zip(LAYERS[:-1], LAYERS[1:]):
                pass
            # connect consecutive present layers through the intermediate span
            for ia in range(len(present) - 1):
                La, Lb = present[ia], present[ia + 1]
                span = 0.0
                k0, k1 = LAYERS.index(La), LAYERS.index(Lb)
                for k in range(k0, k1):
                    span += DZ[(LAYERS[k], LAYERS[k + 1])]
                r = RHO20 * 1e3 * span / ring                                       # ohm
                na = self._near(La, j, i); nb = self._near(Lb, j, i)
                if na is None or nb is None:
                    continue
                g = 1.0 / r
                rows += [np.array([na, nb])]; cols += [np.array([nb, na])]; vals += [np.array([g, g])]
        r = np.concatenate(rows); c_ = np.concatenate(cols); v = np.concatenate(vals)
        A = sp.coo_matrix((v, (r, c_)), shape=(self.n, self.n)).tocsr()
        d = np.asarray(A.sum(axis=1)).ravel()
        return sp.diags(d) - A

    def _near(self, L, j, i, rad=3):
        ids = self.idx[L]
        best = None
        for dj in range(-rad, rad + 1):
            for di in range(-rad, rad + 1):
                jj, ii = j + dj, i + di
                if 0 <= jj < self.ny and 0 <= ii < self.nx and ids[jj, ii] >= 0:
                    dd = dj * dj + di * di
                    if best is None or dd < best[0]:
                        best = (dd, ids[jj, ii])
        return None if best is None else int(best[1])

    def pad_nodes(self, ref):
        out = []
        W = box(*self.window)
        for p in self.prims:
            if p["kind"] == "pad" and p.get("ref") == ref and p["net"] == self.net:
                g = fix(Polygon(p["shell"], p.get("holes") or []))
                if not g.intersects(W):
                    continue
                m = shapely.contains_xy(g.buffer(0.01), self.X, self.Y) & self.mask[p["layer"]]
                out += list(self.idx[p["layer"]][m])
        return sorted(set(int(v) for v in out))

    def resistance(self, src_refs, snk_refs, amps=1.0, lap=None):
        """Resistance (ohm) from source pads (uniform injection) to sink pads (grounded)."""
        L = lap if lap is not None else self.laplacian()
        src = sorted(set(n for r in src_refs for n in self.pad_nodes(r)))
        snk = sorted(set(n for r in snk_refs for n in self.pad_nodes(r)))
        if not src or not snk:
            raise RuntimeError("terminal not found: %s %s" % (src_refs, snk_refs))
        # keep only the connected component(s) that contain a sink; report sources that are cut off
        ncomp, lab = csgraph.connected_components(sp.csr_matrix(L != 0), directed=False)
        good = np.isin(lab, np.unique(lab[snk]))
        lost = [n for n in src if not good[n]]
        if lost:
            raise RuntimeError("%d of %d source nodes are not connected to the sink" % (len(lost), len(src)))
        b = np.zeros(self.n)
        b[src] = amps / len(src)
        free = good.copy()
        free[snk] = False
        sel = np.where(free)[0]
        Lk = L[sel][:, sel].tocsc()
        v = np.zeros(self.n)
        v[sel] = spl.spsolve(Lk, b[sel])
        self.v = v
        self.src, self.snk = src, snk
        r = float(np.sum(v[src]) / len(src)) / amps
        return r

    def layer_current_density(self, amps):
        """Max |J| (A/mm) per layer from the last solve, scaled to `amps` through the terminals."""
        out = {}
        for L in LAYERS:
            ids = self.idx[L]
            rs = RHO20 * 1e3 / CU_T[L]
            best = (0.0, None)
            v = np.where(ids >= 0, self.v[np.maximum(ids, 0)], np.nan)
            for axis in (1, 0):
                a = v[:, :-1] if axis == 1 else v[:-1, :]
                b = v[:, 1:] if axis == 1 else v[1:, :]
                i_edge = np.abs(a - b) / rs                      # amps through one cell edge (width = pitch)
                dens = i_edge / self.pitch * amps
                dens = np.nan_to_num(dens)
                k = np.unravel_index(np.argmax(dens), dens.shape)
                if dens[k] > best[0]:
                    best = (float(dens[k]), (self.window[0] + (k[1] + 0.5) * self.pitch, self.window[1] + (k[0] + 0.5) * self.pitch))
            out[L] = best
        return out

    def loss(self, amps):
        """I^2 R dissipated in the sheets and barrels for the last solve (W)."""
        L = self.laplacian()
        return float(self.v @ (L @ self.v)) * amps ** 2


def validate():
    d = load_copper()
    P = d["primitives"]
    rows = []
    cases = [("bus_p", "J8.1", "Q2.2", (0, 0, 150, 60), 3.626, "task04 bus-dc-q2 p025 (0.25 mm)"),
             ("bus_p", "J8.1", "Q5.2", (0, 0, 150, 60), 5.647 * 1.0, "task04 bus_dc_q5 p0125"),
             ("hv_ret", "R5.4", "J10.1", (0, 0, 200, 60), 6.373, "task04 hv_dc p00625")]
    for net, a, b, win, ref, note in cases:
        g = NetGrid(P, net, win, pitch=0.25)
        r = g.resistance([a], [b]) * 1e3
        rows.append((net, a, b, r, ref, 100 * (r - ref) / ref, note))
    print("net      src      snk     mine mOhm  task04 mOhm   diff %   note")
    for r in rows:
        print("%-8s %-8s %-7s %9.3f  %11.3f  %7.1f   %s" % r)
    return rows


if __name__ == "__main__":
    validate()
