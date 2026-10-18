#!/usr/bin/env python3
"""Jet bench: choose the test plate, quantify its losses and size the heater (temper-airflow-r1 bench).

    python3 plate_design.py        # seconds; numpy + scipy -> plate-design.json

What it computes (every number DECISIONS.md / RIG.md quotes about the plate comes from here):
  A. Isothermality. 1D fin along the strip (x 0-90 mm): k t T'' = h(x) T - q(x). h(x) is a STRESS PATTERN, not data:
     mean h_bar, +-60 % cosine ripple at the 11 mm jet pitch (stagnation peaks over x = 5.5 + 11k) times a +-40 %
     linear ramp along x (crossflow toward one end; both signs run). Heat enters under the two TO-220 heaters
     (16 mm footprints centred at x 30 and 60) on the metal plates, uniformly on the FR-4 coupon (etched heater).
     Reported: plate temperature spread / mean rise, and the error of h computed from the mean of three
     thermocouples (x 15, 45, 75) against the isothermal-surface h (= the area mean of h(x), what Martin and the
     board model mean by h_top).
  B. Losses of an UNGUARDED plate sunk flush in XPS foam: 2D finite differences across the strip (y-z section,
     0.25 mm grid), plate isothermal, 25 mm foam under it, foam bottom to room at h 4-8, foam top outside the
     plate adiabatic (under the wall blocks) or jet-cooled; G = G'_section x (L + W) (end correction, +-30 %).
  C. Losses of the GUARDED plate (RIG.md): plate-to-guard conductance G_gap summed from its paths. Only
     G_gap x (T_plate - T_guard) reaches the plate's balance; the guard loop holds the difference to <= 0.1 K.
  D. Heater sizing for 2 x 10 ohm in series at the planned rise, against the INA226 module's 0.82 A range.
  E. Time constants, F. radiation, G. how much the spent air heats (why T_jet, not the exit air, is the reference).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import scipy
import scipy.sparse as sp
import scipy.sparse.linalg as spla

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from air import SIGMA, props  # noqa: E402

L, W = 0.090, 0.0165                      # strip, model x 0-90, y 7-23.5 (m)
A = L * W
PITCH, X_JET = 0.011, [0.0055 + 0.011 * k for k in range(8)]
TC_X = [0.015, 0.045, 0.075]
HEATERS = [(0.030, 0.016), (0.060, 0.016)]  # centre, footprint length along x (TO-220 tab + body ~ 16 mm)
DT_PLAN = 25.0                            # planned plate rise over jet air (K)
R_HEATER = 20.0                           # 2 x 10 ohm in series
INA_I_MAX = 0.08192 / 0.1                 # INA226 module: +-81.92 mV over its 0.1 ohm shunt

PLATES = {
    "Al6061_3mm": {"kt": 167.0 * 0.003, "rho_cp_t": 2700 * 896 * 0.003, "heat": "resistors"},
    "Al6061_2mm": {"kt": 167.0 * 0.002, "rho_cp_t": 2700 * 896 * 0.002, "heat": "resistors"},
    "Cu110_2mm": {"kt": 391.0 * 0.002, "rho_cp_t": 8940 * 385 * 0.002, "heat": "resistors"},
    # FR-4 1.6 mm + 2 oz (70 um) copper: the board itself, with an etched (uniform) heater on the back
    "FR4_2oz_coupon": {"kt": 0.30 * 0.0016 + 391.0 * 70e-6, "rho_cp_t": 1850 * 1100 * 0.0016, "heat": "uniform"},
}


def h_pattern(x, h_bar, ripple=0.6, ramp=0.4):
    d = np.min([np.abs(x - xj) for xj in X_JET], axis=0)
    shape = (1 + ripple * np.cos(2 * np.pi * d / PITCH)) * (1 + ramp * (x / L - 0.5))
    return h_bar * shape / shape.mean()


def fin_1d(kt, h, q, dx):
    """k t T'' - h T + q = 0, adiabatic ends (the guard faces the ends at plate temperature)."""
    n = len(h)
    main = -2 * kt / dx ** 2 - h
    off = np.full(n - 1, kt / dx ** 2)
    m = sp.diags([off, main, off], [-1, 0, 1]).tolil()
    m[0, 1] = 2 * kt / dx ** 2
    m[n - 1, n - 2] = 2 * kt / dx ** 2
    return spla.spsolve(m.tocsr(), -q)


def isothermality():
    dx = 0.00025
    x = np.arange(0, L + dx / 2, dx)
    out = {}
    for name, p in PLATES.items():
        rows = []
        for h_bar in (10.0, 100.0, 240.0):
            for ramp in (+0.4, -0.4):
                h = h_pattern(x, h_bar, ramp=ramp)
                if p["heat"] == "resistors":
                    q = np.zeros_like(x)
                    for xc, ln in HEATERS:
                        q[np.abs(x - xc) <= ln / 2] = 1.0
                else:
                    q = np.ones_like(x)
                q *= h_bar * DT_PLAN * L / (q.sum() * dx)        # total = h_bar * L * dT (per unit width)
                t = fin_1d(p["kt"], h, q, dx)
                t_tc = float(np.mean(np.interp(TC_X, x, t)))
                qtot = float(q.sum() * dx)
                h_meas = qtot / (L * t_tc)
                rows.append({"h_bar": h_bar, "ramp": ramp, "spread_over_rise": round(float((t.max() - t.min()) / t.mean()), 4),
                             "h_from_3TC_over_isothermal_h": round(h_meas / h_bar, 4),
                             "h_from_area_mean_T_over_isothermal_h": round(qtot / (L * float(t.mean())) / h_bar, 4)})
        out[name] = {"spreading_length_mm_at_h100": round(1000 * math.sqrt(p["kt"] / 100.0), 1),
                     "spreading_length_mm_at_h240": round(1000 * math.sqrt(p["kt"] / 240.0), 1), "cases": rows,
                     "worst_3TC_error": round(max(abs(r["h_from_3TC_over_isothermal_h"] - 1) for r in rows if r["h_bar"] >= 100), 4)}
    return out


def foam_section(k_foam=0.035, h_bottom=6.0, h_top_out=0.0, foam_t=0.025, margin=0.030, dz=0.00025):
    """Heat loss per metre of an isothermal 16.5 x 3 mm plate sunk flush in foam (y-z section). Returns W/(m K)."""
    ny = int(round((W + 2 * margin) / dz)) + 1
    nz = int(round((0.003 + foam_t) / dz)) + 1
    y = np.linspace(-margin, W + margin, ny)
    z = np.linspace(-(0.003 + foam_t), 0.0, nz)
    Y, Z = np.meshgrid(y, z, indexing="ij")
    plate = (Y >= -1e-12) & (Y <= W + 1e-12) & (Z >= -0.003 - 1e-12)
    idx = -np.ones((ny, nz), dtype=int)
    free = ~plate
    idx[free] = np.arange(free.sum())
    rows, cols, vals = [], [], []
    b = np.zeros(free.sum())
    g = k_foam  # conductance between neighbours per unit length (dz/dz * k)
    for i in range(ny):
        for j in range(nz):
            n = idx[i, j]
            if n < 0:
                continue
            diag = 0.0
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ii, jj = i + di, j + dj
                if not (0 <= ii < ny and 0 <= jj < nz):
                    continue                                  # adiabatic sides
                w = g * (0.5 if (dj == 0 and (j == 0 or j == nz - 1)) or (di == 0 and (i == 0 or i == ny - 1)) else 1.0)
                if plate[ii, jj]:
                    diag += w
                    b[n] += w * 1.0                           # plate at +1 K
                else:
                    diag += w
                    rows.append(n); cols.append(idx[ii, jj]); vals.append(-w)
            if j == 0:
                diag += h_bottom * dz * (0.5 if i in (0, ny - 1) else 1.0)
            if j == nz - 1:
                diag += h_top_out * dz * (0.5 if i in (0, ny - 1) else 1.0)
            rows.append(n); cols.append(n); vals.append(diag)
    m = sp.csr_matrix((vals, (rows, cols)), shape=(free.sum(), free.sum()))
    t = spla.spsolve(m, b)
    T = np.zeros((ny, nz)); T[free] = t; T[plate] = 1.0
    w_edge = np.where((np.arange(ny) == 0) | (np.arange(ny) == ny - 1), 0.5, 1.0)
    q = float(np.sum(h_bottom * dz * w_edge * T[:, 0]))
    out_top = ~plate[:, -1]
    q += float(np.sum(h_top_out * dz * w_edge[out_top] * T[out_top, -1]))
    return q


def losses():
    cases = {}
    for label, kw in {"nominal (k 0.035, bottom h 6, top outside adiabatic)": {},
                      "foam k +20 %": {"k_foam": 0.042},
                      "bottom on a metal bench (h 50)": {"h_bottom": 50.0},
                      "foam top outside the plate jet-cooled (h 50)": {"h_top_out": 50.0}}.items():
        gp = foam_section(**kw)
        cases[label] = {"G_per_m_W_mK": round(gp, 4), "G_W_K": round(gp * (L + W), 4)}
    g_nom = cases["nominal (k 0.035, bottom h 6, top outside adiabatic)"]["G_W_K"]
    g_all = [c["G_W_K"] for c in cases.values()]
    unguarded = {"cases": cases,
                 "loss_fraction_of_hA": {f"h{h:g}": {"nominal": round(g_nom / (h * A), 4),
                                                     "range": [round(min(g_all) / (h * A), 4), round(max(g_all) / (h * A), 4)]}
                                         for h in (10.0, 100.0, 240.0)},
                 "note": "the loss is set by foam k, the bench under the foam and how the foam top beside the plate is cooled; "
                         "it cannot be separated from h by a still-air run (still-air h is itself unknown)"}

    air = props(40.0)
    k_air, k_rtv, k_nylon, k_cu = air["k"], 0.20, 0.25, 390.0
    perim = 2 * (L + W)
    res_fp = 2 * 0.010 * 0.016
    gap = {
        "side air gaps 1.0 mm x 3 mm plate edge": k_air * perim * 0.003 / 0.001,
        "RTV seal bead 1 x 1 mm over the side gap": k_rtv * perim * 0.001 / 0.001,
        "air under the plate, 7 mm": k_air * (A - res_fp) / 0.007,
        "air under the two resistor bodies, 1.5 mm": k_air * res_fp / 0.0015,
        "4 nylon M3 set-screw supports, 7 mm": 4 * k_nylon * math.pi / 4 * 0.003 ** 2 / 0.007,
        "4 resistor leads (0.4 mm2 Cu, 10 mm to the guard anchor)": 4 * k_cu * 0.4e-6 / 0.010,
        "radiation in the gaps (bare Al both sides, eps_eff 0.05)": 0.05 * 4 * SIGMA * 313.0 ** 3 * (A + perim * 0.003),
    }
    g_gap = sum(gap.values())
    null_k = 0.1
    guarded = {"G_gap_paths_W_K": {k: round(v, 5) for k, v in gap.items()}, "G_gap_W_K": round(g_gap, 4),
               "null_band_K": null_k,
               "residual_if_uncorrected_fraction_of_hA_dT": {f"h{h:g}": round(g_gap * null_k / (h * A * DT_PLAN), 4)
                                                              for h in (10.0, 100.0, 240.0)},
               "after_correction": "fit.py subtracts G_gap x (T_p - T_g) with G_gap from the guard-offset runs (PROCEDURE "
                                   "run G); +-30 % on that correction leaves <= 0.3 x the figures above"}
    return unguarded, guarded


def sizing_and_dynamics():
    rows = []
    for h in (5.0, 10.0, 60.0, 100.0, 167.0, 240.0):
        p = h * A * DT_PLAN
        v = math.sqrt(p * R_HEATER)
        rows.append({"h": h, "P_W": round(p, 3), "V": round(v, 2), "I_A": round(v / R_HEATER, 3),
                     "dT_max_at_0p8A": round(0.8 ** 2 * R_HEATER / (h * A), 1)})
    c_plate = PLATES["Al6061_3mm"]["rho_cp_t"] * A
    c_extra = 2 * 2.0e-3 * 800.0 + 0.5                      # two TO-220 (~2 g, cp ~800) + epoxy (estimate)
    c = c_plate + c_extra
    tau = {f"h{h:g}": round(c / (h * A), 1) for h in (10.0, 100.0, 240.0)}
    return {"heater": {"R_ohm": R_HEATER, "dT_plan_K": DT_PLAN, "ina226_I_max_A": round(INA_I_MAX, 3), "rows": rows,
                       "all_within_ina_range": all(r["I_A"] <= INA_I_MAX for r in rows)},
            "plate_heat_capacity_J_K": {"plate": round(c_plate, 2), "resistors_and_epoxy_est": round(c_extra, 2), "total": round(c, 2)},
            "tau_s": tau, "settle_7tau_min": {k: round(7 * v / 60, 1) for k, v in tau.items()}}


def radiation():
    t_m = 273.15 + 37.0
    return {f"eps{e:g}": round(4 * e * SIGMA * t_m ** 3, 2) for e in (0.03, 0.08, 0.15, 0.9)} | {
        "note": "h_rad = 4 eps sigma T_m^3 at T_m 37 C (rig: jet air ~24 C, plate ~49 C). Bare machined 6061 eps 0.03-0.15; "
                "solder mask ~0.9 (the product board, not counted by the model)"}


def air_heating():
    deliv = json.loads((HERE.parent / "delivery.json").read_text())
    pts = {round(r["drive"], 3): r for r in deliv["operating_points"]["S8"]["with_board"]}
    out = {}
    for d in (0.458, 0.55, 1.0):
        r = pts[d]
        q = r["board_cfm"] * 0.000471947
        rig = props(24.0)
        mcp = q * rig["rho"] * rig["cp"]
        out[f"drive_{d}"] = {"board_cfm": r["board_cfm"], "mdot_cp_W_K": round(mcp, 4),
                             "NTU_at_h_design": round(r["board_h_design"] * A / mcp, 3),
                             "NTU_at_h_est": round(r["board_h_est"] * A / mcp, 3)}
    ntu = [v[k] for v in out.values() for k in ("NTU_at_h_design", "NTU_at_h_est")]
    out["note"] = ("NTU = hA/(mdot cp): the spent air leaving the channel is heated by up to NTU x (mean plate rise). "
                   f"NTU {min(ntu)}-{max(ntu)} means the exit air is far from jet temperature, so h is referenced to "
                   "the jet supply (manifold) temperature, as Martin and delivery.py do; the exit-air thermocouple is only a "
                   "rough energy-balance check")
    return out


def main():
    iso = isothermality()
    unguarded, guarded = losses()
    dyn = sizing_and_dynamics()
    al = iso["Al6061_3mm"]
    fr4 = iso["FR4_2oz_coupon"]
    out = {"scope": __doc__.strip(), "versions": {"numpy": np.__version__, "scipy": scipy.__version__},
           "strip_m": [L, W], "area_m2": A, "tc_x_m": TC_X, "heaters_x_m": HEATERS,
           "A_isothermality": iso, "B_unguarded_losses": unguarded, "C_guarded": guarded, "D_E_sizing_dynamics": dyn,
           "F_radiation_h_W_m2K": radiation(), "G_air_heating": air_heating()}
    out["choice"] = {
        "plate": "Al6061_3mm",
        "why": (f"3-TC h error <= {al['worst_3TC_error']:.2%} under the stress pattern at h >= 100 (spreading length "
                f"{al['spreading_length_mm_at_h100']} mm >> 11 mm pitch). The FR-4 coupon's spreading length is "
                f"{fr4['spreading_length_mm_at_h100']} mm, longer than the 11 mm pitch, so local h is smeared out; its "
                f"temperature spread reaches {max(r['spread_over_rise'] for r in fr4['cases']):.0%} of the rise, and its "
                f"uniform-flux h differs from the isothermal h by up to {fr4['worst_3TC_error']:.1%} with no better area mean"),
        "guard": (f"unguarded foam loss is {unguarded['loss_fraction_of_hA']['h100']['nominal']:.1%} of hA at h 100 "
                  f"(range {unguarded['loss_fraction_of_hA']['h100']['range'][0]:.1%}-"
                  f"{unguarded['loss_fraction_of_hA']['h100']['range'][1]:.1%} over plausible conditions) and not separable "
                  f"from h; the guard leaves G_gap {guarded['G_gap_W_K']} W/K x <= 0.1 K = "
                  f"{guarded['residual_if_uncorrected_fraction_of_hA_dT']['h100']:.2%} of the plate power at h 100 before correction"),
    }
    (HERE / "plate-design.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"choice": out["choice"], "tau_s": dyn["tau_s"], "settle_min": dyn["settle_7tau_min"],
                      "heater": [(r["h"], r["P_W"], r["V"], r["I_A"]) for r in dyn["heater"]["rows"]],
                      "G_gap": guarded["G_gap_W_K"], "unguarded": unguarded["loss_fraction_of_hA"],
                      "rad": out["F_radiation_h_W_m2K"], "air": out["G_air_heating"]}, indent=1))


if __name__ == "__main__":
    main()
