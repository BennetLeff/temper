#!/usr/bin/env python3
"""Round 6, question 2: what each tank RMS ceiling asks of the board, coil and protection. ASSUMED / estimates.

Inputs (read-only; nothing here edits a board, source or firmware file):
  * tank copper: task 04 round 5 (validation-results/04-board-current-thermal/round5-native21/README.md): one
    2 oz (70 um) outer layer per leg; SW_A narrowest long section 7.0 mm (12 mm long), SW_B long sections 8.1-8.5 mm
    (stage 6 fix), SW_B short necks 3.1-6 mm over 4-6 mm; path resistances (stage 13): SW_A 4.146 mOhm,
    SW_B 7.08 / 6.88 mOhm, RES_A 0.668, coil feed 0.410 (18 um plating). Screen: IPC-2221 external,
    I = 0.048 dT^0.44 A^0.725 (A in mil^2), 20 K.
  * R5 1.0 mOhm / 1 W (DECISIONS 2026-10-08: 1 W good to 31.6 A).
  * CT T1 1:100 into 1.5 ohm (round 4 s.2); thermal reference 88 A RMS; CT_MON rail +/-110 A.
  * OCP bands (brief): shunt 47.33-97.77 A, CT 50.56-60.01 A, firmware peak trip 45 A (n21_binding.c, capped < 50.9 A
    by config_ok()); OCP-loop coil pickup stack 3.0 A (DECISIONS 2026-10-09 item 9).
  * Tank peaks per ceiling: this round's ngspice grid (config-summary6.csv).
  * Bank: TDK p.57 (outputs/tdk-p57-1600v.csv) at the worst +/-10 % share.
  * Coil cooling: enclosure R33 study 09 coil_thermal.py (imported read-only, 'R34 as modelled' variant from its
    run_variants.sh), R_ac <= 0.25 ohm at 40 kHz / 100 C -> R25 = 0.25 / (1 + 0.00393 x 75), scaled by (f/40k)^0.55.
  * MOSFETs and sink: R33 thermal/requirement.py solve() (D-18 loss model, basis A conservative switching proxy;
    basis B ZVS estimate), R_SA 0.29 C/W + 0.0161 pedestal, 13 CFM, R_cs 0.634, 50 C inlet, Tj target 125 C.
Writes outputs/board-side.json and board-side-*.csv.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from pathlib import Path

import common6 as M

OUT = M.OUT
R33 = Path("/Users/bennet/Desktop/temper/output/temper-r33-studies/09-coil-210-strayfield/thermal")
CEIL = [22.0, 24.0, 26.0, 28.0, 30.0]
T_MIL = 70e-3 / 0.0254                     # 2 oz in mil
K_EXT = 0.048


def ipc_dt(i, w_mm):
    a = w_mm / 0.0254 * T_MIL
    return (i / (K_EXT * a ** 0.725)) ** (1 / 0.44)


def ipc_width(i, dt=20.0):
    a = (i / (K_EXT * dt ** 0.44)) ** (1 / 0.725)
    return a / T_MIL * 0.0254


def copper():
    secs = [("SW_A F.Cu narrowest long section (12 mm)", 7.0), ("SW_B B.Cu long sections, narrow end", 8.1),
            ("SW_B B.Cu long sections, wide end", 8.5), ("SW_B short necks (4-6 mm long), narrowest", 3.1)]
    paths = {"SW_A": 4.146e-3, "SW_B (high)": 7.08e-3, "RES_A": 0.668e-3, "coil feed": 0.410e-3}
    rows = []
    for name, w in secs:
        r = {"section": name, "width_mm": w}
        for i in CEIL:
            r[f"dT_{int(i)}A_K"] = round(ipc_dt(i, w), 1)
        rows.append(r)
    need = {f"{int(i)}A": round(ipc_width(i), 2) for i in CEIL}
    loss = {p: {f"{int(i)}A": round(i * i * R, 2) for i in CEIL} for p, R in paths.items()}
    return rows, need, loss


def protection():
    cs = list(csv.DictReader(open(OUT / "config-summary6.csv")))
    out = []
    for i in CEIL:
        rs = [r for r in cs if float(r["I_max_A"]) == i and r["geom"] == M.GEOM]
        pk = max(float(r["i_pk_max_A"]) for r in rs)
        need = pk + 3.0 + 2.0                 # pickup stack + 2 A detection margin (estimate)
        out.append({"I_max_A": i, "configs": len(rs), "tank_pk_max_A": round(pk, 2),
                    "pk_over_rms": round(pk / i, 3),
                    "fw_45A_ok": pk <= 45.0, "ct_min_50.56_ok": pk + 3.0 <= M.CT_BAND[0],
                    "shunt_min_47.33_ok": pk + 3.0 <= M.SHUNT_BAND[0],
                    "trip_floor_needed_A": round(need, 1),
                    "ct_band_scale": round(need / M.CT_BAND[0], 3),
                    "ct_band_if_scaled_A": [round(M.CT_BAND[0] * need / M.CT_BAND[0], 1), round(M.CT_BAND[1] * need / M.CT_BAND[0], 1)],
                    "shunt_band_if_scaled_A": [round(need, 1), round(M.SHUNT_BAND[1] * need / M.SHUNT_BAND[0], 1)],
                    "ct_sec_pk_V": round(pk / 100 * 1.5, 3), "ct_mon_headroom_A": round(110 - pk, 1),
                    "ct_rms_over_88A": round(i / M.CT_RATED_A, 3),
                    "r5_W": round(i * i * M.R5_OHM, 3), "r5_over_1W": round(i * i * M.R5_OHM / M.R5_RATED_W, 3),
                    "vc_rms_max_V": max(float(r["vc_rms_max_V"]) for r in rs),
                    "vc_pk_max_V": max(float(r["vc_pk_max_V"]) for r in rs),
                    "cap_part_over_TDK85C_max": max(float(r["cap_part_over_TDK85C_at_f_max"]) for r in rs
                                                     if float(r["C_bank_uF"]) == 0.5),
                    "f_op_max_kHz": max(float(r["f_op_kHz_max"]) for r in rs)})
    return out


def bank():
    rows = []
    for label, n, nf in (("5 x B32654A1104 (0.50 uF, today)", 5, 100), ("4 x B32654A1104 (0.40 uF)", 4, 100),
                         ("3 x B32654A1154 (0.45 uF)", 3, 150), ("4 x B32654A1154 (0.60 uF)", 4, 150),
                         ("6 x B32654A1104 (0.60 uF; 90 mm, does not fit the slot)", 6, 100)):
        share = M.worst_share(n, 1.0)
        r = {"bank": label, "worst_share": round(share, 3)}
        for f in (35e3, 40e3, 45e3, 50e3):
            i85 = M.tdk_limit(nf, f) / share
            r[f"tank_A_85C_{int(f / 1e3)}k"] = round(i85, 1)
            r[f"tank_A_60C_est_{int(f / 1e3)}k"] = round(i85 * math.sqrt(45 / 20), 1)
        rows.append(r)
    return rows


def coil():
    os.environ["CT_VARIANT"] = json.dumps({"name": "R34 as modelled: gap at r80-92 over the J5 drop, 8x20",
                                           "sections": [[0.026, 0.080], [0.092, 0.114]], "bars": [8, 0.020],
                                           "N_J": 135, "S_J": 0.013})
    sys.path.insert(0, str(R33))
    import coil_thermal as CT  # noqa: E402  (read-only import; main() is not run)
    full = CT.op(1.0)
    rows = []
    for rac100, label in ((0.25, "spec R_ac <= 0.25 ohm @100 C"), (0.25 * 76 / 66.5, "80 uH, same window (R ~ N^2)"),
                          (0.25 * 85.5 / 66.5, "90 uH, same window (R ~ N^2)")):
        for f in (40e3, 45e3, 50e3):
            r25 = rac100 / (1 + 0.00393 * 75) * (f / 40e3) ** 0.55
            row = {"coil": label, "R_ac40_100C_ohm": round(rac100, 3), "f_kHz": f / 1e3, "R25_at_f_ohm": round(r25, 4)}
            for i in CEIL:
                c = CT.coil_temp(i, r25, 110.0, 50.0, full["coil_cfm"])
                c6 = CT.coil_temp(i, r25, 110.0, 50.0, full["coil_cfm"], 0.6)
                row[f"Tw_{int(i)}A_C"] = c["T_winding_C"] if c and "T_winding_C" in c else "runaway"
                row[f"Tw_{int(i)}A_h0.6_C"] = c6["T_winding_C"] if c6 and "T_winding_C" in c6 else "runaway"
                row[f"loss_{int(i)}A_W"] = c["Q_gen_W"] if c and "Q_gen_W" in c else ""
            lo, hi = 5.0, 45.0
            for _ in range(40):
                m = (lo + hi) / 2
                c = CT.coil_temp(m, r25, 110.0, 50.0, full["coil_cfm"], 0.6)
                ok = c and "T_winding_C" in c and c["T_winding_C"] <= 150 and c["T_ferrite_C_est"] <= 140
                lo, hi = (m, hi) if ok else (lo, m)
            row["I_max_sustained_fullspeed_h0.6_A"] = round(lo, 1)
            lo, hi = 5.0, 45.0
            for _ in range(40):
                m = (lo + hi) / 2
                c = CT.coil_temp(m, r25, 110.0, 50.0, full["coil_cfm"])
                ok = c and "T_winding_C" in c and c["T_winding_C"] <= 150 and c["T_ferrite_C_est"] <= 140
                lo, hi = (m, hi) if ok else (lo, m)
            row["I_max_sustained_fullspeed_h1.0_A"] = round(lo, 1)
            rows.append(row)
    # reproduction of R33's own figure for this variant (maxR 0.318 at 25 C, 22 A, full speed)
    c = CT.coil_temp(22.0, 0.318, 110.0, 50.0, full["coil_cfm"])
    return rows, {"full_speed_op": full, "check_22A_R25_0.318": c}


def fets():
    sys.path.insert(0, str(R33))
    import requirement as RQ  # noqa: E402
    order = ("Q5", "Q6", "Q3", "Q2", "BR1")
    rows = []
    for i in CEIL:
        for f in (40e3, 45e3, 50e3):
            for V, P in ((120.0, 1239.0), (108.0, 1115.0)):
                case = {"frequency_hz": f, "i_rms_a": i, "target_w": P, "vrms_v": V}
                r = RQ.solve(case, 50.0, 0.29 + RQ.R_PED, 0.634, 13, order, 0.378)
                cond = i * i / 2 * RQ.rds(r["max_tj"])
                # basis B (m11 ZVS estimate), isothermal sink at 0.29 + pedestal
                p_fet = 6.78 * (i / 21.47) ** 2 + 0.33
                p_br1 = 2 * 1.05 * 0.9 * (P / (0.95 * V))
                p_sink_b = 2 * (p_fet - 0.07) + 2 * p_fet + p_br1
                tj_b = 50.0 + (0.29 + RQ.R_PED) * p_sink_b + p_fet * (0.28 + 0.634)
                lo, hi = 0.0, 1.0
                for _ in range(40):
                    mid = (lo + hi) / 2
                    rr = RQ.solve(case, 50.0, mid, 0.634, 13, order, 0.378)
                    lo, hi = (mid, hi) if (rr and rr["max_tj"] <= RQ.TJ_MAX) else (lo, mid)
                rows.append({"I_tank_A": i, "f_kHz": f / 1e3, "line_V": V, "A_tj_max_C": round(r["max_tj"], 1),
                             "A_RSA_max_for_125C_excl_pedestal": round(lo - RQ.R_PED, 3),
                             "A_worst": r["worst"], "A_sink_W": round(r["psink"], 1),
                             "A_fet_cond_W_hot": round(cond, 2), "B_fet_W": round(p_fet, 2),
                             "B_sink_W": round(p_sink_b, 1), "B_tj_C": round(tj_b, 1)})
    return rows


def write(name, rows):
    with open(OUT / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    cu, need, loss = copper()
    prot = protection()
    bk = bank()
    co, cchk = coil()
    fe = fets()
    write("board-side-copper.csv", cu)
    write("board-side-protection.csv", prot)
    write("board-side-bank.csv", bk)
    write("board-side-coil.csv", co)
    write("board-side-fets.csv", fe)
    out = {"status": "ASSUMED / estimates", "ipc2221_width_for_20K_mm": need, "copper_loss_W": loss,
           "coil_model_check": cchk}
    (OUT / "board-side.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(out, indent=1, default=str))
    for t in (cu, prot, bk, co, fe):
        for r in t:
            print(r)


if __name__ == "__main__":
    main()
