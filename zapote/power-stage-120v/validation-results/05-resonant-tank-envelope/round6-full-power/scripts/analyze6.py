#!/usr/bin/env python3
"""Round 6 analysis: ngspice grid summary per configuration, FHA calibration against it, and the Monte Carlo
'required tank current' distribution that gives full-power yield at any RMS ceiling. ASSUMED.

Yield definition (round 5): a draw reaches full power when it delivers >= 99 % of min(1710 W request,
11.1 A x 0.93 x V) -> 1239 W at 120 V, 1115 W at 108 V. Draws are uniform inside each class's ranges
(round 4 basis rescaled by the round-5 coupling ratios), L0 +/-10 %, C +/-10 %, R_ac 0.168-0.25 ohm at 40 kHz.

For each draw the MC finds the LOWEST legal frequency that delivers the target (P falls monotonically with f
above resonance) and the line-cycle tank RMS there: I_req. Yield at a ceiling I_max is P(I_req <= I_max).
Draws that the window floor max(35 kHz, 1.05 f_res) cannot bring to the target have I_req = inf
(FLOOR-limited: no ceiling helps them). The peak-limited yield adds kpk(Q) x I_req <= peak limit, with kpk the
ngspice tank-peak / line-RMS ratio fitted against the loaded Q at the operating point.

Writes outputs/config-summary6.csv, calibration6.json, yield-by-class.csv, yield-pooled.csv, ireq-percentiles.csv,
summary6.json.
"""
from __future__ import annotations

import csv
import glob
import json
import math
from collections import Counter, defaultdict

import numpy as np

import common6 as M
import fha6 as F

OUT = M.OUT
N_MC = 4000
SEED = 20261010
PEAK_LIMITS = [45.0, 50.56 - 3.0, 55.0, 60.0]      # fw today; CT minimum less the 3 A pickup stack; two raised settings
# bank arrangements: C_bank -> (n parts, part nF)
BANKS = {0.50: (5, 100), 0.40: (4, 100), 0.45: (3, 150), 0.60: (4, 150), 0.30: (3, 100), 0.35: (7, 47)}


def load_rows():
    rows = []
    for p in sorted(glob.glob(str(OUT / "grid6-*-cases.csv"))):
        for r in csv.DictReader(open(p)):
            for k, v in list(r.items()):
                try:
                    r[k] = float(v)
                except (TypeError, ValueError):
                    pass
            rows.append(r)
    return rows


def full_power(r):
    cap = M.I_PS_HOLD * M.ETA * r["line_vrms"]
    return r["p_tank_w"] >= 0.99 * min(r["p_request_w"], cap)


def q_at(r):
    return 2 * math.pi * r["freq_hz"] * r["L_eq_uH"] * 1e-6 / r["R_eq_ohm"]


def bank_part_ratio(r):
    n, nf = BANKS[round(r["C_bank_uF"], 2)]
    share = M.worst_share(n, 1.0)
    return r["i_tank_rms_a"] * share / M.tdk_limit(nf, r["freq_hz"]), r["i_tank_rms_a"] * share


