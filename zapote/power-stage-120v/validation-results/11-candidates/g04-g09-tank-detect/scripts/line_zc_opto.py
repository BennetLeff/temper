#!/usr/bin/env python3
"""G09 line zero-cross: VOL628A-3X001T (CTR bin 3, 100-200 %) vs VOL628A-2X001T (bin 2, 63-125 %), same package, VDE option.

Model (ASSUMPTIONS flagged, because Vishay specifies CTR only at IF = 1 mA, ECO.md "extrapolated sub-mA CTR is not a
timing guarantee"):
  LED string = 4 x 16.5 k (RC1206FR-0716K5L, +-1 %) between L_FILT and N_FILT; LED Vf = VF_LOW (assumed 0.9 V at tens of uA;
  datasheet gives 1.16 V typ at 5 mA, Fig. 6).
  Output node is HIGH (pulse) while Ic < IC_HI and goes LOW above IC_LO, with the 33 k pull-up to 3.3 V and the Schmitt
  buffer (SN74LVC1G17 VT+/VT- assumed 1.9 / 1.0 V at 3.3 V): IC_HI = (3.3-1.9)/33k, IC_LO = (3.3-1.0)/33k.
  Ic = CTR(1 mA) * g * IF, with g = CTR(IF)/CTR(1 mA) at the threshold current, swept over {0.1, 0.2, 0.3, 0.6, 1.0}.
Pulse width = time the |line| stays below the (rising/falling) LED threshold voltage around each zero crossing.
Firmware window (firmware/components/power/n21_binding.c): width 300-4000 us, half-period 7833-8834 us.
This computes where each bin sits against that window; it is NOT a timing certificate (bench item, ECO.md).
Run: python3 -I line_zc_opto.py -> ../results/line_zc_opto.json
"""
import json, math
from pathlib import Path

HERE = Path(__file__).resolve().parent
R_STRING = 4 * 16.5e3
VF_LOW = 0.9
IC_HI = (3.3 - 1.9) / 33e3       # output goes high below this collector current
IC_LO = (3.3 - 1.0) / 33e3
W_MIN, W_MAX = 300.0, 4000.0     # us
BINS = {"-3 (100-200 %)": (1.0, 2.0), "-2 (63-125 %)": (0.63, 1.25)}


def width_us(ctr, g, vrms, f, r_scale=1.0):
    ic = IC_HI                                   # rising edge of output = LED turning off
    i_f = ic / (ctr * g)
    vth = VF_LOW + i_f * R_STRING * r_scale
    vpk = vrms * math.sqrt(2)
    if vth >= vpk:
        return float("inf")
    return 2 * math.asin(vth / vpk) / (2 * math.pi * f) * 1e6


res = {"assumptions": {"VF_LOW_V": VF_LOW, "IC_HI_mA": round(IC_HI * 1e3, 4), "IC_LO_mA": round(IC_LO * 1e3, 4),
                       "R_string_ohm": R_STRING, "window_us": [W_MIN, W_MAX]}, "bins": {}}
for nm, (lo, hi) in BINS.items():
    rows = []
    for g in (0.1, 0.2, 0.3, 0.6, 1.0):
        for (vrms, f) in ((85, 47), (108, 60), (120, 60), (132, 60), (140, 63)):
            for tag, ctr in (("min", lo), ("max", hi)):
                for rs in (0.99, 1.01):
                    w = width_us(ctr, g, vrms, f, rs)
                    rows.append({"g": g, "Vrms": vrms, "f": f, "CTR": tag, "w_us": round(w, 0)})
    ws = [r["w_us"] for r in rows]
    by_g = {}
    for gg in (0.1, 0.2, 0.3, 0.6, 1.0):
        wg = [r["w_us"] for r in rows if r["g"] == gg and r["Vrms"] == 120]
        by_g[str(gg)] = {"w120V_us_min": min(wg), "w120V_us_max": max(wg)}
    res["bins"][nm] = {"by_g_at_120V_60Hz": by_g, "width_us_min": min(ws), "width_us_max": max(ws),
                       "n_below_300us": sum(w < W_MIN for w in ws), "n_cases": len(ws),
                       "typ_120V_60Hz_g0.6_midCTR_us": round(width_us((lo + hi) / 2, 0.6, 120, 60), 0)}
(HERE.parent / "results" / "line_zc_opto.json").write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps(res, indent=1))
