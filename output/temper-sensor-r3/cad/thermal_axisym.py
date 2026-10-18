"""G8: steady temperatures of the C1 cartridge under a 260 C pan (2-D axisymmetric finite-volume conduction).

Geometry: the CAD sections from cartridge_r3.profiles(travel) at the working position (travel 0.60: a pan holds the
disc flush with the glass top, Z110). Rasterised on an (r, z) grid r 0-26, Z74-110 (0.05 mm cells round the axis).

Boundary conditions and inputs (study 08, output/temper-r33-studies/08-undrilled-glass-sensor/undrilled_thermal.py
PARAMS, unless stated):
- pan base T_PAN = 260 C over the whole domain top (G8 premise).
- pan -> glass top: h_i = k_air(T)/(gap + delta0) + 4 sigma eps T^3, delta0 = 20 um (flat pan) or gap 0.5 mm (warped).
- pan -> disc: dry contact h_c from ../contact-model.json (sensor-r3 disc): 888 (worst, as-cast iron, 2 mrad) and
  12991 (enamel, 0 mrad), plus 21946 (polished clad) for the hottest disc.
- glass k 1.6 W/mK (SCHOTT CERAN, via study 08).
- coil eye below the glass, outside the cartridge: well-mixed eye air (R32 coil-air jets) at T_air with h_eye 10 W/m2K
  on every exposed solid face (study 08 h_eye); eye states from study 02 via study 08 env: full_22A (winding 147.9,
  air 130.0) and fry_hold_12.7A (159.8, 139.7).
- winding/former zone r >= 22, Z93-101.6 held at T_winding; the stagnant gap above it (Z101.6-106) is air + radiation.
- enclosed air (bore, sump, gland): k 0.038 + linearised radiation over ~1 mm gaps (4 sigma 0.8 T^3 x 1 mm) = 0.058.
- materials: Si3N4 85, IST chip (alumina) 25, bond 1.7 (EPO-TEK 930-4 TDS), Vespel SP-1 0.35 (DuPont sheet), PEEK 450G
  0.29 (Victrex TDS), FFKM 0.20 (ASSUMPTION, typical perfluoroelastomer), fibre 0.04 (budget value; 0.08 sensitivity),
  potting 4.3 (Duralco 128, 30 BTU in/ft2 h F), G11 carrier 0.30, 6-core cable as 23 W/mK (Cu fraction ~6 %),
  spring envelope 0.06 (A-286 wire fraction along the helix + air); the three 0.6 mm guide pads as an equivalent ring
  (7 % polyimide, 93 % air).
Outputs per part: max and mean temperature over every case, and the disc's heat outflow split.
Run: python thermal_axisym.py -> thermal-axisym.json
"""
from __future__ import annotations

import json
import sys
from math import pi
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import shapely
from shapely.geometry import Polygon

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cartridge_r3 as C  # noqa: E402

SIG = 5.670e-8
T_PAN = 260.0
K = dict(silica=1.38, padring=0.07 * 0.35 + 0.93 * 0.058, si3n4=85.0, alumina=25.0, bond=1.7, pi=0.35, peek=0.29, ffkm=0.20, fibre=0.04, potting=4.3, glass=1.6,
         g11=0.30, cable=23.0, spring=0.06, cav=0.058, gap=0.13)
EYE = {"full_22A": (147.9, 130.0), "fry_hold_12.7A": (159.8, 139.7)}       # (T_winding, T_air), study 02 via study 08
H_EYE = 10.0
DELTA0, WARP = 20e-6, 0.5e-3


def k_air(t_c):
    return 0.0241 * ((t_c + 273.15) / 273.15) ** 0.81


def h_glass(gap):
    t = T_PAN - 10
    return k_air(t) / (gap + DELTA0) + 4 * 0.73 * SIG * (t + 273.15) ** 3


