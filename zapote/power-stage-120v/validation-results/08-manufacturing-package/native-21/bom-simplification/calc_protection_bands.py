#!/usr/bin/env python3
"""Re-run the committed task-02 round-3 threshold corner model (read-only import) for
proposed resistor changes. The repo file is imported, never written; PARTS is patched in memory.

  P-R34  : R34/R35 10.6k/10.0k (no stock)  ->  12.4k/11.7k  (alt 19.3k/18.2k)  [shunt OCP band]
  NC-R40 : R40/R41 1k 0.1 % thin film      ->  1k 1 % 100 ppm thick film      [CT trip band]
Also re-derives the REF25 (LM4040) minimum cathode current with the new R34+R35 load, using
the same corner formula as audit.rs::min_reference_cathode_current_ua.
usage: python3 calc_protection_bands.py <unit dir>   -> prints table, writes out/protection_bands.json
"""
import importlib.util, json, sys, os
from pathlib import Path
UNIT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[4]
src = UNIT / "validation-results/02-protection-timing/round3/thresholds.py"
spec = importlib.util.spec_from_file_location("thr", src); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
BASE = dict(m.PARTS)
RT = (0.001, 25e-6); RC = (0.01, 100e-6)

def band(over, key):
    m.PARTS.clear(); m.PARTS.update(BASE); m.PARTS.update(over)
    out = {t: m.exact_corners(t, 50.0)[key] for t in (-10.0, 85.0)}
    return round(min(b["min"] for b in out.values()), 2), round(max(b["max"] for b in out.values()), 2)

def nominal_trip(r34, r35, ref=2.5):
    th = ref * r35 / (r34 + r35)
    return th, (ref * 1.0 - th * 2.0) / 0.001      # R32 = R33, R5 = 1 mOhm

def cathode_ua(bias_ohm, r34r35):
    ref_max = 2.520
    i_bias = (4.75 - ref_max) / (bias_ohm * 1.01)
    return (i_bias - (ref_max + .15) / (20e3 * .999) - ref_max / (r34r35 * .999) - ref_max / (150e3 * .999)) * 1e6

rows = []
for label, r34, r35 in [("baseline (fitted) 10.6k/10.0k", 10.6e3, 10e3),
                        ("P-R34: 12.4k/11.7k", 12.4e3, 11.7e3),
                        ("alt: 19.3k/18.2k", 19.3e3, 18.2e3),
                        ("rejected: 10.5k/10.0k (D-31 old)", 10.5e3, 10e3)]:
    lo, hi = band({"R34": (r34, *RT), "R35": (r35, *RT)}, "shunt_a")
    th, it = nominal_trip(r34, r35)
    rows.append({"case": label, "thresh_V": round(th, 5), "nominal_trip_A": round(it, 2),
                 "band_min_A": lo, "band_max_A": hi, "meets_44A_min": lo >= 44.0,
                 "thevenin_ohm": round(r34 * r35 / (r34 + r35)), "ref25_cathode_uA_min": round(cathode_ua(5600, r34 + r35), 1)})
ct = []
for label, tolset in [("baseline R40/R41 0.1 % 25 ppm", RT), ("NC-R40: R40/R41 1 % 100 ppm (Basic 0603WAF1001T5E)", RC)]:
    over = {"R40": (1e3, *tolset), "R41": (1e3, *tolset)}
    ct.append({"case": label, "ct_pos_band_A": band(over, "ct_pos_a"), "ct_neg_band_A": band(over, "ct_neg_a")})
res = {"model": str(src), "shunt_ocp": rows, "ct_trip": ct,
       "note": "band = min/max over every resistor vertex, ref +/-20 mV, Vos +/-4 mV, input bias, at -10 and +85 C, R5 +50 C (task 02 round 3 model, unchanged)"}
os.makedirs(Path(__file__).parent / "out", exist_ok=True)
(Path(__file__).parent / "out/protection_bands.json").write_text(json.dumps(res, indent=1) + "\n")
print(f"{'case':38s} {'thresh V':>9s} {'nom A':>7s} {'min A':>7s} {'max A':>7s} {'Rth':>6s} {'Ik uA':>7s}")
for r in rows:
    print(f"{r['case']:38s} {r['thresh_V']:9.5f} {r['nominal_trip_A']:7.2f} {r['band_min_A']:7.2f} {r['band_max_A']:7.2f} {r['thevenin_ohm']:6d} {r['ref25_cathode_uA_min']:7.1f}")
for c in ct:
    print(c)
