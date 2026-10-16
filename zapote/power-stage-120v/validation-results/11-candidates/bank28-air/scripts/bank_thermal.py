#!/usr/bin/env python3
"""Physical self-heating / hot-spot check of the resonant bank at 28 A under the airflow28 cases (bank28 lane).

    python3 -I bank_thermal.py [--ps PS] [--pads ../bank_pads.json] [--out ../bank_thermal.json]

Read-only on PS (zapote/power-stage-120v).  Stdlib only.

TDK's rule, read from the data sheets (pages cited in results.md):
  * B3265x (fitted B32654A1104J000): I_RMS(f) curve p.57 is the locus of self-heating dT = 20 K at T_A <= 85 C
    (p.57 title; p.23 fn 2).  dT is "the steady-state overtemperature attained at the hottest part of the capacitor
    surface in relation to the surrounding atmosphere" and Pdiss = alpha * A * dT (General technical information,
    Oct 2025, p.25).  T_A is measured on an unpowered dummy capacitor of similar size ~50 mm away on the same PC board
    (GTI p.30, Figure 26).  Above 85 C, I_RMS x F_T(T_A) (p.64), with Top = T_A + dT <= Top,max 110 C (p.35, p.64).
    F_T read off p.64 fits sqrt((110 - T_A) / 25)  ->  dT_allowed = 20 K x F_T^2 = 0.8 (110 - T_A).
  * B3264*B (c34 B32643B8104J000): p.24 curve at T_A <= 85 C, dT <= 15 K (p.11 fn 8); F_T p.25 fits
    sqrt((125 - T_A) / 40), Top,max 125 C case (p.2, p.12).
TDK's own scaling of dT with load (GTI p.27): dT' = (I' / I_max(f))^2 x dT_lim.  So at the curve's own test
conditions the part rises ratio^2 x dT_lim, ratio = I_part / I_allow(f) (c34 bank_margin.json, J worst share).
The physical check rescales that by the conductance of TDK's test mounting over ours:

    P            = ratio^2 x dT_lim x G_tdk                      (heat the part makes; G_tdk = TDK's test conductance)
    dT_ours      = P / G_ours = ratio^2 x dT_lim x G_tdk / G_ours
    T_A (dummy)  = (G_air T_air + G_board T_board) / (G_air + G_board)     (an unpowered cap at the same spot)
    pass         : dT_ours <= dT_lim x F_T(T_A)^2   and   T_A + dT_ours <= Top,max
    eff. ratio   = sqrt(dT_ours / (dT_lim F_T(T_A)^2))     (<= 1: TDK limit; <= 0.85: the c34 project margin)

G_tdk and G_ours come from the SAME first-principles model (correlation errors cancel in the ratio):
  G = sum_faces h_face A_face  +  G_board
  TDK test: isolated part, all five faces exposed (bottom faces the board), still air, natural convection
    (Churchill-Chu vertical faces; 0.54 Ra^1/4 hot face up) + radiation eps 0.9 to walls at T_A = 85 C, surface at
    T_A + dT_lim; board at T_A.
  Ours: the bank is one column with 0.5-0.8 mm gaps (native21-boxes.json), so an interior part's two h x l faces face
    equally hot neighbours and shed nothing (symmetry); it keeps its top (w x l) and its two end faces (w x h).
    The two end parts (C21, C152) keep one h x l face as well.
    Still air: natural convection on the exposed faces, air at bay + 15 K (B3 FILM_HF_AIR_RISE_K, the board's
      natural-convection layer), with and without radiation (eps 0.9 to surroundings at that air).
    Forced (flow along +x, meeting the column's w x h end faces): no radiation, no natural convection credit.
      Correlation set A, face by face: top and outer side faces laminar flat plate over l (Nu = 0.664 Re^0.5 Pr^1/3);
        upstream face Sparrow & Geiger 1985 flat face normal to the flow, Nu_D = 1.05 Re_D^0.5 Pr^0.36, D = h;
        rear (wake) face 0.5 x the top-face h (ASSUMED).
      Correlation set B, bluff prism: Incropera Table 7.3 square cylinder, flat face to the flow (Jakob),
        Nu_D = 0.102 Re_D^0.675 Pr^1/3, D = l, on every exposed face (Re below 5e3 is an extrapolation).
      The check uses the LOWER of A and B.
    Velocity: airflow28 results/enclosure.json "corner + tank path along x", v_turbulent (the lower, tripped
      estimate); air at bay + that path's bulk rise (gap 10 mm), i.e. the whole upstream pick-up.
  G_board (leads + bottom-face gap), the same in TDK's test and ours, two bounds:
    lo 0.005 W/K: TDK's rating implies the hottest-surface point is only weakly tied to its leads (calibration below);
    hi 0.046 W/K: B3's 50 K/W lead path (thermal_body film_radial) + air conduction across the 0.5 mm seat
       (K_AIR 0.026 x bottom area / seat; body z 2.113 mm over a 1.6 mm board, native21-boxes.json).
    T_board = the B3 bank pad maximum of that case (bank_pads.json, the gate's estimator).  Each criterion takes
    the worse bound (hi raises T_A toward the hot pads; lo gives the larger dT).
Sensitivities reported, not gated: 29.4 A (the 1.05 x ceiling trip, I^2); a part at the tan d upper limit (p.35 / p.12,
20 C limits fitted R_s + D / (w C), as B3's make_heat_sources); core penalty of the shadowed column (heat must run
along the winding to the end contacts instead of through the big faces: slab estimate, k_radial 0.2, k_inplane
0.5-1.0 W/mK ASSUMED); velocity x 0.5 at the bank (the 26 mm-tall column in a 10 mm face gap).
"""
import argparse
import json
import math
from pathlib import Path

