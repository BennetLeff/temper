"""Validation of the axisymmetric solver (axi.py) against independent closed forms.

V1  Air-core R43 winding (21.93 turns, no ferrite): FEM L against a filament sum (Maxwell's coaxial-loop mutual
    inductance with elliptic integrals; each bundle split into 6 x 6 filaments, self term from the GMD of a square).
V2  One thin loop (a = 50 mm) 10 mm above a thick plate: FEM impedance change against the Dodd-Deeds half-space integral
    dZ = j w mu0 pi a^2 int J1(ka)^2 e^{-2kh} (mu_r k - lam)/(mu_r k + lam) dk, lam = sqrt(k^2 + j w mu0 mu_r sigma),
    for aluminium, 430 at mu 50/200/500 and cast iron, at 40 kHz.
V3  Mesh convergence on the production case (R43, homogenised bars, 430 pan mu 200, enclosure): refine 1.0 vs 0.6.
V4  Far-boundary check: domain 2 m vs 4 m.
Run: .venv/bin/python model/validate.py  -> model/results/validate.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy import integrate, special

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coil_geometry as G  # noqa: E402
import coil_model as CM  # noqa: E402
import materials as M  # noqa: E402
from axi import MU0, Model, make_grid  # noqa: E402

mm = 1e-3


def m_loops(a, b, d):
    k2 = 4 * a * b / ((a + b) ** 2 + d ** 2)
    k = math.sqrt(k2)
    K, E = special.ellipk(k2), special.ellipe(k2)
    return MU0 * math.sqrt(a * b) * ((2 / k - k) * K - 2 / k * E)


def filament_L_stranded(winding, n=6):
    side = G.D_BUNDLE * math.sqrt(math.pi) / 2 * mm
    rs, zs, ws = [], [], []
    for rc, w in winding.rings():
        for i in range(n):
            for j in range(n):
                rs.append(rc * mm + (i + 0.5 - n / 2) * side / n)
                zs.append(winding.z_c * mm + (j + 0.5 - n / 2) * side / n)
                ws.append(w)
    rs, zs, ws = map(np.array, (rs, zs, ws))
    N2 = n * n
    gmd = 0.44705 * side / n
    lam = 0.0
    for i in range(len(rs)):
        d = zs[i] - zs
        a, b = rs[i], rs
        k2 = np.minimum(4 * a * b / ((a + b) ** 2 + d ** 2), 1 - 1e-15)
        k = np.sqrt(k2)
        Mi = MU0 * np.sqrt(a * b) * ((2 / k - k) * special.ellipk(k2) - 2 / k * special.ellipe(k2))
        Mi[i] = MU0 * a * (math.log(8 * a / gmd) - 2.0)
        flux_i = float(np.sum(ws / N2 * Mi))       # flux at filament i per unit terminal current (filament j carries w_j I / n^2)
        lam += ws[i] * flux_i / N2                 # turn linkage = w_t x mean over its n^2 filaments
    return lam


def dodd_deeds_dZ(a, h, f, sigma, mu_r):
    w = 2 * math.pi * f

    def integrand(k, part):
        lam = np.sqrt(k * k + 1j * w * MU0 * mu_r * sigma)
        R = (mu_r * k - lam) / (mu_r * k + lam)
        v = special.j1(k * a) ** 2 * np.exp(-2 * k * h) * R
        return v.real if part == 0 else v.imag
    kmax = 60 / h
    re = integrate.quad(integrand, 0, kmax, args=(0,), limit=800)[0]
    im = integrate.quad(integrand, 0, kmax, args=(1,), limit=800)[0]
    dZ = 1j * w * MU0 * math.pi * a * a * (re + 1j * im)
    return dZ


def fem_loop(a, h, f, sigma, mu_r, plate_t=0.02, refine=1.0):
    z_plate = 0.100
    zl = z_plate - h
    d = M.skin_depth(sigma, mu_r, f)
    s = 0.4 * mm
    rr = [(0.0, 0.2, 1.0 * mm * refine), (a - 2 * mm, a + 2 * mm, 0.05 * mm * refine)]
    zz = [(zl - 2 * mm, zl + 2 * mm, 0.05 * mm * refine), (z_plate, z_plate + 4 * d, d / 6 * refine),
          (zl, z_plate, 0.5 * mm * refine)]
    r = make_grid(0.0, 3.0, rr, 0.08, 1.12, mandatory=[a - s / 2, a + s / 2])
    z = make_grid(-3.0, 3.0, zz, 0.08, 1.12, mandatory=[zl - s / 2, zl + s / 2, z_plate, z_plate + plate_t])
    out = []
    for with_plate in (False, True):
        m = Model(r, z)
        if with_plate:
            m.add_conductor("plate", 0.0, 1.0, z_plate, z_plate + plate_t, sigma, mu_r)
        m.add_turn(a, zl, s, 1.0)
        res = m.solve(f)
        out.append(complex(res["R"], 2 * math.pi * f * res["L"]))
    return out[1] - out[0], out[0]


def main():
    res = {}
    # ---- V1
    m = CM.build(G.R43, ferrite="air")
    L_fem = m.solve(40e3)["L"]
    L_fil = filament_L_stranded(G.R43, n=6)
    res["V1_air_core"] = dict(L_fem_uH=L_fem * 1e6, L_filament_uH=L_fil * 1e6, err_pct=(L_fem / L_fil - 1) * 100)
    print("V1", res["V1_air_core"], flush=True)
    # ---- V2
    rows = []
    for name, sig, mu in (("Al3003", M.SIGMA["Al3003"], 1.0), ("SS430 mu50", M.SIGMA["SS430"], 50.0),
                          ("SS430 mu200", M.SIGMA["SS430"], 200.0), ("SS430 mu500", M.SIGMA["SS430"], 500.0),
                          ("cast iron mu100", M.SIGMA["cast_iron"], 100.0)):
        a, h, f = 0.050, 0.010, 40e3
        dz_ref = dodd_deeds_dZ(a, h, f, sig, mu)
        dz_fem, z0 = fem_loop(a, h, f, sig, mu)
        rows.append(dict(case=name, dR_ref_ohm=dz_ref.real, dR_fem_ohm=dz_fem.real, dX_ref_ohm=dz_ref.imag,
                         dX_fem_ohm=dz_fem.imag, X0_ohm=z0.imag,
                         err_dR_pct=(dz_fem.real / dz_ref.real - 1) * 100, err_dX_pct=(dz_fem.imag / dz_ref.imag - 1) * 100))
        print("V2", {k: (round(v, 6) if isinstance(v, float) else v) for k, v in rows[-1].items()}, flush=True)
    res["V2_loop_over_halfspace"] = rows
    # ---- V3 / V4
    conv = {}
    for label, kw in (("refine_1.0", dict(refine=1.0)), ("refine_0.6", dict(refine=0.6)), ("rmax_4m", dict(refine=1.0, r_max=4.0))):
        out = {}
        for case, pan in (("free_bars", None), ("pan_ss430_mu200_installed", M.pan("ss430"))):
            mm_ = CM.build(G.R43, ferrite="bars", enclosure=pan is not None, pan=pan, **kw)
            r = mm_.solve(40e3)
            out[case] = dict(L_uH=r["L"] * 1e6, R_ohm=r["R"], nodes=len(mm_.r) * len(mm_.z))
        conv[label] = out
        print("V3/4", label, out, flush=True)
    a, b = conv["refine_1.0"], conv["refine_0.6"]
    conv["delta_pct"] = {c: dict(L=(b[c]["L_uH"] / a[c]["L_uH"] - 1) * 100, R=(b[c]["R_ohm"] / (a[c]["R_ohm"] or 1) - 1) * 100 if a[c]["R_ohm"] else 0.0)
                         for c in a}
    conv["delta_rmax_pct"] = {c: (conv["rmax_4m"][c]["L_uH"] / a[c]["L_uH"] - 1) * 100 for c in a}
    res["V3_V4_convergence"] = conv
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "validate.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(conv["delta_pct"]), conv["delta_rmax_pct"])


if __name__ == "__main__":
    main()
