#!/usr/bin/env python3
"""-2 V split (RegulatedSplit: TLVH431B, rtop src->fb, rbot fb->n) versus the RailMonitor negative window
(TL431A reference halved by 10k/10k; UV divider 4.42k/10k, OV divider 7.68k/10k), for the no-stock
rtop = 6.12 k (R77/R95/R110) and stocked candidates 6.19 k / 6.2 k / 6.04 k (all 0.1 %, 25 ppm).

Datasheet inputs (cited in PROPOSAL.md; edit here if a reviewer prefers other figures):
  TLVH431BQ (SLVS555N, Jun 2024, TLVH431B table): VREF full range -40..125 C = 1.221 .. 1.265 V (IK = 10 mA);
            dVREF/dVKA <= -2.7 mV/V (VKA - VREF ~ 0.76 V here -> <= 2.1 mV low); Iref <= 0.5 uA (adds Iref*rtop).
  TL431AIDBZR (SLVS543S, May 2024, sec 6.9): Vref 2.470 .. 2.520 V at 25 C, VI(dev) <= 34 mV (SOT-23-3) -> 2.436 .. 2.554 V
            used as a conservative full-range band; REF tied to K so ratio term is 0.
  LM339B  : Vio <= 4 mV (SLCS517 LM339B) -> referred to the rail through the divider gain.
  Resistors 0.1 %, 25 ppm, |dT| = 125 K.
Prints nominal Vneg, its corner range, the corner UV/OV trip window, and the margins
(Vneg_min - UV_trip_max must stay > 0 and OV_trip_min - Vneg_max > 0), plus margin to the -1.6 V qualification bound.
NB: these are conservative linear stacks, not a TI guarantee; the repo's own figures (ECO.md) quote nominal window -2.198/-1.799 V.
"""
import itertools, json, os
from pathlib import Path
TOL, TCR, DT = 0.001, 25e-6, 125.0
def rr(r):  # (min, max) of a 0.1 % 25 ppm resistor over temperature
    d = TOL + TCR * DT
    return r * (1 - d), r * (1 + d)
def vneg_range(rtop, rbot=10e3):
    vals = []
    for vref, rt, rb, iref in itertools.product((1.221 - .0021, 1.265), rr(rtop), rr(rbot), (0, 0.5e-6)):
        vals.append(vref * (1 + rt / rb) + iref * rt)
    return min(vals), max(vals), 1.24 * (1 + rtop / rbot)
def window():
    # src-n trips when (src-n)*rbot/(rtop+rbot) crosses halfref = Vref431/2 * (10k/(10k+10k))*2 ... i.e. Vref431*h, h = rb/(rt+rb) of the 10k/10k
    uv, ov = [], []
    for vref, h1, h2, vio in itertools.product((2.470 - .034, 2.520 + .034), rr(10e3), rr(10e3), (-.004, .004)):
        half = vref * h2 / (h1 + h2) + vio
        for t, b in itertools.product(rr(4.42e3), rr(10e3)):
            uv.append(half * (t + b) / b)
        for t, b in itertools.product(rr(7.68e3), rr(10e3)):
            ov.append(half * (t + b) / b)
    return (min(uv), max(uv)), (min(ov), max(ov)), (2.495 / 2 * 14.42 / 10, 2.495 / 2 * 17.68 / 10)
(uvlo, uvhi), (ovlo, ovhi), (uvn, ovn) = window()
rows = []
for label, rtop, stock in [("fitted 6.12k RT0603BRD076K12L (JLC 0)", 6.12e3, "0"),
                           ("6.19k RT0603BRD076K19L C861530", 6.19e3, "343"),
                           ("6.2k  RT0603BRD076K2L  C136960", 6.2e3, "91153"),
                           ("6.04k RT0603BRD076K04L C728595", 6.04e3, "3454")]:
    lo, hi, nom = vneg_range(rtop)
    rows.append({"case": label, "jlc_stock": stock, "vneg_nom": round(nom, 4), "vneg_min": round(lo, 4), "vneg_max": round(hi, 4),
                 "margin_to_uv_trip_V": round(lo - uvhi, 4), "margin_to_ov_trip_V": round(ovlo - hi, 4),
                 "margin_to_-1.6V_bound_V": round(lo - 1.6, 4), "nominal_shift_mV": round((nom - 1.24 * 1.612) * 1e3, 1)})
res = {"uv_trip_V": [round(uvlo, 4), round(uvhi, 4)], "ov_trip_V": [round(ovlo, 4), round(ovhi, 4)],
       "nominal_window_V": [round(uvn, 4), round(ovn, 4)], "rows": rows}
os.makedirs(Path(__file__).parent / "out", exist_ok=True)
(Path(__file__).parent / "out/neg_rail.json").write_text(json.dumps(res, indent=1) + "\n")
print("monitor window (magnitude of src-n): UV trip", res["uv_trip_V"], " OV trip", res["ov_trip_V"], " nominal", res["nominal_window_V"])
for r in rows: print(r)