SIGMA = 5.670374e-8
G0 = 9.81
EPS = 0.9
K_AIR_GAP = 0.026
SEAT_M = 0.5e-3

ap = argparse.ArgumentParser()
ap.add_argument("--ps", default="/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
ap.add_argument("--pads", default=str(Path(__file__).resolve().parent.parent / "bank_pads.json"))
ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "bank_thermal.json"))
a = ap.parse_args()
PS = Path(a.ps)
C34 = PS / "validation-results/11-candidates/c34-bank-margin"
AF = PS / "validation-results/11-candidates/airflow28-2026-10-16"

bm = json.loads((C34 / "results/bank_margin.json").read_text())
parts = {}
for f in ("raw/parts_tdk.json", "raw/parts_tdk_b3264.json"):
    for p in json.loads((C34 / f).read_text())["parts"]:
        parts[p["id"]] = p


def bank_row(prefix):
    for r in bm["banks"]:
        if r.get("bank", "").startswith(prefix):
            return r
    raise KeyError(prefix)


FAM = {
    "fitted 5 x B32654A1104J000": dict(pid="tdk_a1104j", row=bank_row("5 x B32654A1104J000"), dT_lim=20.0,
                                       top_max=110.0, ft_end=110.0, ft_span=25.0, h_box=24.5,
                                       tand=(1.0e-3, 3.0e-3), esr_typ_100k=19.3e-3, i100k=7.3),
    "c34 5 x B32643B8104J000": dict(pid="tdk_b8104j", row=bank_row("5 x B32643B8104J (2000 V, 22.5 mm"), dT_lim=15.0,
                                    top_max=125.0, ft_end=125.0, ft_span=40.0, h_box=29.5,
                                    tand=(0.6e-3, 1.5e-3), esr_typ_100k=8e-3, i100k=8.3),
}


def ft2(fam, ta):
    """F_T^2 fitted to the p.64 / p.25 curves: 1 at <= 85 C, (end - T_A) / span above, 0 at the end."""
    if ta <= 85.0:
        return 1.0
    return max(0.0, (fam["ft_end"] - ta) / fam["ft_span"])


def air(t_c):
    t = t_c + 273.15
    k = 0.02624 * (t / 300.0) ** 0.8
    mu = 1.846e-5 * (t / 300.0) ** 0.7
    rho = 101325.0 / (287.05 * t)
    return dict(k=k, nu=mu / rho, pr=0.70, rho=rho, cp=1007.0, beta=1.0 / t)


def h_vert(dt, H, tf):
    if dt <= 0:
        return 0.0
    p = air(tf)
    ra = G0 * p["beta"] * dt * H ** 3 / (p["nu"] ** 2) * p["pr"]
    nu = 0.68 + 0.670 * ra ** 0.25 / (1 + (0.492 / p["pr"]) ** (9 / 16)) ** (4 / 9)
    return nu * p["k"] / H