def grid():
    re = np.concatenate([np.arange(0, 10, 0.05), np.arange(10, 26.001, 0.25)])
    ze = np.concatenate([np.arange(74, 90, 0.5), np.arange(90, 104, 0.1), np.arange(104, 110.0001, 0.05)])
    return re, ze


def rasterise(travel):
    d = C.DIM
    re, ze = grid()
    rc, zc = (re[:-1] + re[1:]) / 2, (ze[:-1] + ze[1:]) / 2
    R, Z = np.meshgrid(rc, zc, indexing="ij")
    mat = np.full(R.shape, "", dtype=object)
    part = np.full(R.shape, "", dtype=object)
    prof = C.profiles(travel)
    body_out = Polygon(prof["body_PI"][1][0])
    void = Polygon(prof["_body_bore_void"][1][0])
    inside_body_env = shapely.contains_xy(body_out, R, Z)
    # glass
    g = (R >= d["bore_r"]) & (Z >= d["glass_under"]) & (Z <= d["glass_top"])
    mat[g], part[g] = "glass", "glass"
    # body = outer - bore
    b = inside_body_env & ~shapely.contains_xy(void, R, Z)
    mat[b], part[b] = "pi", "body_PI"
    order = ["guide_pads_equiv_ring", "stop_collar_PI", "wiper_FFKM", "static_gasket_FFKM", "spring_washer_bayonet_PEEK", "spring_A286",
             "splice_potting", "cable_strain_relief_PEEK", "seat_cup_PEEK", "post_polyimide", "fibre_plug_annulus",
             "fibre_plug_core", "lead_capillary_fused_silica", "foot_potting", "Pt100_chip_IST_P0K1202", "chip_bond", "disc_Si3N4"]
    for name in order:
        m, polys = prof[name]
        for poly in polys:
            inside = shapely.contains_xy(Polygon(poly), R, Z)
            mat[inside], part[inside] = m, name
    cab = (R <= d["cable_r"]) & (Z < 76.0)                           # the cable runs through the strain relief bore
    mat[cab], part[cab] = "cable", "cable"
    # background
    empty = mat == ""
    enclosed = empty & ((inside_body_env) | ((Z >= d["glass_under"]) & (R < d["bore_r"]))
                        | ((Z >= d["gland_floor"]) & (Z < d["glass_under"]) & (R < d["rim_ri"])))
    mat[enclosed], part[enclosed] = "cav", "enclosed_air"
    empty = mat == ""
    wind = empty & (R >= 22.0) & (Z >= 93.0) & (Z < 101.6)
    mat[wind], part[wind] = "WIND", "winding_zone"
    gapz = empty & (R >= 22.0) & (Z >= 101.6) & (Z < d["glass_under"])
    mat[gapz], part[gapz] = "gap", "winding_glass_gap"
    car = empty & (R >= d["carrier_aperture_r"]) & (Z >= 90.0) & (Z < 93.0)
    mat[car], part[car] = "g11", "carrier"
    rest = mat == ""
    mat[rest], part[rest] = "EYE", "eye_air"
    return re, ze, R, Z, mat, part


