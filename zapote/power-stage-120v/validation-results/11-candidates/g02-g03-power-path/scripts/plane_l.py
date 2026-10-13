#!/usr/bin/env python3
"""Plane-pair loop-inductance screen for the bus_p (In2) / hv_ret (In1) pair on the stage-19c copper.

Model: the two planes are 0.561 mm apart (centre to centre, stackup.json: 0.5 mm core + half of each 61 um
copper). Where both planes are present the return current mirrors the forward current, so the loop inductance
of a stretch of overlap is  L = mu0 * h * N_sq  with N_sq the number of squares of that overlap as seen by the
current (resistance of the overlap divided by sheet resistance, from a 5-point finite-difference solve).
Cells where only one plane exists are NOT counted as conducting (the mirrored-return assumption fails there),
so N_sq is a lower bound for the in-overlap part and a pinched overlap shows up as extra squares.
This is a screening estimate, +-50 %: it carries no pin/via loop, no cap ESL and ignores the outer-layer
pours. Anything below FEM accuracy is marked "needs the chain" (a P5-style FEM port, ALT-C5C6 section 7).

    python3 -I plane_l.py             # baseline 19c table
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import scipy.sparse as sp
import scipy.sparse.csgraph as csgraph
import scipy.sparse.linalg as spl
import shapely
from shapely.geometry import Point, box

from pp_common import MU0, DZ, load_copper, net_layer_geom

H_MM = DZ[("In1.Cu", "In2.Cu")]          # 0.561 mm
NH_PER_SQ = MU0 * H_MM * 1e-3 * 1e9      # nH per square


def overlap_mask(prims, window, pitch, bus_layer="In2.Cu", ret_layer="In1.Cu", bus="bus_p", ret="hv_ret"):
    x0, y0, x1, y1 = window
    nx, ny = int(round((x1 - x0) / pitch)), int(round((y1 - y0) / pitch))
    xs = x0 + (np.arange(nx) + 0.5) * pitch
    ys = y0 + (np.arange(ny) + 0.5) * pitch
    X, Y = np.meshgrid(xs, ys)
    gb = net_layer_geom(prims, bus, bus_layer)
    gr = net_layer_geom(prims, ret, ret_layer)
    mb = shapely.contains_xy(gb.buffer(0), X, Y)
    mr = shapely.contains_xy(gr.buffer(0), X, Y)
    return mb & mr, X, Y


def squares(mask, src, snk, bridge_pairs=()):
    """Equivalent squares between boolean cell sets src and snk through `mask` (unit-conductance 5-point FD)."""
    ny, nx = mask.shape
    ids = -np.ones(mask.shape, np.int64)
    ids[mask] = np.arange(int(mask.sum()))
    n = int(mask.sum())
    r, c = [], []
    a, b = ids[:, :-1], ids[:, 1:]
    ok = (a >= 0) & (b >= 0)
    r += [a[ok]]; c += [b[ok]]
    a, b = ids[:-1, :], ids[1:, :]
    ok = (a >= 0) & (b >= 0)
    r += [a[ok]]; c += [b[ok]]
    r = np.concatenate(r); c = np.concatenate(c)
    A = sp.coo_matrix((np.ones(len(r)), (r, c)), shape=(n, n))
    A = (A + A.T).tocsr()
    L = sp.diags(np.asarray(A.sum(axis=1)).ravel()) - A
    s = ids[src & mask]; t = ids[snk & mask]
    if len(s) == 0 or len(t) == 0:
        return float("nan")
    nc, lab = csgraph.connected_components(A, directed=False)
    good = np.isin(lab, np.unique(lab[t]))
    s = s[good[s]]
    if len(s) == 0:
        return float("inf")
    squares.last_connected = (len(s), int((src & mask).sum()))
    free = good.copy(); free[t] = False
    sel = np.where(free)[0]
    bvec = np.zeros(n); bvec[s] = 1.0 / len(s)
    v = np.zeros(n)
    v[sel] = spl.spsolve(L[sel][:, sel].tocsc(), bvec[sel])
    return float(v[s].mean())     # resistance in units of the square cell == squares (cells are square)


def region_sets(X, Y, spec):
    """spec: ('disk', cx, cy, r) | ('box', x0, y0, x1, y1)"""
    if spec[0] == "disk":
        return (X - spec[1]) ** 2 + (Y - spec[2]) ** 2 <= spec[3] ** 2
    return (X >= spec[1]) & (X <= spec[3]) & (Y >= spec[2]) & (Y <= spec[4])


FET_ROW = ("box", 55.0, 26.0, 62.0, 31.0)      # C38.1/C39.2 neighbourhood; the commutation-loop end of the trunk


def trunk_table(prims, pitch=0.5, window=(0, 0, 290, 190)):
    m, X, Y = overlap_mask(prims, window, pitch)
    out = {}
    # sources: the commutation-loop end (overlap cells around C38/C39 pins and the drain tongues' roots)
    src = region_sets(X, Y, ("box", 62.0, 8.0, 76.0, 24.0))   # FET-row side of the corridor (both planes overlap here in 19c)
    sinks = {
        "x=100 plane cut": ("box", 99.5, 27.0, 100.5, 50.0),
        "x=150 plane cut": ("box", 149.5, 27.0, 150.5, 50.0),
        "x=197 cut (y27-50)": ("box", 196.5, 27.0, 197.5, 50.0),
        "C5 pin zone (205,66-86)": ("box", 198.0, 60.0, 210.0, 90.0),
        "C6 pin zone (248,74-94)": ("box", 244.0, 70.0, 252.0, 97.0),
    }
    for k, sset in sinks.items():
        N = squares(m, src, region_sets(X, Y, sset))
        out[k] = {"squares": N, "L_nH": N * NH_PER_SQ if np.isfinite(N) else None}
    return out


if __name__ == "__main__":
    d = load_copper()
    print("nH per square at h=%.3f mm: %.3f" % (H_MM, NH_PER_SQ))
    for k, v in trunk_table(d["primitives"]).items():
        print("%-28s squares %8s   L %s nH" % (k, "%.2f" % v["squares"], "%.2f" % v["L_nH"] if v["L_nH"] is not None else "n/a"))