def h_up(dt, L, tf):
    if dt <= 0:
        return 0.0
    p = air(tf)
    ra = G0 * p["beta"] * dt * L ** 3 / (p["nu"] ** 2) * p["pr"]
    nu = 0.54 * ra ** 0.25 if ra < 1e7 else 0.15 * ra ** (1 / 3)
    return nu * p["k"] / L


def h_rad(ts, tsur):
    a_, b_ = ts + 273.15, tsur + 273.15
    return EPS * SIGMA * (a_ * a_ + b_ * b_) * (a_ + b_)


def faces(p, h_box, position):
    """exposed faces (m^2) of a part in the bank column; flow along x meets the w x h end faces."""
    w, l = p["w"] * 1e-3, p["l"] * 1e-3
    h = h_box * 1e-3
    f = {"top": w * l, "front": w * h, "rear": w * h}
    if position == "isolated":
        f["side"] = 2 * h * l
    elif position == "end":
        f["side"] = h * l
    return f


def g_tdk_test(fam, g_board):
    """first-principles conductance of TDK's test: isolated part, still air at 85 C, surface at 85 + dT_lim."""
    p = parts[fam["pid"]]
    fc = faces(p, fam["h_box"], "isolated")
    ts, ta = 85.0 + fam["dT_lim"], 85.0
    tf = (ts + ta) / 2
    hv = h_vert(ts - ta, fam["h_box"] * 1e-3, tf)
    hu = h_up(ts - ta, fc["top"] / (2 * (p["w"] + p["l"]) * 1e-3), tf)
    hr = h_rad(ts, ta)
    g_air = (hv + hr) * (fc["front"] + fc["rear"] + fc["side"]) + (hu + hr) * fc["top"]
    return g_air + g_board, dict(h_vert=round(hv, 2), h_up=round(hu, 2), h_rad=round(hr, 2), g_air=round(g_air, 5))


def g_forced(fam, position, v, t_air, corr):
    p = parts[fam["pid"]]
    fc = faces(p, fam["h_box"], position)
    pr = air(t_air + 10)
    l, hh = p["l"] * 1e-3, fam["h_box"] * 1e-3
    if corr == "A":
        re_l = v * l / pr["nu"]
        h_top = 0.664 * re_l ** 0.5 * pr["pr"] ** (1 / 3) * pr["k"] / l
        re_d = v * hh / pr["nu"]
        h_front = 1.05 * re_d ** 0.5 * pr["pr"] ** 0.36 * pr["k"] / hh
        hs = {"top": h_top, "front": h_front, "rear": 0.5 * h_top, "side": h_top}
    else:
        re = v * l / pr["nu"]
        h_all = 0.102 * re ** 0.675 * pr["pr"] ** (1 / 3) * pr["k"] / l
        hs = {k: h_all for k in fc}
    return sum(hs[k] * fc[k] for k in fc), {k: round(hs[k], 1) for k in fc}


def g_slot(fam, v, t_air, gap_m=0.5e-3, cp_diff=1.3):
    """capacity-limited conductance of laminar slot flow through the two side gaps of an interior part: dp = cp_diff
    x 1/2 rho v^2 front-to-rear, u = dp b^2 / (12 mu L), each slot shared by two parts (half each, two slots)."""
    p = parts[fam["pid"]]
    pr = air(t_air + 10)
    mu = pr["nu"] * pr["rho"]
    dp = cp_diff * 0.5 * pr["rho"] * v * v
    u = dp * gap_m ** 2 / (12 * mu * p["l"] * 1e-3)
    return pr["rho"] * u * gap_m * fam["h_box"] * 1e-3 * pr["cp"]


def g_still(fam, position, dt_s, t_air, rad):
    p = parts[fam["pid"]]
    fc = faces(p, fam["h_box"], position)
    ts = t_air + dt_s
    tf = (ts + t_air) / 2
    hv = h_vert(dt_s, fam["h_box"] * 1e-3, tf)
    col_top = 72.3e-3 * p["l"] * 1e-3                     # the column top acts as one plate (A/P)
    hu = h_up(dt_s, col_top / (2 * (72.3e-3 + p["l"] * 1e-3)), tf)
    hr = h_rad(ts, t_air) if rad else 0.0
    g = (hv + hr) * (fc["front"] + fc["rear"] + fc.get("side", 0.0)) + (hu + hr) * fc["top"]
    return g, {"h_vert": round(hv, 2), "h_up": round(hu, 2), "h_rad": round(hr, 2)}


