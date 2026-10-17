#!/usr/bin/env python3
"""First-order estimates behind README.md. Reads committed files of the ps-integrate tree (read-only); prints and writes
results/estimates.json. Every input is a cited committed value; every output is an ESTIMATE (no re-solve).
    python3 -I estimates.py
"""
import json, math
from pathlib import Path
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
VR = PS / "validation-results"
R5 = VR / "04-board-current-thermal/round5-native21"
A = 0.00393
f = lambda T: 1 + A * (T - 20.0)             # rho(T)/rho(20 C)
J = lambda p: json.loads((PS / p).read_text())
out = {}

# E1 B3 release margins after the committed first-order TCR step (heat-attribution results.json)
ha = J("validation-results/04-board-current-thermal/round5-native21/heat-attribution-2026-10-15/results.json")
mg = J("validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json")
dk = ha["copper_tcr_first_order"]["dK_c18_bay61"]
rows = {r["item"].split(":")[0] + (" terminal" if "terminal" in r["item"] else "") + (" body" if r["item"].startswith("C") else ""): r for r in mg["cases"]["c18_h10"]}
e1 = {}
for k, add in dk.items():
    for r in mg["cases"]["c18_h10"]:
        key = r["item"]
        if (k.startswith("C40") and key.startswith("C40")) or (k.startswith("C41") and key.startswith("C41")) or \
           (k.startswith("R10") and key.startswith("R10: 2512 terminal")) or (k.startswith("R20") and key.startswith("R20: 2512 terminal")) or \
           (k.startswith("laminate") and key.startswith("laminate: 1 mm")):
            e1[k] = {"margin_K_20C": r["margin_k"], "add_K": round(add, 2), "margin_K_after": round(r["margin_k"] - add, 2)}
out["E1_b3_release_c18_bay61"] = e1
out["E1_ceiling_bay61"] = ha["copper_tcr_first_order"]["ceiling_bay61"]

# E2 copper temperature at c28: bounds
tw = {k: v["T_w_C"] for k, v in ha["copper_tcr_first_order"]["fields"].items()}
c28 = {r["item"]: r["est_c"] for r in mg["cases"]["c28_h10"]}
peak28 = max(c28["laminate: 1 mm-block copper peak"], c28["laminate: FET-row copper"])
scale = (29.4 / 18.9) ** 2
lo = 55.0 + scale * (min(tw.values()) - 61.0)
out["E2_c28_copper_temperature"] = {"c18_heat_weighted_C": [min(tw.values()), max(tw.values())], "I2_scale_c28_over_c18": round(scale, 3),
    "naive_low_C": round(lo, 0), "upper_bound_C_b3_c28_copper_peak": peak28,
    "rho_factor_range": [round(f(lo), 2), round(f(peak28), 2)],
    "note": "ESTIMATE: low = bay 55 + (29.4/18.9)^2 x (smallest c18 heat-weighted rise over bay 61); high = B3 c28 copper peak (margins.json), which no heat-weighted mean can exceed"}

# E3 G6 R5 derating headroom
g6 = J("validation-results/04-board-current-thermal/round5-native21/stage17-r5/g6.json")
head = 148.39 - g6["r5"]["pad_cell_max_c"]
rise = g6["trip_band"]["r5_rise_k"]
e3 = {"pad_max_c": g6["r5"]["pad_cell_max_c"], "bound_c": 148.39, "headroom_K": round(head, 2), "pad_rise_K": rise}
for s in (f(peak28) , f(lo)):
    e3[f"copper_share_that_flips_at_rho_x{round(s,2)}"] = round(head / (rise * (s - 1)), 2)
out["E3_G6_R5_derating_c28_h25"] = e3
out["E3_note"] = ("ESTIMATE: pad rise x copper share x (rho factor - 1) >= headroom flips G6. The share is unknown without a re-solve; "
                  "b3-ratings c18/c22/c28 R5 rows (57.3 / 75.9 / 107.5 K at bay 61/55/55) fit 20 K fixed + 0.1 K/A^2, so the I^2 part is most of the rise")

# E4 OCP band: R5 alloy TCR vs the B3 rise
lo_edge = g6["trip_band"]["before_kelvin_a"][0]
out["E4_ocp_band"] = {"band_low_before_kelvin_A": lo_edge, "tcr_ppm": 75, "A_per_K": round(lo_edge * 75e-6, 5),
    "extra_pad_rise_0_to_20K_A": [0.0, round(lo_edge * 75e-6 * 20, 3)], "after_kelvin_low_A": g6["trip_band"]["low_after_kelvin_bound_a"],
    "floor_A": 64.17, "margin_A": round(g6["trip_band"]["low_after_kelvin_bound_a"] - 64.17, 2)}

