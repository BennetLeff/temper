#!/usr/bin/env python3
"""Round 5: coupling of candidate coil geometries to pans of 160-260 mm, by axisymmetric FEM.

ASSUMED / COMPARATIVE. The solver is the R32 study-06 eddy-current FEM (fem_axi.py, copied
byte for byte; see README). The pan is a LINEAR steel disc (mu_r is a fit parameter, not a
property; R32 study 06 found no single mu reproduces both round-4 priors), so absolute kl and r
are not used. Only RATIOS between geometries are carried into the tank grid:

    f_k(g, D) = (1 - kl[g, D]) / (1 - kl[basis, D_ref])     (inductance drop)
    f_r(g, D) =  r[g, D]       /  r[basis, D_ref]           (reflected R per uH of L0)

kl = L_pan/L0 and r = R_pan/L0 (ohm/uH), both against the INSTALLED no-pan L0 (base plate and
roof ring present, as R32's 66.34 uH). A ratio is turn-independent for a fixed geometry
(everything scales as N^2), so each geometry is solved at 1 turn and scaled.

Geometries (winding radii in mm; Z 98.5-102.5; ferrite 8 radial bars, mu 2000, Z 93.5-97.5,
from 3 mm inside the winding to 2 mm outside it; R32 stack: glass Z 106-110, pan Z 110-112):
  basis_d180  continuous r 22-90  (round-4 anchors: Infineon kit, [PAS] 180 mm/19 t, MDPI 180 mm)
  basis_d170, basis_d200          basis-diameter sensitivity
  d210_2sec   inner r 26-63 (9 t) + outer r 75-106 (8 t), series  (Control Freak, coil-estimate.json)
              -- ruled out by coil cooling (enclosure R33 study 09); kept for one comparison row
  d228_2sec   inner r 26-68 + outer r 76-114, series, uniform turn density (42:38 turn share);
              the R34 candidate (R33 study 09, "R34: Ø228 two-section r26-68 / gap / r76-114, 8 x 20")
  d240_cont   continuous r 22-116 (the R32 study-06 winding)

Writes outputs/coupling.json and outputs/coupling.csv.
Run: python3 scripts/coupling.py   (numpy, scipy; ~3-6 min)
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs"
sys.path.insert(0, str(HERE))
from fem_axi import MU0, Model, make_grid  # noqa: E402

mm = 1e-3
F = 40e3
SIG_AL5052 = 1 / 4.99e-8
SIG_STEEL = 1 / 6.0e-7
MU_FERRITE = 2000.0
MU_PANS = (30.0, 100.0, 300.0, 1000.0)
MU_CENTRAL = 100.0
PAN_D_MM = (160, 180, 200, 220, 240, 260)
REF = ("basis_d180", 200)

GEOMS = {
    "basis_d170": [(22, 85, 1.0)],
    "basis_d180": [(22, 90, 1.0)],
    "basis_d200": [(22, 100, 1.0)],
    "d210_2sec": [(26, 63, 9 / 17), (75, 106, 8 / 17)],
    "d228_2sec": [(26, 68, 42 / 80), (76, 114, 38 / 80)],
    "d240_cont": [(22, 116, 1.0)],
}


def grid():
    rr = [(0.0, 0.025, 0.5 * mm), (0.018, 0.135, 0.8 * mm), (0.155, 0.225, 2.0 * mm)]
    rr += [(d / 2000 - 0.002, d / 2000 + 0.002, 0.25 * mm) for d in PAN_D_MM]
    zz = [(0.0075, 0.0115, 0.1 * mm), (0.088, 0.106, 0.5 * mm), (0.1015, 0.1055, 0.12 * mm),
          (0.1098, 0.1106, 0.035 * mm), (0.1106, 0.1122, 0.15 * mm), (0.011, 0.105, 4 * mm)]
    return make_grid(0.0, 4.0, rr, 0.08, 1.12), make_grid(-4.0, 4.0, zz, 0.08, 1.12)


R_GRID, Z_GRID = grid()


class MultiCoil(Model):
    """Series sections carrying the same current; section turn shares n_i (sum 1 at 1 turn)."""

    def set_sections(self, secs, current=1.0):
        self.secs = []
        for r0, r1, share in secs:
            m = self.box(r0 * mm, r1 * mm, 0.0985, 0.1025)
            area = (r1 - r0) * mm * 0.004
            self.J[m] = share * current / area
            self.secs.append((m, share, area))
        self.coil_mask = np.zeros_like(self.J, dtype=bool)
        for m, _, _ in self.secs:
            self.coil_mask |= m
        self.turns, self.current, self.coil_area = 1.0, current, 1.0

    def post(self):
        res = super().post()  # losses; L/R recomputed below for multiple sections
        psi = self.psi
        psic = 0.25 * (psi[:-1, :-1] + psi[1:, :-1] + psi[:-1, 1:] + psi[1:, 1:])
        area = np.diff(self.r)[:, None] * np.diff(self.z)[None, :]
        lam = sum(share / a * np.sum(2 * np.pi * psic[m] * area[m]) for m, share, a in self.secs)
        Z = 1j * self.w * lam / self.current
        self.L, self.R = float(Z.imag / self.w), float(Z.real)
        res.update(L=self.L, R=self.R)
        return res


def build(geom, enclosure=True, pan_d_mm=None, mu_pan=100.0):
    secs = GEOMS[geom]
    m = MultiCoil(R_GRID, Z_GRID)
    r_in, r_out = secs[0][0] - 3, secs[-1][1] + 2
    fm = m.box(r_in * mm, r_out * mm, 0.0935, 0.0975)
    p = np.minimum(1.0, 8 * 0.020 / (2 * np.pi * m.RC))
    m.mur[fm] = (1 + p * (MU_FERRITE - 1))[fm]
    if enclosure:  # R32 installed condition (study-06 calibrate_pan.py parts)
        m.add_conductor("base", 0.0, 0.221, 0.008, 0.011, SIG_AL5052)
        m.add_conductor("roof_ring", 0.158, 0.221, 0.102, 0.105, SIG_AL5052)
    if pan_d_mm:
        m.add_conductor("pan", 0.0, pan_d_mm / 2000, 0.110, 0.112, SIG_STEEL, mu_pan)
    m.set_sections(secs)
    return m


def main():
    OUT.mkdir(exist_ok=True)
    res = {"status": "ASSUMED/COMPARATIVE: linear-mu FEM; only ratios between geometries are used",
           "f_Hz": F, "mu_pans": MU_PANS, "mu_central": MU_CENTRAL, "ref": REF, "geoms": {}}
    rows = []
    for g in GEOMS:
        L1_free = build(g, enclosure=False).solve(F)["L"]
        L1_inst = build(g, enclosure=True).solve(F)["L"]
        N70 = math.sqrt(70e-6 / L1_free)
        gi = {"sections_mm": GEOMS[g], "L_per_turn2_free_uH": L1_free * 1e6,
              "L_per_turn2_installed_uH": L1_inst * 1e6, "installed_over_free": L1_inst / L1_free,
              "turns_for_70uH_free": N70, "turns_for_66.34uH_installed": math.sqrt(66.34e-6 / L1_inst),
              "pans": {}}
        for D in PAN_D_MM:
            for mu in MU_PANS:
                s = build(g, True, D, mu).solve(F)
                kl = s["L"] / L1_inst
                r = s["R"] / (L1_inst * 1e6)  # ohm per uH of installed L0 (coil R excluded: Litz sigma=0)
                gi["pans"][f"{D}_{int(mu)}"] = {"kl": kl, "r_ohm_per_uH": r}
                rows.append({"geom": g, "pan_d_mm": D, "mu_pan": mu, "kl": round(kl, 4),
                             "one_minus_kl": round(1 - kl, 4), "r_ohm_per_uH": round(r, 5)})
                print(g, D, mu, round(kl, 4), round(r, 5), flush=True)
        res["geoms"][g] = gi
    # ratios against the reference (basis_d180 on a 200 mm pan), per mu
    for row in rows:
        ref = res["geoms"][REF[0]]["pans"][f"{REF[1]}_{int(row['mu_pan'])}"]
        row["f_k"] = round(row["one_minus_kl"] / (1 - ref["kl"]), 4)
        row["f_r"] = round(row["r_ohm_per_uH"] / ref["r_ohm_per_uH"], 4)
    res["rows"] = rows
    (OUT / "coupling.json").write_text(json.dumps(res, indent=1) + "\n")
    with open(OUT / "coupling.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for g, gi in res["geoms"].items():
        print(g, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in gi.items() if k != "pans"})


if __name__ == "__main__":
    main()