G_BOARD = {"lo": 0.005, "hi": 1.0 / 50.0 + K_AIR_GAP * 0.0 }   # filled per family below (gap uses bottom area)


def g_board(fam, bound):
    p = parts[fam["pid"]]
    if bound == "lo":
        return 0.005
    return 1.0 / 50.0 + K_AIR_GAP * (p["w"] * p["l"] * 1e-6) / SEAT_M


def esr_limit(fam, f):
    c = 1e-7
    t10, t100 = fam["tand"]
    e10, e100 = t10 / (2 * math.pi * 1e4 * c), t100 / (2 * math.pi * 1e5 * c)
    d = (e10 - e100) / (1 / (2 * math.pi * 1e4 * c) - 1 / (2 * math.pi * 1e5 * c))
    rs = e100 - d / (2 * math.pi * 1e5 * c)
    return rs + d / (2 * math.pi * f * c)


pads = {c["case"]: c for c in json.loads(Path(a.pads).read_text())}
enc = json.loads((AF / "results/enclosure.json").read_text())
PATH = "corner + tank path along x, 195 mm run, 120 mm wide"


def enc_v(key):
    if key[0] == "jetmix":
        r = enc["jetmix_base"][key[1]][PATH]
    else:
        r = enc[key[1]][key[2]][PATH]
    return r["v_turbulent_m_s"], r["bulk_rise_K_gap10"]


CASES = [
    # label, pads case, bay, enclosure key (None = still air)
    ("still air h10 @61", "still air h10 @61", 61, None),
    ("still air h10 @55", "still air h10 @55", 55, None),
    ("jets + base h16 @61 (min)", "jet100 + base h16 @61 (min)", 61, ("jetmix", "h16")),
    ("jets + base h20 @61 (design x1.25)", "jet100 + base h20 @61 (x1.25)", 61, ("jetmix", "h20")),
    ("jets + base h12 @55 (min)", "jet100 + base h12 @55 (min)", 55, ("jetmix", "h12")),
    ("jets + base h15 @55 (design x1.25)", "jet100 + base h15 @55 (x1.25)", 55, ("jetmix", "h15")),
    ("no jets h31 @61 (min)", "no-jet h31 @61 (min)", 61, ("uniform", "uniform:c28@61", "at_h")),
    ("no jets h37 @61 (design x1.2)", "no-jet h37 @61 (x1.2)", 61, ("uniform", "uniform:c28@61", "at_1.2h")),
    ("no jets h27 @55 (min)", "no-jet h27 @55 (min)", 55, ("uniform", "uniform:c28@55", "at_h")),
    ("no jets h33 @55 (design x1.2)", "no-jet h33 @55 (x1.2)", 55, ("uniform", "uniform:c28@55", "at_1.2h")),
]
POS = {"interior (C22, C23, C151)": ("interior", ("C22", "C23", "C151")), "end (C21, C152)": ("end", ("C21", "C152"))}


