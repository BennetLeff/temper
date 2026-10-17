#!/usr/bin/env python3
"""RESOLUTION-PLAN F12 steps 1-2. Run: python3 -I f12_l1_mot.py  (reads runs/*.json produced by b3_rerun.py) -> results/f12.json

Step 1: L1 (TDK B82726S2203A020) at the 15 A envelope. Sources: TDK B82726S22*3A020 datasheet 5/26 p.4 (4.5 mOhm typ per winding at 20 C,
rated 20 A at TR 60 C, climatic category 40/125/56) and p.5 derating curve Iop/IR vs TA (read by eye from the plot, +-0.03).
 DC copper at 15 A, 20 C: 2 x 4.5 mOhm x 15^2 = 2.025 W (losses.csv:34). AC: 50/60 Hz skin depth ~9 mm >> wire, HF ripple on the line is
 filtered upstream of L1 (module/X caps) -> AC copper << 0.1 W; core: DM leakage flux only (stray 18 uH) -> not quantifiable without the
 core data; bounded by the reviewer's 2.7 W (= 2.025 W at a ~100 C winding: x(1+0.00393*80)=2.66 W).
"""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
R = HERE / "runs"
ld = lambda n: json.loads((R / f"{n}.json").read_text())
out = {}
def part(run, ref):
    return {p["ref"]: p for p in run["parts"]}[ref]
base, dc, hot = ld("base_c28_h25_p0p25"), ld("L1_15A_dc20_c28_h25_p0p25"), ld("L1_15A_hot_c28_h25_p0p25")
rows = {}
for name, r in (("L1 1.229 W (11.7 A, as modelled)", base), ("L1 2.025 W (15 A DC, 20 C DCR)", dc), ("L1 2.70 W (reviewer bound / hot DCR)", hot)):
    rows[name] = {"L1_winding_C": round(part(r, "L1")["tj_c"], 1), "L1_pad_max_C": round(part(r, "L1")["pad_max_cell_c"], 1),
                  "C5_C": round(part(r, "C5")["tj_c"], 1), "C6_C": round(part(r, "C6")["tj_c"], 1),
                  "PS2_C": round(part(r, "PS2")["tj_c"], 1), "PS1_C": round(part(r, "PS1")["tj_c"], 1),
                  "board_peak_C": round(r["peak"]["temperature_c"], 1)}
out["b3_0p25mm_c28_h25"] = rows
out["criterion"] = "L1 <= 125 C with >= 15 K margin; C5/C6/PS2 not pushed past their limits"
l1 = rows["L1 2.70 W (reviewer bound / hot DCR)"]["L1_winding_C"]
out["verdict_L1"] = {"worst_winding_C": l1, "margin_to_125_K": round(125 - l1, 1), "pass": 125 - l1 >= 15,
                     "neighbour_shift_K": {k: round(rows["L1 2.70 W (reviewer bound / hot DCR)"][k] - rows["L1 1.229 W (11.7 A, as modelled)"][k], 2) for k in ("C5_C", "C6_C", "PS2_C", "PS1_C")}}
# independent check from the TDK derating curve (no B3): the curve ties rated current IR at TR to the 125 C limit.
pts = [(42, 1.15), (60, 1.0), (80, 0.80), (100, 0.52), (110, 0.33), (120, 0.12), (124, 0.0)]
def allowed_TA(ratio):
    for (t0, r0), (t1, r1) in zip(pts, pts[1:]):
        if r1 <= ratio <= r0: return t0 + (r0 - ratio) / (r0 - r1) * (t1 - t0)
out["tdk_curve"] = {"points_TA_vs_Iop_over_IR": pts, "allowed_air_C_at_15A": round(allowed_TA(15 / 20), 1),
                    "allowed_air_C_at_11p1A": round(allowed_TA(11.1 / 20), 1)}
# lumped model calibrated on the curve: winding 125 C at TA 60 C, I = 20 A, copper tempco 0.00393/K
r20 = 2 * 4.5e-3
p20 = r20 * 400 * (1 + 0.00393 * (125 - 20))
rth = (125 - 60) / p20
def tw(i, ta):
    t = ta
    for _ in range(200): t = ta + rth * r20 * i * i * (1 + 0.00393 * (t - 20))
    return t
out["lumped_calibrated_on_curve"] = {"Rth_K_per_W": round(rth, 2), "winding_C_15A_air50": round(tw(15, 50), 1),
                                    "winding_C_15A_air60": round(tw(15, 60), 1), "winding_C_15A_air70": round(tw(15, 70), 1),
                                    "loss_W_15A_air50": round(2 * 4.5e-3 * 225 * (1 + 0.00393 * (tw(15, 50) - 20)), 2)}
# Step 2: R5.4 vs laminate MOT 130 C (NP-155F datasheet MOT per sourcing/inquiries/CTI-JLC.md:37, quoted in bogatin-practical.md)
MOT = 130.0
out["R5_4_vs_MOT"] = {"legacy_1mm_peak_C (scorecard b3_c28_h25_peak_C)": 136.0, "legacy_margin_K": round(MOT - 136.0, 1),
                      "converged_R5_pad_max_cell_C (0.0625 mm, results.json / RESULTS-TABLES)": 129.4,
                      "converged_1mm_block_mean_C": 129.1, "converged_margin_K": round(MOT - 129.4, 1),
                      "my_0p25mm_rerun_R5_pad_max_C": round(part(base, "R5")["pad_max_cell_c"], 1),
                      "rule": "below 5 K margin -> 28 A needs a bench IR point at R5.4 (RESOLUTION-PLAN F12.2)",
                      "needs_bench_IR": MOT - 129.4 < 5}
# sensitivity of the R5.4 peak to tank current (0.5 mm runs; offset to the converged 0.0625 mm value = +6.7 K from R5 0.5 mm 122.8 vs 129.5)
off = 129.5 - 122.8
sw = {}
for it in (22, 24, 26, 27, 28):
    r = ld(f"base_it{it}.0_ik_h25_p0p5"); sw[str(it)] = round(part(r, "R5")["pad_max_cell_c"] + off, 1)
sw["29.4"] = round(part(ld("base_c28_h25_p0p5"), "R5")["pad_max_cell_c"] + off, 1)
out["R5_pad_max_C_vs_tank_RMS_A_converged_equiv"] = sw
need = 125.0
# tank A at which converged-equivalent peak = MOT-5 (linear interpolation)
xs = sorted((float(k), v) for k, v in sw.items())
for (x0, y0), (x1, y1) in zip(xs, xs[1:]):
    if y0 <= need <= y1: out["tank_A_for_5K_MOT_margin"] = round(x0 + (need - y0) / (y1 - y0) * (x1 - x0), 2)
(HERE / "results").mkdir(exist_ok=True)
(HERE / "results/f12.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
