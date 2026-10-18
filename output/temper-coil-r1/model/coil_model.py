"""Build the coil-r1 axisymmetric model: winding (discrete turns), ferrite, enclosure, pan.

Units: inputs in mm (coil_geometry) are converted to metres here. Materials are in materials.py.
"""
from __future__ import annotations

import math

import numpy as np

import coil_geometry as G
import materials as M
from axi import Model, make_grid

mm = 1e-3


def bar_fill(r_m, n=G.N_BARS, w_mm=G.BAR_W):
    """Angular fill of n constant-width radial bars at radius r."""
    return np.minimum(1.0, n * w_mm * mm / (2 * np.pi * np.maximum(r_m, 1e-9)))


def grid(winding: G.Winding, pan=None, refine=1.0, r_max=2.0, z_span=2.0):
    s = G.D_BUNDLE * math.sqrt(math.pi) / 2           # square of equal area to the round bundle
    rings = winding.rings()
    mand_r = [x for rc, _ in rings for x in ((rc - s / 2) * mm, (rc + s / 2) * mm)]
    mand_r += [G.BAR_R[0] * mm, G.BAR_R[1] * mm] + [x * mm for sec in winding.sections for x in (sec.r0, sec.r1)]
    zc = winding.z_c
    mand_z = [(zc - s / 2) * mm, (zc + s / 2) * mm, G.Z_BAR[0] * mm, G.Z_BAR[1] * mm, G.GLASS[0] * mm]
    h = refine
    rr = [(0.0, 0.024, 1.0 * mm * h), (0.024, 0.122, 0.2 * mm * h), (0.122, 0.150, 0.6 * mm * h),
          (0.150, 0.225, 1.0 * mm * h), (0.1575, 0.1590, 0.12 * mm * h), (0.1705, 0.1720, 0.12 * mm * h)]
    zz = [(0.0089, 0.0111, 0.12 * mm * h), (0.0925, 0.0985, 0.25 * mm * h), (0.0985, 0.1020, 0.1 * mm * h),
          (0.1020, 0.1100, 0.4 * mm * h), (0.1015, 0.1055, 0.15 * mm * h), (0.1048, 0.1095, 0.25 * mm * h)]
    if pan is not None:
        z0 = G.PAN_Z0 * mm
        mand_r.append(pan["radius_mm"] * mm)
        rr.append(((pan["radius_mm"] - 6) * mm, (pan["radius_mm"] + 6) * mm, 0.4 * mm * h))
        for t_mm, sig, mu, _nl in pan["layers"]:
            t = t_mm * mm
            mand_z += [z0, z0 + t]
            d = M.skin_depth(sig, mu, pan.get("f_grid", 40e3)) if sig > 0 else 1.0
            hz = min(d / 5, 0.1 * mm) * h
            zz.append((z0, z0 + min(t, 4 * d), hz))                 # field enters from below
            zz.append((max(z0, z0 + t - min(t, 2 * d)), z0 + t, min(d / 2.5, 0.2 * mm) * h))
            z0 += t
    r = make_grid(0.0, r_max, rr, 0.08, 1.12, mandatory=mand_r)
    z = make_grid(-z_span, z_span, zz, 0.08, 1.12, mandatory=mand_z)
    return r, z


def build(winding: G.Winding = G.R43, ferrite="bars", mu_ferrite=M.FERRITE_MU, enclosure=False, pan=None, refine=1.0,
          bar_n=G.N_BARS, bar_w=G.BAR_W, bar_r=G.BAR_R, z_bar=G.Z_BAR, r_max=2.0, turn_model="discrete"):
    """pan: dict(name, radius_mm, layers=[(thickness_mm, sigma, mu_r, mu_of_H or None), ...] bottom-up)."""
    r, z = grid(winding, pan, refine, r_max=r_max)
    m = Model(r, z)
    if ferrite != "air":
        fm = m.box(bar_r[0] * mm, bar_r[1] * mm, z_bar[0] * mm, z_bar[1] * mm)
        if ferrite == "plate":
            m.set_mu(fm, mu_ferrite)
        else:
            p = bar_fill(m.RC, bar_n, bar_w)
            mu = 1 + p * (mu_ferrite - 1)
            m.set_mu(fm, mu)
    if enclosure:
        for name, part in (("base", G.BASE), ("seat_ring", G.SEAT_RING), ("fence_ring", G.FENCE_RING)):
            m.add_conductor(name, part["r"][0] * mm, part["r"][1] * mm, part["z"][0] * mm, part["z"][1] * mm, M.SIGMA["Al5052"])
    if pan is not None:
        z0 = G.PAN_Z0 * mm
        for i, (t_mm, sig, mu, nl) in enumerate(pan["layers"]):
            m.add_conductor(f"pan{i}", 0.0, pan["radius_mm"] * mm, z0, z0 + t_mm * mm, sig, mu, nl)
            z0 += t_mm * mm
    side = G.D_BUNDLE * math.sqrt(math.pi) / 2 * mm
    if turn_model == "smeared":       # each section a uniform annulus (the 3D cross-check uses the same source)
        for s in winding.sections:
            m.add_turn((s.r0 + s.r1) / 2 * mm, winding.z_c * mm, side, s.turns, width=(s.r1 - s.r0) * mm)
    else:
        for rc, w in winding.rings():
            m.add_turn(rc * mm, winding.z_c * mm, side, w)
    m.winding = winding
    return m


def pan_regions(m):
    return [rid for rid, n in m.region_names.items() if n.startswith("pan")]


def pan_profile(m, bins_mm=(0, 20, 40, 55, 70, 84, 92, 100, 110, 120, 130)):
    """Pan eddy power per radial band (W) for the solved current, and the share per band."""
    dP = m.loss_density()
    mask = np.isin(m.region, pan_regions(m))
    rc = m.RC[mask] / mm
    p = dP[mask]
    out = []
    for a, b in zip(bins_mm, bins_mm[1:]):
        sel = (rc >= a) & (rc < b)
        P = float(p[sel].sum())
        out.append(dict(r_mm=[a, b], W=P, W_per_cm2=P / (math.pi * (b * b - a * a) / 100.0)))
    tot = sum(x["W"] for x in out) or 1.0
    for x in out:
        x["share"] = x["W"] / tot
    return out