def solve(fam, ratio, case, vfac=1.0, i_scale=1.0, bound=None, corr=None, rad_forced=False, slot=False):
    """returns per position the worse-bound result."""
    label, pk, bay, ek = case
    t_board_case = pads[pk]["bank"]
    out = {}
    for pname, (pos, refs) in POS.items():
        t_board = max(t_board_case[r]["pad_max_c"] for r in refs)
        res = {}
        for b in (("lo", "hi") if bound is None else (bound,)):
            gb = g_board(fam, b)
            gt, _ = g_tdk_test(fam, gb)
            p_w = (ratio * i_scale) ** 2 * fam["dT_lim"] * gt
            if ek is None:
                t_air = bay + 15.0
                for rad in (True, False):
                    dt = 10.0
                    for _ in range(200):
                        ga, hd = g_still(fam, pos, max(dt, 0.5), t_air, rad)
                        ta = (ga * t_air + gb * t_board) / (ga + gb)
                        dt_new = p_w / (ga + gb)
                        ts_air = ta + dt_new - t_air         # surface over the air drives the film coefficients
                        if abs(ts_air - dt) < 1e-4:
                            break
                        dt = 0.5 * dt + 0.5 * ts_air
                    res[f"{b}{'' if rad else '_norad'}"] = dict(g_air=ga, g_board=gb, g_tdk=gt, P_W=p_w, T_air=t_air,
                                                                T_board=t_board, h=hd)
            else:
                v, rise = enc_v(ek)
                v *= vfac
                t_air = bay + rise
                for cset in ("A", "B"):
                    ga, hd = g_forced(fam, pos, v, t_air, cset)
                    if rad_forced:                      # SENSITIVITY: eps 0.9 to surroundings at the local air
                        fc = faces(parts[fam["pid"]], fam["h_box"], pos)
                        ga += h_rad(t_air + 25.0, t_air) * sum(fc.values())
                    if slot and pos == "interior":      # SENSITIVITY: pressure-driven flow through the two 0.5 mm gaps
                        ga += g_slot(fam, v, t_air)
                    res[f"{b}_{cset}"] = dict(g_air=ga, g_board=gb, g_tdk=gt, P_W=p_w, T_air=t_air, T_board=t_board,
                                              v=v, corr=cset, h=hd)
        for k, r in res.items():
            r["T_A_dummy"] = (r["g_air"] * r["T_air"] + r["g_board"] * r["T_board"]) / (r["g_air"] + r["g_board"])
            r["dT"] = r["P_W"] / (r["g_air"] + r["g_board"])
            r["dT_allowed"] = fam["dT_lim"] * ft2(fam, r["T_A_dummy"])
            r["T_op"] = r["T_A_dummy"] + r["dT"]
            r["eff_ratio"] = math.sqrt(r["dT"] / r["dT_allowed"]) if r["dT_allowed"] > 0 else float("inf")
            r["Top_margin_K"] = fam["top_max"] - r["T_op"]
        # the check: worst bound (still air: with radiation is the central case; no-radiation reported)
        keys = [k for k in res if not k.endswith("_norad") and (corr is None or k.endswith("_" + corr) or "_" not in k)]
        worst = max(keys, key=lambda k: (res[k]["eff_ratio"], -res[k]["Top_margin_K"]))
        worst_top = min(keys, key=lambda k: res[k]["Top_margin_K"])
        out[pname] = dict(bounds={k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in r.items()}
                                  for k, r in res.items()},
                          eff_ratio=round(res[worst]["eff_ratio"], 3), dT_K=round(res[worst]["dT"], 1),
                          dT_allowed_K=round(res[worst]["dT_allowed"], 1), T_A_dummy_C=round(res[worst]["T_A_dummy"], 1),
                          worst_bound=worst, T_op_C=round(res[worst_top]["T_op"], 1),
                          Top_margin_K=round(res[worst_top]["Top_margin_K"], 1),
                          passes_tdk=res[worst]["eff_ratio"] <= 1.0 and res[worst_top]["Top_margin_K"] >= 0,
                          meets_085=res[worst]["eff_ratio"] <= 0.85 and res[worst_top]["Top_margin_K"] >= 0)
    w = max(out.values(), key=lambda r: r["eff_ratio"])
    return out, w


def core_penalty(fam, p_w, kip):
    """extra core rise of the shadowed column over TDK's isolated test (slab estimates, winding = body - 1 mm walls)."""
    p = parts[fam["pid"]]
    w, h, l = (p["w"] - 2) * 1e-3, (fam["h_box"] - 2) * 1e-3, (p["l"] - 2) * 1e-3
    vol = w * h * l
    r_iso = w / (8 * 0.2 * h * l)                      # through the big faces, k_radial 0.2
    r_col = (l / 2) ** 2 / (2 * kip * vol)             # along the winding to the two end contacts
    return p_w * (r_col - r_iso)


res = {"basis": {"I_tank_A": 28.0, "ratios_from": str(C34 / "results/bank_margin.json"), "pads_from": a.pads,
                 "velocity_from": str(AF / "results/enclosure.json") + " / " + PATH + " (v_turbulent, bulk_rise_K_gap10)",
                 "g_board_bounds_W_per_K": {f: {"lo": g_board(fam, "lo"), "hi": round(g_board(fam, "hi"), 4)}
                                            for f, fam in FAM.items()}},
       "calibration": {}, "cases": {}, "sensitivities": {}, "velocity_needed": {}}

