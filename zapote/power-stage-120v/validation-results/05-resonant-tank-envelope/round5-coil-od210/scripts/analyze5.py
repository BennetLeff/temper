#!/usr/bin/env python3
"""Round 5 summary: coupling table, grid results per config, resonance extremes, capacitor
stress, and a first-harmonic (FHA) Monte Carlo yield calibrated against the ngspice grid.

ASSUMED. All maxima are maxima over evaluated cases, not bounds beyond them.
Writes outputs/summary5.json, outputs/config-summary.csv, outputs/class-power-120v.csv,
outputs/yield-mc.csv, outputs/coupling-table.csv.
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "outputs"
sys.path.insert(0, str(HERE))
import run_grid5 as G  # noqa: E402

RG, B4 = G.RG, G.B4
I_TANK_MAX, I_PS_HOLD, ETA = 22.0, 11.1, 0.93
SHUNT_MIN, FW_PEAK_LIMIT = 47.32, 45.0          # DECISIONS 2026-10-09 stage-13 Kelvin band low corner; fw tank-peak limit
SHARE_WORST = 1.1 / (1.1 + 4 * 0.9)             # one 0.10 uF part +10 %, four -10 % (K000)
I_PART_LIM = 5.97                               # A, TDK B3265*A p.57 I_RMS-vs-f, 85 C, 35 kHz, read by eye +/-10 % (bank review)
V_PART_AC = 500.0                               # Vac rating, B32654A1104 (DECISIONS 2026-10-09)
C_TOL = 0.10


def load_cases(cfg):
    p = OUT / f"grid5-{cfg}-cases.csv"
    if not p.exists():
        return None
    with open(p) as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k, v in r.items():
            try:
                r[k] = float(v)
            except ValueError:
                pass
    return rows


def full_power(r):
    cap = I_PS_HOLD * ETA * r["line_vrms"]
    return r["p_tank_w"] >= 0.99 * min(r["p_request_w"], cap)


def fres(p, C):
    return RG.f_res(p, C)


def fha_solve(p, C, V, P_req, kp=1.0, ki=1.0):
    """FHA analogue of RG.solve (corrected by ngspice/FHA ratios kp, ki). Returns (P, f, status)."""
    P_tgt = min(P_req, I_PS_HOLD * ETA * V)
    fr = fres(p, C)
    f0 = max(35e3, 1.05 * fr)
    if f0 > 60e3:
        return 0.0, f0, "NO_WINDOW"
    def ev(f):
        P, i, _ = RG.fha(p, C, V, f)
        return P * kp, i * ki

    def ok(f):
        P, i = ev(f)
        return P <= P_tgt * 1.0005 and i <= I_TANK_MAX

    if ok(f0):
        return ev(f0)[0], f0, "OK"
    if not ok(60e3):
        return ev(60e3)[0], 60e3, "BURST"
    lo, hi = f0, 60e3  # P and I fall monotonically with f above resonance
    while hi - lo > 10.0:
        mid = 0.5 * (lo + hi)
        lo, hi = (lo, mid) if ok(mid) else (mid, hi)
    return ev(hi)[0], hi, "OK"


def main():
    cpl = json.loads((OUT / "coupling.json").read_text())
    # ---- coupling table (central mu, with the mu 30-1000 spread)
    ctab = []
    by = defaultdict(list)
    for r in cpl["rows"]:
        by[(r["geom"], r["pan_d_mm"])].append(r)
    for (g, D), rs in sorted(by.items()):
        c = next(x for x in rs if x["mu_pan"] == 100.0)
        ctab.append({"geom": g, "pan_d_mm": D, "kl_mu100": c["kl"], "r_mu100": c["r_ohm_per_uH"],
                     "f_k_mu100": c["f_k"], "f_k_min": min(x["f_k"] for x in rs), "f_k_max": max(x["f_k"] for x in rs),
                     "f_r_mu100": c["f_r"], "f_r_min": min(x["f_r"] for x in rs), "f_r_max": max(x["f_r"] for x in rs)})
    with open(OUT / "coupling-table.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ctab[0].keys()))
        w.writeheader()
        w.writerows(ctab)
    geoms = {g: {k: v for k, v in gi.items() if k != "pans"} for g, gi in cpl["geoms"].items()}

    summ, cls_rows, cfg_rows, calib = {}, [], [], []
    for cfg, (geom, pan_d, l0) in G.CONFIGS.items():
        rows = load_cases(cfg)
        if rows is None:
            continue
        st_counts = Counter(r["status"] for r in rows)
        fp = [r for r in rows if full_power(r)]
        i_part = [r["i_tank_rms_a"] * SHARE_WORST for r in rows]
        vrms_part = max(r["vc_rms_v"] for r in rows)
        d = {
            "geom": geom, "pan_d_mm": pan_d, "L0_installed_uH": l0,
            "status": dict(st_counts), "full_power_cases": f"{len(fp)}/{len(rows)}",
            "full_power_120V": f"{sum(1 for r in fp if r['line_vrms'] == 120)}/{sum(1 for r in rows if r['line_vrms'] == 120)}",
            "f_res_kHz_range": [round(min(r["f_res_hz"] for r in rows) / 1e3, 2), round(max(r["f_res_hz"] for r in rows) / 1e3, 2)],
            "f_op_kHz_range": [round(min(r["freq_hz"] for r in rows) / 1e3, 2), round(max(r["freq_hz"] for r in rows) / 1e3, 2)],
            "f_over_fres_min": min(r["f_over_fres"] for r in rows),
            "f_over_fres_max_at_full_power": max((r["f_over_fres"] for r in fp), default=None),
            "fha_phase_min_deg": min(r["fha_phase_deg"] for r in rows),
            "i_edge_crest_min_A": min(r["i_edge_crest_a"] for r in rows),
            "floor_limited": st_counts.get("FLOOR_LIMITED", 0),
            "i_tank_rms_max_A": max(r["i_tank_rms_a"] for r in rows),
            "i_tank_pk_max_A": max(r["i_tank_pk_a"] for r in rows),
            "cases_pk_over_45A_fw_limit": sum(1 for r in rows if r["i_tank_pk_a"] > FW_PEAK_LIMIT),
            "margin_to_shunt_min_A": round(SHUNT_MIN - max(r["i_tank_pk_a"] for r in rows), 2),
            "vc_pk_max_V": max(r["vc_pk_v"] for r in rows), "vc_rms_max_V": vrms_part,
            "vc_rms_over_500Vac": round(vrms_part / V_PART_AC, 3),
            "cap_part_I_worst_A": round(max(i_part), 2),
            "cap_part_I_over_TDK_85C_35kHz": round(max(i_part) / I_PART_LIM, 3),
            "coil_loss_max_W": round(max(r["i_tank_rms_a"] ** 2 * r["param_Q40"] * r["param_L0U"]
                                         * (r["freq_hz"] / 40e3) ** r["param_GAMMA"] for r in rows), 1),
        }
        summ[cfg] = d
        cfg_rows.append({"config": cfg, **{k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in d.items()}})
        for r in rows:
            if r["line_vrms"] == 120:
                cls_rows.append({"config": cfg, "pan_class": r["pan_class"], "corner": r["corner"],
                                 "status": r["status"], "p_w": r["p_tank_w"], "full_power": full_power(r),
                                 "f_kHz": round(r["freq_hz"] / 1e3, 2), "f_res_kHz": round(r["f_res_hz"] / 1e3, 2),
                                 "i_rms_A": r["i_tank_rms_a"], "i_pk_A": r["i_tank_pk_a"]})
            # FHA calibration at the ngspice operating point
            p = {k[6:]: r[k] for k in r if k.startswith("param_")}
            P, i, _ = RG.fha(p, r["C_bank_uF"] * 1e-6, r["line_vrms"], r["freq_hz"])
            calib.append((r["p_tank_w"] / P, r["i_tank_rms_a"] / i))
    kp = st.median(c[0] for c in calib)
    ki = st.median(c[1] for c in calib)

    # ---- resonance extremes incl. tolerances (installed L0 +/-10 %, bank +/-10 %), central coupling
    res_ext = {}
    for cfg, (geom, pan_d, l0) in G.CONFIGS.items():
        fk, fr_ = G.factors(geom, pan_d)
        hi, lo, nom = 0, 1e9, []
        for name, pan in B4.PANS.items():
            pmin = G.pan_params(pan, "low", l0 * 0.9, fk, fr_)
            pmax = G.pan_params(pan, "high", l0 * 1.1, fk, fr_)
            hi = max(hi, fres(pmin, G.C_BANK * (1 - C_TOL)))
            lo = min(lo, fres(pmax, G.C_BANK * (1 + C_TOL)))
            nom.append(fres(G.pan_params(pan, "nom", l0, fk, fr_), G.C_BANK))
        res_ext[cfg] = {"f_res_nom_kHz": [round(min(nom) / 1e3, 2), round(max(nom) / 1e3, 2)],
                        "f_res_max_kHz (L0-10%, kl min, C-10%)": round(hi / 1e3, 2),
                        "f_res_min_kHz (L0+10%, kl max, C+10%)": round(lo / 1e3, 2),
                        "zvs_floor_max_kHz": round(1.05 * hi / 1e3, 2)}
        if cfg in summ:
            summ[cfg]["resonance_with_tolerances"] = res_ext[cfg]

    # ---- FHA Monte Carlo yield (uniform draws inside each class's ranges)
    rng = random.Random(20261010)
    N = 4000
    mc_rows = []
    for cfg, (geom, pan_d, l0) in G.CONFIGS.items():
        fk, fr_ = G.factors(geom, pan_d)
        for V in G.LINES:
            for name, pan in B4.PANS.items():
                ok = 0
                Ps = []
                for _ in range(N):
                    kl = 1 - (1 - rng.uniform(pan["kl40"][1], pan["kl40"][2])) * fk
                    p = {"L0U": l0 * rng.uniform(0.9, 1.1), "KL40": kl, "BETA": B4.COIL["beta_kl"][0],
                         "GAMMA": B4.COIL["gamma_coil"][0], "R40": rng.uniform(pan["r40"][1], pan["r40"][2]) * fr_,
                         "ALPHA": pan["alpha"]}
                    p["Q40"] = rng.uniform(0.168, 0.25) / p["L0U"]
                    C = G.C_BANK * rng.uniform(1 - C_TOL, 1 + C_TOL)
                    P, f, s = fha_solve(p, C, V, G.P_REQ, kp, ki)
                    tgt = min(G.P_REQ, I_PS_HOLD * ETA * V)
                    ok += P >= 0.99 * tgt
                    Ps.append(P)
                mc_rows.append({"config": cfg, "line_vrms": V, "pan_class": name, "yield_full_power": round(ok / N, 3),
                                "p_median_w": round(st.median(Ps)), "p_p05_w": round(sorted(Ps)[int(0.05 * N)])})
    with open(OUT / "yield-mc.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(mc_rows[0].keys()))
        w.writeheader()
        w.writerows(mc_rows)
    for cfg in summ:
        for V in G.LINES:
            ys = [r["yield_full_power"] for r in mc_rows if r["config"] == cfg and r["line_vrms"] == V]
            summ[cfg][f"mc_yield_{int(V)}V_mean_over_classes"] = round(sum(ys) / len(ys), 3)
        summ[cfg]["mc_yield_120V_by_class"] = {r["pan_class"]: r["yield_full_power"] for r in mc_rows
                                               if r["config"] == cfg and r["line_vrms"] == 120}

    # ---- L-target sweep (FHA MC, 120 V, all classes pooled equally), per geometry and pan diameter
    lsw = []
    for geom in ("d228_2sec", "d240_cont"):
        for pan_d in (180, 220, 260):
            fk, fr_ = G.factors(geom, pan_d)
            for l0 in range(45, 105, 5):
                ok = n = 0
                hi = 0.0
                for name, pan in B4.PANS.items():
                    hi = max(hi, fres(G.pan_params(pan, "low", l0 * 0.9, fk, fr_), G.C_BANK * (1 - C_TOL)))
                    for _ in range(800):
                        kl = 1 - (1 - rng.uniform(pan["kl40"][1], pan["kl40"][2])) * fk
                        p = {"L0U": l0 * rng.uniform(0.9, 1.1), "KL40": kl, "BETA": B4.COIL["beta_kl"][0],
                             "GAMMA": B4.COIL["gamma_coil"][0], "R40": rng.uniform(pan["r40"][1], pan["r40"][2]) * fr_,
                             "ALPHA": pan["alpha"]}
                        p["Q40"] = rng.uniform(0.168, 0.25) / p["L0U"]
                        C = G.C_BANK * rng.uniform(1 - C_TOL, 1 + C_TOL)
                        P, f, s_ = fha_solve(p, C, 120.0, G.P_REQ, kp, ki)
                        ok += P >= 0.99 * I_PS_HOLD * ETA * 120.0
                        n += 1
                lsw.append({"geom": geom, "pan_d_mm": pan_d, "L0_installed_uH": l0, "yield_120V": round(ok / n, 3),
                            "f_res_max_tol_kHz": round(hi / 1e3, 2), "zvs_floor_max_kHz": round(1.05 * hi / 1e3, 2)})
    with open(OUT / "l-sweep-mc.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(lsw[0].keys()))
        w.writeheader()
        w.writerows(lsw)

    for name, rows_, path in (("class", cls_rows, "class-power-120v.csv"), ("cfg", cfg_rows, "config-summary.csv")):
        with open(OUT / path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_[0].keys()))
            w.writeheader()
            w.writerows(rows_)
    out = {"status": "ASSUMED / pre-measurement; maxima over evaluated cases",
           "fha_calibration": {"p_ngspice_over_fha_median": round(kp, 4), "i_ngspice_over_fha_median": round(ki, 4),
                               "p_ratio_range": [round(min(c[0] for c in calib), 4), round(max(c[0] for c in calib), 4)],
                               "i_ratio_range": [round(min(c[1] for c in calib), 4), round(max(c[1] for c in calib), 4)]},
           "constants": {"share_worst": SHARE_WORST, "I_part_limit_A_85C_35kHz": I_PART_LIM,
                         "shunt_min_A": SHUNT_MIN, "fw_peak_limit_A": FW_PEAK_LIMIT, "mc_draws": N},
           "geometries": geoms, "configs": summ}
    (OUT / "summary5.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["fha_calibration"]))
    for cfg, d in summ.items():
        print(cfg, {k: d[k] for k in ("full_power_120V", "f_res_kHz_range", "f_op_kHz_range", "f_over_fres_min",
                                      "i_tank_pk_max_A", "cap_part_I_over_TDK_85C_35kHz", "mc_yield_120V_mean_over_classes")})
        print("   ", d["resonance_with_tolerances"], d["status"])


if __name__ == "__main__":
    main()