def config_summary(rows):
    meta = json.loads((OUT / "grid6-configs.json").read_text())
    by = defaultdict(list)
    for r in rows:
        by[r["config"]].append(r)
    out = []
    for cfg, rs in by.items():
        m = meta[cfg]
        st = Counter(r["status"] for r in rs)
        ratios = [bank_part_ratio(r) for r in rs]
        d = {"config": cfg, "geom": m["geom"], "L_free_uH": m["L_free_uH"], "L0_installed_uH": m["L0_installed_uH"],
             "C_bank_uF": m["C_bank_uF"], "I_max_A": m["I_tank_max_A"], "pan_d_mm": m["pan_d_mm"],
             "status": json.dumps(dict(st)),
             "full_power_108V": f"{sum(full_power(r) for r in rs if r['line_vrms'] == 108)}/15",
             "full_power_120V": f"{sum(full_power(r) for r in rs if r['line_vrms'] == 120)}/15",
             "p_120V_min_W": round(min(r["p_tank_w"] for r in rs if r["line_vrms"] == 120)),
             "p_120V_median_W": round(float(np.median([r["p_tank_w"] for r in rs if r["line_vrms"] == 120]))),
             "f_res_nom_kHz_min": round(min(r["f_res_hz"] for r in rs if r["corner"] == "nom") / 1e3, 2),
             "f_res_nom_kHz_max": round(max(r["f_res_hz"] for r in rs if r["corner"] == "nom") / 1e3, 2),
             "f_op_kHz_min": round(min(r["freq_hz"] for r in rs) / 1e3, 2),
             "f_op_kHz_max": round(max(r["freq_hz"] for r in rs) / 1e3, 2),
             "f_over_fres_min": min(r["f_over_fres"] for r in rs),
             "fha_phase_min_deg": min(r["fha_phase_deg"] for r in rs),
             "i_edge_crest_min_A": min(r["i_edge_crest_a"] for r in rs),
             "floor_limited": st.get("FLOOR_LIMITED", 0), "burst_required": st.get("BURST_REQUIRED", 0),
             "i_rms_max_A": max(r["i_tank_rms_a"] for r in rs),
             "i_pk_max_A": max(r["i_tank_pk_a"] for r in rs),
             "n_pk_over_45A": sum(r["i_tank_pk_a"] > M.FW_PEAK for r in rs),
             "n_pk_over_shunt_min": sum(r["i_tank_pk_a"] > M.SHUNT_BAND[0] for r in rs),
             "n_pk_over_ct_min": sum(r["i_tank_pk_a"] > M.CT_BAND[0] for r in rs),
             "vc_rms_max_V": max(r["vc_rms_v"] for r in rs), "vc_pk_max_V": max(r["vc_pk_v"] for r in rs),
             "cap_part_I_worst_A": round(max(x[1] for x in ratios), 2),
             "cap_part_over_TDK85C_at_f_max": round(max(x[0] for x in ratios), 3),
             "coil_loss_max_W_at_Rac0.25": round(max(r["i_tank_rms_a"] ** 2 * 0.25 * (r["freq_hz"] / 40e3) ** 0.55
                                                     for r in rs), 1),
             "r5_W_max": round(max(r["i_tank_rms_a"] for r in rs) ** 2 * M.R5_OHM, 3)}
        out.append(d)
    out.sort(key=lambda d: (d["geom"], d["L_free_uH"], d["C_bank_uF"], d["pan_d_mm"], d["I_max_A"]))
    with open(OUT / "config-summary6.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    return out


def calibrate(rows):
    kp, ki, kq, kk = [], [], [], []
    for r in rows:
        p = {k[6:]: r[k] for k in r if str(k).startswith("param_")}
        P, i, _ = M.RG.fha(p, r["C_bank_uF"] * 1e-6, r["line_vrms"], r["freq_hz"])
        kp.append(r["p_tank_w"] / P)
        ki.append(r["i_tank_rms_a"] / i)
        kq.append(q_at(r))
        kk.append(r["i_tank_pk_a"] / r["i_tank_rms_a"])
    kq, kk = np.array(kq), np.array(kk)
    b, a = np.polyfit(kq, kk, 1)
    resid = kk - (a + b * kq)
    cal = {"n": len(rows), "kp_median": float(np.median(kp)), "kp_range": [float(min(kp)), float(max(kp))],
           "ki_median": float(np.median(ki)), "ki_range": [float(min(ki)), float(max(ki))],
           "kpk_fit": {"a": float(a), "b_per_Q": float(b), "resid_max": float(resid.max()),
                       "resid_min": float(resid.min()), "use": "kpk = a + b*Q + resid_max (conservative)"},
           "kpk_range": [float(kk.min()), float(kk.max())], "Q_range": [float(kq.min()), float(kq.max())]}
    (OUT / "calibration6.json").write_text(json.dumps(cal, indent=1) + "\n")
    return cal


MC_CONFIGS = [  # (L free, C uF, label)
    (70, 0.50, "R34 70 uH, 0.50 uF (today)"),
    (70, 0.40, "70 uH, 0.40 uF"),
    (80, 0.50, "80 uH, 0.50 uF"),
    (80, 0.45, "80 uH, 0.45 uF (3 x 150 nF)"),
    (80, 0.40, "80 uH, 0.40 uF"),
    (90, 0.50, "90 uH, 0.50 uF"),
    (90, 0.40, "90 uH, 0.40 uF"),
]


def mc(cal):
    kp, ki = cal["kp_median"], cal["ki_median"]
    a, b, rmax = cal["kpk_fit"]["a"], cal["kpk_fit"]["b_per_Q"], cal["kpk_fit"]["resid_max"]
    by_class, pooled, pct = [], [], []
    store = {}
    for lfree, c_uf, label in MC_CONFIGS:
        for pan_d in M.PAN_D:
            fk, fr = M.coupling(M.GEOM, pan_d)
            for V in (108.0, 120.0):
                rng = np.random.default_rng([SEED, lfree, int(c_uf * 100), pan_d, int(V)])
                tgt = min(M.P_REQ, M.I_PS_HOLD * M.ETA * V)
                allI, allPk, allF = [], [], []
                for name, pan in M.B4.PANS.items():
                    d = F.draws(pan, N_MC, rng, M.L_INSTALLED[lfree], fk, fr, c_uf * 1e-6)
                    i, f, st, fres = F.required_current(d, V, 0.99 * tgt, kp, ki)
                    L, R = F.lr(d, f)
                    Q = 2 * np.pi * f * L / R
                    ipk = (a + b * Q + rmax) * i
                    coil = np.where(np.isfinite(i), i ** 2 * d["rac"] * (f / 40e3) ** F.GAMMA, np.nan)
                    row = {"L_free_uH": lfree, "C_bank_uF": c_uf, "pan_d_mm": pan_d, "line_vrms": V, "pan_class": name,
                           "floor_limited": round(float((st == 2).mean()), 3),
                           "I_req_p50_A": round(float(np.percentile(i, 50)), 2),
                           "I_req_p90_A": round(float(np.percentile(i, 90)), 2) if np.isfinite(np.percentile(i, 90)) else "inf",
                           "f_op_med_kHz": round(float(np.median(f)) / 1e3, 2), "f_res_med_kHz": round(float(np.median(fres)) / 1e3, 2)}
                    for imax in M.CEILINGS:
                        row[f"yield_{int(imax)}A"] = round(float((i <= imax).mean()), 3)
                    for imax in M.CEILINGS:
                        row[f"yield_{int(imax)}A_pk45"] = round(float(((i <= imax) & (ipk <= 45.0)).mean()), 3)
                    by_class.append(row)
                    allI.append(i)
                    allPk.append(ipk)
                    allF.append(f)
                    store[(lfree, c_uf, pan_d, V, name)] = (i, ipk, f, coil)
                I = np.concatenate(allI)
                PK = np.concatenate(allPk)
                prow = {"L_free_uH": lfree, "C_bank_uF": c_uf, "config": label, "pan_d_mm": pan_d, "line_vrms": V,
                        "floor_limited": round(float(np.isinf(I).mean()), 3)}
                for imax in M.CEILINGS:
                    prow[f"yield_{int(imax)}A"] = round(float((I <= imax).mean()), 3)
                for pl in PEAK_LIMITS:
                    for imax in (22.0, 26.0, 28.0, 30.0):
                        prow[f"yield_{int(imax)}A_pk{pl:g}"] = round(float(((I <= imax) & (PK <= pl)).mean()), 3)
                pooled.append(prow)
                pr = {"L_free_uH": lfree, "C_bank_uF": c_uf, "pan_d_mm": pan_d, "line_vrms": V}
                for q in (50, 70, 80, 85, 90):
                    v = np.percentile(I, q)
                    pr[f"I_req_p{q}_A"] = round(float(v), 2) if np.isfinite(v) else "inf"
                    vpk = np.percentile(PK, q)
                    pr[f"I_pk_p{q}_A"] = round(float(vpk), 1) if np.isfinite(vpk) else "inf"
                pct.append(pr)
            # all three diameters pooled (equal weight)
        for V in (108.0, 120.0):
            I = np.concatenate([store[(lfree, c_uf, d_, V, n)][0] for d_ in M.PAN_D for n in M.B4.PANS])
            PK = np.concatenate([store[(lfree, c_uf, d_, V, n)][1] for d_ in M.PAN_D for n in M.B4.PANS])
            prow = {"L_free_uH": lfree, "C_bank_uF": c_uf, "config": label, "pan_d_mm": "180/220/260",
                    "line_vrms": V, "floor_limited": round(float(np.isinf(I).mean()), 3)}
            for imax in M.CEILINGS:
                prow[f"yield_{int(imax)}A"] = round(float((I <= imax).mean()), 3)
            for pl in PEAK_LIMITS:
                for imax in (22.0, 26.0, 28.0, 30.0):
                    prow[f"yield_{int(imax)}A_pk{pl:g}"] = round(float(((I <= imax) & (PK <= pl)).mean()), 3)
            pooled.append(prow)
            pr = {"L_free_uH": lfree, "C_bank_uF": c_uf, "pan_d_mm": "180/220/260", "line_vrms": V}
            for q in (50, 70, 80, 85, 90):
                v = np.percentile(I, q)
                pr[f"I_req_p{q}_A"] = round(float(v), 2) if np.isfinite(v) else "inf"
                vpk = np.percentile(PK, q)
                pr[f"I_pk_p{q}_A"] = round(float(vpk), 1) if np.isfinite(vpk) else "inf"
            pct.append(pr)
    for name, rows in (("yield-by-class.csv", by_class), ("yield-pooled.csv", pooled), ("ireq-percentiles.csv", pct)):
        with open(OUT / name, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return by_class, pooled, pct, store


def coil_loss_table(store):
    """Coil loss at the operating point of draws that reach full power within each ceiling (R_ac as drawn)."""
    out = []
    for (lfree, c_uf, pan_d, V, name), (i, ipk, f, coil) in store.items():
        if pan_d != 220 or V != 120.0:
            continue
        for imax in (22.0, 26.0, 28.0):
            m = i <= imax
            out.append({"L_free_uH": lfree, "C_bank_uF": c_uf, "pan_class": name, "I_max_A": imax,
                        "coil_loss_p50_W": round(float(np.median(coil[m])), 1) if m.any() else "",
                        "coil_loss_max_W": round(float(np.max(coil[m])), 1) if m.any() else ""})
    with open(OUT / "coil-loss-mc.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)


def main():
    rows = load_rows()
    cs = config_summary(rows)
    cal = calibrate(rows)
    by_class, pooled, pct, store = mc(cal)
    coil_loss_table(store)
    summ = {"status": "ASSUMED / pre-measurement. Model results on the round-4/5 basis; maxima are over evaluated cases.",
            "n_grid_cases": len(rows), "calibration": cal, "mc_draws_per_class": N_MC, "seed": SEED,
            "pooled_120V": [p for p in pooled if p["line_vrms"] == 120.0],
            "percentiles": pct}
    (OUT / "summary6.json").write_text(json.dumps(summ, indent=1) + "\n")
    print(json.dumps(cal, indent=1))
    for p in pooled:
        print({k: p[k] for k in ("config", "pan_d_mm", "line_vrms", "floor_limited", "yield_22A", "yield_24A",
                                 "yield_26A", "yield_28A", "yield_30A", "yield_22A_pk45", "yield_26A_pk45")})


if __name__ == "__main__":
    main()