def solve(travel, h_c, eye, gap_glass, k_over=None, bc=None):
    """bc (optional) overrides the boundary temperatures for transfer-conductance runs:
    dict(t_pan, t_wind, t_air, t_disc) - t_disc holds the disc, bond and chip cells fixed."""
    kk = dict(K, **(k_over or {}))
    re, ze, R, Z, mat, part = rasterise(travel)
    t_wind, t_air = EYE[eye]
    t_pan = T_PAN
    t_disc = None
    if bc:
        t_wind, t_air, t_pan, t_disc = bc["t_wind"], bc["t_air"], bc["t_pan"], bc.get("t_disc")
    nr, nz = R.shape
    dr, dz = np.diff(re), np.diff(ze)
    disc_cells = np.isin(part, ["disc_Si3N4", "chip_bond", "Pt100_chip_IST_P0K1202"])
    fixed = (mat == "WIND") | (mat == "EYE")
    tfix = np.where(mat == "WIND", t_wind, t_air).astype(float)
    if t_disc is not None:
        fixed = fixed | disc_cells
        tfix[disc_cells] = t_disc
    kmap = np.vectorize(lambda m: kk.get(m, 0.0))(mat)
    idx = -np.ones((nr, nz), dtype=int)
    free = ~fixed
    idx[free] = np.arange(free.sum())
    n = free.sum()
    rows, cols, vals, rhs = [], [], [], np.zeros(n)

    def couple(i, j, ii, jj, g):
        a, b = idx[i, j], idx[ii, jj]
        if a >= 0 and b >= 0:
            rows.extend([a, a, b, b]); cols.extend([a, b, b, a]); vals.extend([g, -g, g, -g])
        elif a >= 0:
            rows.append(a); cols.append(a); vals.append(g); rhs[a] += g * tfix[ii, jj]
        elif b >= 0:
            rows.append(b); cols.append(b); vals.append(g); rhs[b] += g * tfix[i, j]

    def half(i, j, area, length):
        return kmap[i, j] * area / (length / 2) if kmap[i, j] > 0 else np.inf

    for i in range(nr):
        for j in range(nz):
            # radial face to i+1
            if i + 1 < nr:
                area = 2 * pi * re[i + 1] * 1e-3 * dz[j] * 1e-3
                g = _series(mat, i, j, i + 1, j, half(i, j, area, dr[i] * 1e-3), half(i + 1, j, area, dr[i + 1] * 1e-3), area)
                if g:
                    couple(i, j, i + 1, j, g)
            if j + 1 < nz:
                area = pi * (re[i + 1] ** 2 - re[i] ** 2) * 1e-6
                g = _series(mat, i, j, i, j + 1, half(i, j, area, dz[j] * 1e-3), half(i, j + 1, area, dz[j + 1] * 1e-3), area)
                if g:
                    couple(i, j, i, j + 1, g)
    # top: pan
    j = nz - 1
    no_top_r = bc.get("no_top_r", -1.0) if bc else -1.0
    for i in range(nr):
        a = idx[i, j]
        if a < 0 or re[i + 1] <= no_top_r + 1e-9:
            continue
        area = pi * (re[i + 1] ** 2 - re[i] ** 2) * 1e-6
        h = {"glass": h_glass(gap_glass), "si3n4": h_c}.get(mat[i, j], None)
        g_in = kmap[i, j] * area / (dz[j] * 1e-3 / 2)
        g = 1 / (1 / g_in + 1 / (h * area)) if h else g_in
        rows.append(a); cols.append(a); vals.append(g); rhs[a] += g * t_pan
    # bottom: eye air
    j = 0
    for i in range(nr):
        a = idx[i, j]
        if a < 0:
            continue
        area = pi * (re[i + 1] ** 2 - re[i] ** 2) * 1e-6
        g = 1 / (1 / (kmap[i, j] * area / (dz[j] * 1e-3 / 2)) + 1 / (H_EYE * area))
        rows.append(a); cols.append(a); vals.append(g); rhs[a] += g * t_air
    A = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
    T = np.array(tfix, dtype=float)
    T[free] = spla.spsolve(A, rhs)
    return dict(re=re, ze=ze, R=R, Z=Z, mat=mat, part=part, T=T, kmap=kmap, fixed=fixed)


def _series(mat, i, j, ii, jj, g1, g2, area):
    m1, m2 = mat[i, j], mat[ii, jj]
    if np.isinf(g1) or np.isinf(g2):
        g1, g2 = (g2, g2) if np.isinf(g1) else (g1, g1)
    f1, f2 = m1 in ("WIND", "EYE"), m2 in ("WIND", "EYE")
    if f1 and f2:
        return 0.0
    if f1 or f2:
        g_solid = g2 if f1 else g1
        if (m1 if f1 else m2) == "EYE":
            return 1 / (1 / g_solid + 1 / (H_EYE * area))
        return g_solid                                      # winding zone: contact to the held temperature
    return 1 / (1 / g1 + 1 / g2)