for fname, fam in FAM.items():
    p = parts[fam["pid"]]
    g_impl = fam["i100k"] ** 2 * fam["esr_typ_100k"] / fam["dT_lim"]
    cal = {}
    for b in ("lo", "hi"):
        gt, det = g_tdk_test(fam, g_board(fam, b))
        cal[b] = dict(G_model_W_per_K=round(gt, 4), **det)
    res["calibration"][fname] = dict(G_implied_by_table_W_per_K=round(g_impl, 4),
                                     table=f"I_RMS {fam['i100k']} A at 85 C / 100 kHz, ESR_typ {fam['esr_typ_100k'] * 1e3:g} mOhm, dT {fam['dT_lim']:g} K",
                                     model=cal,
                                     model_over_implied={b: round(cal[b]["G_model_W_per_K"] / g_impl, 3) for b in cal})
    r35, r40 = fam["row"]["ratio_35k"], fam["row"]["ratio_40k"]
    res["cases"][fname] = {}
    for case in CASES:
        row = {}
        for fk, rr in (("35k", r35), ("40k", r40)):
            per, w = solve(fam, rr, case, corr="B")
            if case[3] is not None:
                _, wa = solve(fam, rr, case, corr="A")
                central = dict(eff_ratio=wa["eff_ratio"], dT_K=wa["dT_K"], T_A_dummy_C=wa["T_A_dummy_C"],
                               Top_margin_K=wa["Top_margin_K"], passes_tdk=wa["passes_tdk"], meets_085=wa["meets_085"])
            else:
                central = None
            row[fk] = dict(ratio_vendor=rr, central_corr_A=central, worst=dict(eff_ratio=w["eff_ratio"], dT_K=w["dT_K"], dT_allowed_K=w["dT_allowed_K"],
                                                       T_A_dummy_C=w["T_A_dummy_C"], T_op_C=w["T_op_C"],
                                                       Top_margin_K=w["Top_margin_K"], passes_tdk=w["passes_tdk"],
                                                       meets_085=w["meets_085"]),
                           positions=per)
        res["cases"][fname][case[0]] = row
    # sensitivities at 35 kHz on the recommended design point and the no-jet design point
    sens = {}
    for case in (CASES[3], CASES[5], CASES[7], CASES[9]):
        _, w294 = solve(fam, r35, case, i_scale=29.4 / 28.0, corr="B")
        _, wv = solve(fam, r35, case, vfac=0.5, corr="B")
        # a part at the tan d upper limit: heat x ESR_limit(35k) / ESR implied by the curve at 35 kHz
        i_allow35 = 28.0 * fam["row"]["worst_share"] / r35
        esr_curve = (fam["dT_lim"] * g_impl) / i_allow35 ** 2
        fac = esr_limit(fam, 35e3) / esr_curve
        _, wt = solve(fam, r35 * math.sqrt(fac), case, corr="B")
        _, wrA = solve(fam, r35, case, corr="A", rad_forced=True)
        _, wrB = solve(fam, r35, case, corr="B", rad_forced=True)
        _, wsB = solve(fam, r35, case, corr="B", slot=True)
        v_case, rise_case = enc_v(case[3])
        p_w = r35 ** 2 * fam["dT_lim"] * g_impl
        sens[case[0]] = {
            "I_29.4A_trip": dict(eff_ratio=w294["eff_ratio"], dT_K=w294["dT_K"], Top_margin_K=w294["Top_margin_K"]),
            "velocity_x0.5": dict(eff_ratio=wv["eff_ratio"], dT_K=wv["dT_K"], Top_margin_K=wv["Top_margin_K"]),
            "tan_d_upper_limit": dict(esr_curve_implied_mOhm=round(esr_curve * 1e3, 1),
                                      esr_limit_mOhm=round(esr_limit(fam, 35e3) * 1e3, 1), heat_factor=round(fac, 2),
                                      eff_ratio=wt["eff_ratio"], dT_K=wt["dT_K"], Top_margin_K=wt["Top_margin_K"]),
            "core_penalty_K_kip_0.5_1.0": [round(core_penalty(fam, p_w, 0.5), 1), round(core_penalty(fam, p_w, 1.0), 1)],
            "P_part_W_at_28A_35k": round(p_w, 3),
            "radiation_credit_eps0.9": dict(A=dict(eff_ratio=wrA["eff_ratio"], dT_K=wrA["dT_K"]),
                                            B=dict(eff_ratio=wrB["eff_ratio"], dT_K=wrB["dT_K"])),
            "slot_flow_credit_B": dict(eff_ratio=wsB["eff_ratio"], dT_K=wsB["dT_K"],
                                       g_slot_W_per_K=round(g_slot(fam, v_case, case[2] + rise_case), 5)),
        }
    res["sensitivities"][fname] = sens
    # bank-local velocity needed (interior part, 35 kHz, 61 C bay, rise 3.7 K, pads of the h20 jet case)
    need = {}
    for tgt, cc in ((1.0, "B"), (0.85, "B"), (1.0, "A"), (0.85, "A")):
        lo, hi = 0.2, 30.0
        base = CASES[3]
        v0, _ = enc_v(base[3])
        for _ in range(60):
            mid = (lo + hi) / 2
            _, w = solve(fam, r35, base, vfac=mid / v0, corr=cc)
            if w["eff_ratio"] <= tgt and w["Top_margin_K"] >= 0:
                hi = mid
            else:
                lo = mid
        need[f"eff_ratio<={tgt} corr {cc}"] = round(hi, 2) if hi < 29.9 else None
    res["velocity_needed"][fname] = dict(case="61 C bay + 3.7 K pick-up, pads of jets + base h20 @61, 28 A, 35 kHz", m_per_s=need)

