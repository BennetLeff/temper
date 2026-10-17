#!/usr/bin/env python3
"""Partial-inductance screen of the bulk path (FET-row film caps C38-C41 <-> bulk cap C5) on the 19c copper.

Method: solve the DC current field of bus_p (1 A from C5.1/C5.2 pads to the C38-C41 bus_p pins) and of hv_ret
(1 A from the C38-C41 hv_ret pins to the C5.3/C5.4 pads) with the grid solver (dcnet.NetGrid, 0.5 mm), turn the
edge currents (lateral edges in every layer, plus the plated barrels as vertical filaments) into current-moment
blocks (2.5 mm cells, per layer), and sum the Neumann interaction
        L = (mu0/4pi) * sum_ab (m_a . m_b) / r_ab         (a != b, r softened by half a block)
            + (mu0/2pi) * sum_a |m_a|^2 / l * (ln(2 l / rho) - 1)   (self term of a straight bar of length l)
for the combined loop (bus_p forward, hv_ret return).  The DC distribution is NOT the high-frequency one: at
tens of MHz the current crowds toward the opposite plane and L falls, so this is an UPPER-BOUND-type screen whose
useful output is the CHANGE between layouts, not an absolute nH.  Both numbers (this and plane_l.py's mirror-image
lower bound) are screening estimates, +-50 %; the chain's FEM port is the arbiter (ALT-C5C6 section 7).
Control: a straight bus_p/hv_ret strip pair of known geometry (cap_control) must come out within 25 % of
mu0*h*l/w.

    python3 -I bulk_path_l.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from dcnet import NetGrid
from pp_common import CU_T, DZ, LAYERS, MU0, RHO20, load_copper

BLK = 2.5          # mm, moment-block size
WINDOW = (0.0, 0.0, 250.0, 115.0)
PITCH = 0.5
ROW_BUS = ["C38.1", "C39.1", "C40.1", "C41.1"]
ROW_RET = ["C38.2", "C39.2", "C40.2", "C41.2"]


def moments(g, amps=1.0):
    """Current-moment blocks (x, y, z, mx, my, mz) in mm / A*mm from a solved NetGrid."""
    xs, ys, zs, mx, my, mz = [], [], [], [], [], []
    zc = {"F.Cu": 0.035, "In1.Cu": 0.536, "In2.Cu": 1.097, "B.Cu": 1.598}
    x0, y0, _, _ = g.window
    p = g.pitch
    for L in LAYERS:
        ids = g.idx[L]
        rs = RHO20 * 1e3 / CU_T[L]
        v = np.where(ids >= 0, g.v[np.maximum(ids, 0)], np.nan)
        # x-edges
        dv = v[:, :-1] - v[:, 1:]
        ok = np.isfinite(dv)
        I = np.where(ok, dv / rs, 0.0) * amps
        jj, ii = np.nonzero(ok & (np.abs(I) > 1e-9))
        xs += list(x0 + (ii + 1.0) * p); ys += list(y0 + (jj + 0.5) * p); zs += [zc[L]] * len(ii)
        mx += list(I[jj, ii] * p); my += [0.0] * len(ii); mz += [0.0] * len(ii)
        dv = v[:-1, :] - v[1:, :]
        ok = np.isfinite(dv)
        I = np.where(ok, dv / rs, 0.0) * amps
        jj, ii = np.nonzero(ok & (np.abs(I) > 1e-9))
        xs += list(x0 + (ii + 0.5) * p); ys += list(y0 + (jj + 1.0) * p); zs += [zc[L]] * len(ii)
        mx += [0.0] * len(ii); my += list(I[jj, ii] * p); mz += [0.0] * len(ii)
    # vertical barrel filaments
    import math as _m
    for c, (d, lays) in g.barrels.items():
        if not (x0 <= c[0] < g.window[2] and y0 <= c[1] < g.window[3]):
            continue
        present = [L for L in LAYERS if L in lays]
        ring = _m.pi * ((d / 2 + g.plating) ** 2 - (d / 2) ** 2)
        j, i = g.cell_of(c)
        for La, Lb in zip(present[:-1], present[1:]):
            span = zc[Lb] - zc[La]
            na, nb = g._near(La, j, i), g._near(Lb, j, i)
            if na is None or nb is None:
                continue
            r = RHO20 * 1e3 * span / ring
            I = (g.v[na] - g.v[nb]) / r * amps
            xs.append(c[0]); ys.append(c[1]); zs.append((zc[La] + zc[Lb]) / 2)
            mx.append(0.0); my.append(0.0); mz.append(I * span)
    return [np.array(a, float) for a in (xs, ys, zs, mx, my, mz)]


def blockify(m):
    x, y, z, mx, my, mz = m
    key = (np.floor(x / BLK).astype(np.int64), np.floor(y / BLK).astype(np.int64), np.round(z / 0.4).astype(np.int64))
    kk = np.stack(key, 1)
    uniq, inv = np.unique(kk, axis=0, return_inverse=True)
    n = len(uniq)
    out = np.zeros((n, 6))
    for k, a in enumerate((x, y, z, mx, my, mz)):
        if k < 3:
            out[:, k] = np.bincount(inv, weights=np.abs(mx) + np.abs(my) + np.abs(mz) + 1e-30, minlength=n)
            out[:, k] = np.bincount(inv, weights=a * (np.abs(mx) + np.abs(my) + np.abs(mz) + 1e-30), minlength=n) / out[:, k]
        else:
            out[:, k] = np.bincount(inv, weights=a, minlength=n)
    return out


def inductance(blocks):
    P = blocks[:, :3]
    M = blocks[:, 3:]
    mag2 = (M ** 2).sum(1)
    keep = mag2 > 1e-14
    P, M, mag2 = P[keep], M[keep], mag2[keep]
    n = len(P)
    nh = 1e9
    mu = MU0 * 1e-3 * nh                         # mu0 in nH/mm
    rho = 0.2235 * (BLK + 0.07)
    Lself = (mu / (2 * math.pi)) * np.sum(mag2 / BLK * (math.log(2 * BLK / rho) - 1.0))
    eps2 = (0.5 * BLK) ** 2
    Lmut = 0.0
    CH = 2000
    for a in range(0, n, CH):
        d = P[a:a + CH, None, :] - P[None, :, :]
        r = np.sqrt((d ** 2).sum(-1) + eps2)
        dot = M[a:a + CH] @ M.T
        s = dot / r
        # exclude self
        idx = np.arange(a, min(a + CH, n))
        s[idx - a, idx] = 0.0
        Lmut += s.sum()
    Lmut *= mu / (4 * math.pi)
    return Lself + Lmut, n


def bulk_L(prims, bulk="C5", window=WINDOW, pitch=PITCH):
    src_b = [bulk + ".1", bulk + ".2"]
    snk_r = [bulk + ".3", bulk + ".4"]
    if bulk == "C6":
        window = (0.0, 0.0, 292.0, 115.0)
    gb = NetGrid(prims, "bus_p", window, pitch=pitch)
    Rb = gb.resistance(src_b, ROW_BUS)
    mb = moments(gb)
    gr = NetGrid(prims, "hv_ret", window, pitch=pitch)
    Rr = gr.resistance(ROW_RET, snk_r)
    mr = moments(gr)
    allm = [np.concatenate([a, b]) for a, b in zip(mb, mr)]
    L, n = inductance(blockify(allm))
    return {"L_nH": L, "blocks": n, "R_bus_mOhm": Rb * 1e3, "R_ret_mOhm": Rr * 1e3}


if __name__ == "__main__":
    d = load_copper()
    r = bulk_L(d["primitives"], "C5")
    print("19c bulk path to C5 (partial-inductance screen):", {k: round(v, 3) for k, v in r.items()})


def cap_control(w=20.0, ell=100.0):
    """Straight strip pair: bus_p on In2 over hv_ret on In1, ends shorted by a copper pad each end (no vias).
    Expected plane-pair L = mu0 * h * ell / w (+ end effects)."""
    def rect(x0, y0, x1, y1):
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    prims = []
    for net, lay in (("bus_p", "In2.Cu"), ("hv_ret", "In1.Cu")):
        prims.append({"kind": "zone", "net": net, "layer": lay, "shell": rect(0, 0, ell, w), "holes": []})
    # terminals are full-width end pads (current spreads evenly: the 1-D case)
    for net, lay, ref, x0, x1 in (("bus_p", "In2.Cu", "S.1", 0.0, 1.0), ("bus_p", "In2.Cu", "K.1", ell - 1.0, ell),
                                  ("hv_ret", "In1.Cu", "S.2", 0.0, 1.0), ("hv_ret", "In1.Cu", "K.2", ell - 1.0, ell)):
        prims.append({"kind": "pad", "net": net, "layer": lay, "ref": ref, "shell": rect(x0, 0, x1, w), "holes": [], "centre": [x0, w / 2], "drill_mm": 0})
    win = (-2.0, -2.0, ell + 2.0, w + 2.0)
    gb = NetGrid(prims, "bus_p", win, pitch=0.5)
    gb.resistance(["S.1"], ["K.1"])
    mb = moments(gb)
    gr = NetGrid(prims, "hv_ret", win, pitch=0.5)
    gr.resistance(["K.2"], ["S.2"])
    mr = moments(gr)
    allm = [np.concatenate([a, b]) for a, b in zip(mb, mr)]
    L, n = inductance(blockify(allm))
    h = DZ[("In1.Cu", "In2.Cu")]
    L_exp = MU0 * h * 1e-3 * ell / w * 1e9
    return L, L_exp