def disc_outflow(sol):
    """Heat (W) leaving the disc+bond+chip into each neighbouring part class."""
    part, T, kmap, re, ze = sol["part"], sol["T"], sol["kmap"], sol["re"], sol["ze"]
    src = {"disc_Si3N4", "chip_bond", "Pt100_chip_IST_P0K1202"}
    nr, nz = part.shape
    dr, dz = np.diff(re), np.diff(ze)
    flows = {}
    for i in range(nr):
        for j in range(nz):
            if part[i, j] not in src:
                continue
            for ii, jj, area, l1, l2 in ((i + 1, j, 2 * pi * re[i + 1] * dz[j], dr[i], dr[i + 1] if i + 1 < nr else 1),
                                         (i, j - 1, pi * (re[i + 1] ** 2 - re[i] ** 2), dz[j], dz[j - 1]),
                                         (i, j + 1, pi * (re[i + 1] ** 2 - re[i] ** 2), dz[j], dz[j + 1] if j + 1 < nz else 1),
                                         (i - 1, j, 2 * pi * re[i] * dz[j], dr[i], dr[i - 1] if i > 0 else 1)):
                if not (0 <= ii < nr and 0 <= jj < nz) or part[ii, jj] in src:
                    continue
                a = area * 1e-6
                g = 1 / (l1 * 1e-3 / 2 / (kmap[i, j] * a) + l2 * 1e-3 / 2 / (kmap[ii, jj] * a))
                flows[part[ii, jj]] = flows.get(part[ii, jj], 0.0) + g * (T[i, j] - T[ii, jj])
    return {k: round(v * 1e3, 3) for k, v in flows.items()}


def part_stats(sol):
    part, T = sol["part"], sol["T"]
    out = {}
    for name in np.unique(part):
        m = part == name
        out[str(name)] = dict(max=round(float(T[m].max()), 1), mean=round(float(T[m].mean()), 1))
    d = C.DIM
    R, Z = sol["R"], sol["Z"]
    post = part == "post_polyimide"
    top = post & (Z > d["disc_bot"] - d["proud"] - 1.0)
    out["post_top_1mm"] = dict(max=round(float(T[top].max()), 1), mean=round(float(T[top].mean()), 1))
    collar = (part == "body_PI") & (Z >= d["glass_under"])
    out["body_collar_in_bore"] = dict(max=round(float(T[collar].max()), 1), mean=round(float(T[collar].mean()), 1))
    below = (part == "body_PI") & (Z < d["glass_under"])
    out["body_below_glass"] = dict(max=round(float(T[below].max()), 1), mean=round(float(T[below].mean()), 1))
    lip = (part == "wiper_FFKM") & (R < 4.3)
    out["wiper_lip_tip"] = dict(max=round(float(T[lip].max()), 1), mean=round(float(T[lip].mean()), 1))
    ntc = (part == "glass") & (np.abs(R - 14.5) < 0.7) & (Z < d["glass_under"] + 0.2)
    out["glass_underside_at_rim_NTC_r14.5"] = dict(max=round(float(T[ntc].max()), 1), mean=round(float(T[ntc].mean()), 1))
    rim = (part == "body_PI") & (R >= d["rim_ri"]) & (R <= d["rim_ro"]) & (Z > 105.0)
    out["body_rim_datum"] = dict(max=round(float(T[rim].max()), 1), mean=round(float(T[rim].mean()), 1))
    return out