# E5 Kelvin plane 125 C vs local copper temperature
kb = J("validation-results/02-protection-timing/kelvin/budget-native21s44.json")
sh = kb["trip_shift_A"]
k5 = {}
for name, T in (("R5 pad c28 h25 (g6.json)", 134.87), ("R5 row c28 h10 bay 55 (margins.json)", 162.5)):
    r = f(T) / f(125.0)
    k5[name] = {"T_C": T, "e_th_scale": round(r, 4), "trip_shift_A": round(sh * r, 3), "band_low_A": round(kb["band_before_A"][0] + sh * r, 2)}
out["E5_kelvin_plane"] = {"band_low_A_at_125C": kb["band_after_A"][0], "floor_A": kb["floor_A"], "margin_A": round(kb["band_after_A"][0] - kb["floor_A"], 2),
                          "hotter_local_copper": k5, "colder_than_125C": {"T_C": 85, "e_th_scale": round(f(85) / f(125), 3)}}

# E6 fuse ratio vs pre-fault copper temperature (Onderdonk)
od = lambda ta: math.log10(1 + (1083 - ta) / (234 + ta))
nk = J("validation-results/02-protection-timing/shoot-through-f1/s44_necks.json")
r105 = nk["min_ratio_all"]
tab = {ta: round(r105 * od(ta) / od(105), 4) for ta in (95, 100, 102, 105, 112)}
cross = next(ta / 10 for ta in range(1050, 900, -1) if r105 * od(ta / 10) / od(105) >= 1.0)
out["E6_fuse_ratio"] = {"min_ratio_all_at_Ta105": r105, "ratio_vs_Ta": tab, "ratio_crosses_1_at_Ta_C": cross,
    "c18_heat_weighted_C": {"bus_p": [99.1, 102.1], "hv_ret": [104.4, 106.3], "leg": [109.2, 112.3]},
    "note": "the binding row is bus_p BR1+ -> Q2/Q5 drain (1697.7 A2s of 1710). Ta 105 is on the hot (conservative) side of 99-102"}

# E7 IPC-2221 20 K screen at bay 61
m = f(61 + 20) / f(25 + 20)
out["E7_ipc2221"] = {"rho_ratio_81C_vs_45C": round(m, 4), "width_ratio": round(m ** (0.5 / 0.725), 4), "width_mm_from_9.82": round(9.82 * m ** (0.5 / 0.725), 2),
    "note": "ESTIMATE: IPC-2221 rise ~ P/(h A); P ~ rho I^2 so I_eq = I sqrt(m); width ~ I^(1/0.725)"}

# E8 neck_fin
nf = json.loads((VR / "02-protection-timing/stage15-28A/out/neck_fin.json").read_text())
w = max(nf, key=lambda r: r["excess_28A_K"])
out["E8_neck_fin"] = {"coded_rho_factor": round(1 + A * 75, 4), "coded_equals_C": 20 + 75, "worst_span": w["run"], "excess_28A_K": w["excess_28A_K"],
    "at_130C": round(w["excess_28A_K"] * f(130) / (1 + A * 75), 1), "at_160C": round(w["excess_28A_K"] * f(160) / (1 + A * 75), 1)}

# E9 via barrel (r5_vias17) and pickup
vv = J("validation-results/04-board-current-thermal/round5-native21/stage17-r5/r5_vias17.json")["worst"]
out["E9_r5_via_barrel"] = {"c28_barrel_w_20C": vv["c28_barrel_w"], "c28_barrel_w_at_135C": round(vv["c28_barrel_w"] * f(135), 4),
    "mid_rise_K_20C": vv["c28_barrel_mid_rise_k"], "mid_rise_K_at_135C": round(vv["c28_barrel_mid_rise_k"] * f(135), 2)}
pk = J("validation-results/02-protection-timing/coil-pickup/s21b/result-s44.json")["rows"]["f60|pan_bars_31kHz_45Apk|base_A|cluster_drawn"]["stack_any_phase_x1p5_A"]
out["E10_pickup"] = {"stack_A": round(pk, 3), "R5_hot_factor": round(1 + 75e-6 * (135 - 25), 4), "stack_A_with_hot_R5": round(pk / (1 + 75e-6 * (135 - 25)), 3),
    "note": "pickup volts come from loop flux (geometry only); A = V/Rs, so a hot Rs makes the pickup in amps smaller. Nominal Rs is the conservative side"}
out["E11_labels"] = {"neck_fin": "1.72e-8 x (1 + 0.00393 x 75) = %.4e is 95 C, comment says 100 C" % (1.72e-8 * (1 + A * 75)),
                     "kelvin_track_bound": "1.72e-8 x (1 + 0.00393 x 100) is 120 C, comment says 125 C; rho 125 C = %.4e vs coded %.4e" % (1.72e-8 * f(125), 1.72e-8 * (1 + A * 100))}
Path(__file__).with_name("estimates.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