# still-air ladder (no airflow): the ceiling each bank supports in the column, pads from the B3 ladder runs
res["still_air_ladder"] = {}
for fname, fam in FAM.items():
    r35 = fam["row"]["ratio_35k"]
    rows = []
    for bay in (61, 55):
        for c in (18, 20, 22, 24, 26):
            case = (f"still c{c} @{bay}", f"still air c{c} h10 @{bay}", bay, None)
            _, w = solve(fam, r35 * c / 28.0, case)
            per, _ = solve(fam, r35 * c / 28.0, case)
            nr = max(per.values(), key=lambda r: r["eff_ratio"])
            lo = per["interior (C22, C23, C151)"]["bounds"]
            rows.append(dict(ceiling_A=c, bay_C=bay, eff_ratio=w["eff_ratio"], dT_K=w["dT_K"], T_A_dummy_C=w["T_A_dummy_C"],
                             Top_margin_K=w["Top_margin_K"], interior_lo_rad=dict(dT_K=round(lo["lo"]["dT"], 1),
                                                                                 eff=round(lo["lo"]["eff_ratio"], 3)),
                             interior_lo_norad=dict(dT_K=round(lo["lo_norad"]["dT"], 1), eff=round(lo["lo_norad"]["eff_ratio"], 3)),
                             interior_hi_rad=dict(T_A=round(lo["hi"]["T_A_dummy"], 1), eff=round(lo["hi"]["eff_ratio"], 3))))
    res["still_air_ladder"][fname] = rows

Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
for fname, rows in res["still_air_ladder"].items():
    print("== still-air ladder", fname)
    for r in rows:
        print("  ", r)
for fname in FAM:
    print("==", fname, "calibration", res["calibration"][fname]["G_implied_by_table_W_per_K"], res["calibration"][fname]["model_over_implied"])
    for c, row in res["cases"][fname].items():
        w = row["35k"]["worst"]
        w4 = row["40k"]["worst"]
        ca = row["35k"]["central_corr_A"]
        print(f"  {c:38s} A {('%.3f dT %4.1f' % (ca['eff_ratio'], ca['dT_K'])) if ca else '   -          '} | B 35k eff {w['eff_ratio']:.3f} dT {w['dT_K']:5.1f}/{w['dT_allowed_K']:4.1f} TA {w['T_A_dummy_C']:5.1f} "
              f"Top {w['T_op_C']:5.1f} (m {w['Top_margin_K']:5.1f}) tdk {w['passes_tdk']!s:5s} 0.85 {w['meets_085']!s:5s} | 40k eff {w4['eff_ratio']:.3f}")
    print("  velocity needed:", res["velocity_needed"][fname])
    for c, s in res["sensitivities"][fname].items():
        print("  sens", c, json.dumps(s))