def leak_split(travel=None, eye="fry_hold_12.7A", h_c=888.0, k_over=None):
    """G4 by transfer conductances (W/K) with the disc, bond and chip held at 1 K:
    The pan boundary over the contact face (r <= disc radius) is made adiabatic: the contact itself is not a leak.
    G_cold: pan/glass held at 1 (the rim-NTC-tracked hot side), eye air and winding at 0 -> disc outflow;
    G_total: everything else at 0 -> disc outflow; G_hot = G_total - G_cold (to the glass-bore collar/glass/pan).
    Also the flow out of the post group (post, fibre, leads, potting, cup) by destination in the G_cold run."""
    d = C.DIM
    t = d["proud"] if travel is None else travel
    a = solve(t, h_c, eye, 0.0, k_over, bc=dict(t_pan=1.0, t_wind=0.0, t_air=0.0, t_disc=1.0, no_top_r=d["disc_r"]))
    b = solve(t, h_c, eye, 0.0, k_over, bc=dict(t_pan=0.0, t_wind=0.0, t_air=0.0, t_disc=1.0, no_top_r=d["disc_r"]))
    qa, qb = sum(disc_outflow(a).values()) / 1e3, sum(disc_outflow(b).values()) / 1e3
    return dict(G_cold_mW_K=round(qa * 1e3, 4), G_total_mW_K=round(qb * 1e3, 4), G_hot_mW_K=round((qb - qa) * 1e3, 4),
                outflow_cold_run_mW_by_neighbour=disc_outflow(a), outflow_total_run_mW_by_neighbour=disc_outflow(b),
                travel=t, eye=eye, h_c=h_c,
                method="transfer conductance: disc held at 1 K; cold = eye air + winding sinks, hot = pan/glass side")


def main():
    d = C.DIM
    hc = json.loads((HERE.parent / "contact-model.json").read_text())["h_c_W_m2K"]["sensor-r3 Si3N4 disc (lapped)"]
    h_list = {"as-cast iron 2 mrad (worst)": hc["cast_iron_as_cast"]["h_c_by_tilt"]["0.002"],
              "enamel iron 0 mrad": hc["enamel_cast_iron"]["h_c_by_tilt"]["0"],
              "polished clad 0 mrad (hottest disc)": hc["clad_polished_ss"]["h_c_by_tilt"]["0"]}
    cases, worst = [], {}
    for eye in EYE:
        for hname, h in h_list.items():
            for gname, gap in (("flat pan", 0.0), ("0.5 mm warp", WARP)):
                sol = solve(d["proud"], h, eye, gap)
                stats = part_stats(sol)
                flows = disc_outflow(sol) if gname == "flat pan" else None
                cases.append(dict(eye=eye, contact=hname, h_c=h, glass=gname, h_glass=round(h_glass(gap), 1),
                                  parts=stats, disc_outflow_mW=flows))
                for k, v in stats.items():
                    if k not in worst or v["max"] > worst[k]["max"]:
                        worst[k] = dict(max=v["max"], case=f"{eye} | {hname} | {gname}")
                print(eye, hname, gname, {k: stats[k]["max"] for k in ("disc_Si3N4", "chip_bond", "post_top_1mm",
                                                                         "wiper_lip_tip", "static_gasket_FFKM",
                                                                         "body_collar_in_bore", "spring_A286")}, flush=True)
    sens = solve(d["proud"], h_list["as-cast iron 2 mrad (worst)"], "fry_hold_12.7A", 0.0, {"fibre": 0.08, "ffkm": 0.3})
    split = {f"{e}|h_c {h:.0f}": leak_split(d["proud"], e, h) for e in EYE for h in (h_list["as-cast iron 2 mrad (worst)"], h_list["polished clad 0 mrad (hottest disc)"])}
    out = {"scope": __doc__.strip(), "T_pan_C": T_PAN, "leak_split_G4": split, "k_W_mK": K, "eye_states": EYE, "h_eye": H_EYE,
           "grid": {"r_cells": int(len(grid()[0]) - 1), "z_cells": int(len(grid()[1]) - 1)},
           "cases": cases, "worst_by_part": worst,
           "sensitivity_fibre0.08_ffkm0.3": {k: v["max"] for k, v in part_stats(sens).items()}}
    (HERE / "thermal-axisym.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(worst, indent=1))


if __name__ == "__main__":
    main()
