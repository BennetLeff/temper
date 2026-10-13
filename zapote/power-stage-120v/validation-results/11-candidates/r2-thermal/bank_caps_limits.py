#!/usr/bin/env python3
"""Film-cap limits re-read from the TDK catalogue (MKP_B32651_658.pdf, 6/26: p.35 technical data, p.64 F_T curve) and the bank
ratio versus frequency / binning. Run: python3 -I bank_caps_limits.py -> results/bank_caps_limits.json

New data vs DECISIONS 21: the B3265*A series (B32652 HF C38-41 and B32654 bank C21-23/151/152) is rated TR 85 C, upper category
temperature Tmax 100 C (climatic 40/100/56), MAXIMUM OPERATING temperature Top,max 110 C (Top = TA + self-heating). B3 used 105 C.
IRMS curves hold for TA <= 85 C with self-heating <= 20 K; above 85 C multiply by F_T(TA) (p.64: 1.0 at 85, ~0.63 at 100, 0 at 110;
fit F_T = sqrt((110-TA)/25), checked against the plotted curve at 90/95/100 C: 0.90/0.77/0.63).
"""
import importlib.util, json, math
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bank_options", HERE.parent / "g04-g09-tank-detect/scripts/bank_options.py")
bo = importlib.util.module_from_spec(spec); spec.loader.exec_module(bo)
out = {}
# 1) HF caps C38-41 (B32652A0104K000): converged B3 element temperatures (RESULTS-TABLES.md, c28 h25): C40 98.7, C38 97.6, C39 95.5, C41 88.5
hf = {"C40": 100.0, "C38": 97.6, "C39": 96.8, "C41": 88.6}   # estimate + convergence uncertainty (the RESULTS-TABLES margin column)
out["hf_caps_margin_K"] = {r: {"to_105_assumed": round(105 - t, 1), "to_Top_max_110": round(110 - t, 1), "to_category_100": round(100 - t, 1)} for r, t in hf.items()}
# allowed IRMS factor at the cap's own temperature if treated as the ambient TA
ft = lambda ta: 1.0 if ta <= 85 else math.sqrt(max(110 - ta, 0) / 25)
out["F_T"] = {str(t): round(ft(t), 2) for t in (85, 90, 95, 100, 105)}
out["hf_voltage_derate_VDC_at_99C"] = round(1000 * (1 - 0.0125 * (99 - 85)), 0)   # p.35: 1.25 %/K above 85 C
# 2) bank ratio versus operating frequency (curve = 85 C curve), J parts +-5 %
rows = {}
for f in (35e3, 40e3, 45e3, 50e3):
    for I in (28.0, 29.4):
        sh = bo.shares([100] * 5, 0.05)
        rows[f"{int(f/1e3)}kHz@{I}A"] = round(max(I * s / bo.limit(100, f) for s in sh), 3)
out["bank_ratio_J"] = rows
# 3) binned capacitance (select-on-test, +-tol at assembly) : ratio at 28 A 40 kHz
out["bank_ratio_28A_40k_vs_bin_tol"] = {f"+-{t*100:g}%": round(max(28 * s / bo.limit(100, 40e3) for s in bo.shares([100] * 5, t)), 3) for t in (0.10, 0.05, 0.03, 0.02, 0.01)}
# 4) tank A allowed (ratio 1.0, J) vs f, and f needed for ratio <= 1.00 / 0.95 at 28 A
def i_allow(f, tol=0.05): return min(bo.limit(100, f) / s for s in bo.shares([100] * 5, tol))
out["tank_A_allowed_J"] = {f"{k}kHz": round(i_allow(k * 1e3), 2) for k in (35, 38, 40, 42, 45, 48, 50)}
for tgt in (1.0, 0.95):
    f = 35e3
    while f < 60e3 and 28 / i_allow(f) > tgt: f += 100
    out[f"f_for_ratio_{tgt}_at_28A_Hz"] = round(f)
# 5) local-air relief for the bank: TDK gives no credit below 85 C, so air temperature does not move the ratio; above 85 C F_T bites
out["bank_ratio_if_local_air_C"] = {str(t): round(1.022 / ft(t), 3) for t in (70, 85, 90, 95, 100)}
(HERE / "results").mkdir(exist_ok=True)
(HERE / "results/bank_caps_limits.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
