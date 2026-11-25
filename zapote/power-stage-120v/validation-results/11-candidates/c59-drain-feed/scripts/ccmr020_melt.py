#!/usr/bin/env python3
"""CCMR020 melting I2t, estimated from Littelfuse's published let-through (OPEN-ITEMS S33 gates G2 / G3 / G5). No melting figure is published.

    python3 -I ccmr020_melt.py      -> ../ccmr020-melt.json

CCMR: Littelfuse CCMR rev 10/10/2022 (sha a63cfddb1077) p.5 table (20 A: 355 A apparent RMS at 5 kA), p.5 rerating curve, p.9 time-current.
KLDR: Littelfuse KLDR rev 092821 (sha 4502be84f474) pp.4-6: melting I2t AND the same let-through table, for nine ratings.
Method: peak = 2.3 x apparent RMS; a fault closed at voltage zero rises as k t, k = sqrt2 w Iprosp, so I2t to the peak = Ip^3 / (3 k).
CONTROL: do that for every KLDR rating with both figures. The spread of estimate / published is the method's error, and the CCMR range is its
estimate divided by that spread. The table follows Iprosp^(1/3) by construction, so agreement between fault currents is NOT a check.
Time-current [PLOT, by eye]: 153 A at 10 ms on the 20 A curve, 234 A2s; still falling with time, so an upper bound on the short-time figure."""
import json, math
from pathlib import Path
H = Path(__file__).resolve().parent
K, F2 = math.sqrt(2) * 2 * math.pi * 60 * 5000, 67.0
def melt(app): return (2.3 * app) ** 3 / (3 * K)
KLDR = {"4": (349, 83.81), "6": (420, 129.5), "7.5": (521, 321.8), "8": (437, 111.2), "10": (359, 132.0), "12": (369, 154.7),
        "15": (435, 200.5), "20": (456, 123.8), "30": (621, 299.6)}       # apparent RMS at 5 kA, published melting I2t
ctrl = {k: round(melt(a) / m, 2) for k, (a, m) in KLDR.items()}
e = melt(355)
near = [ctrl[k] for k in ("20", "30")]                    # same body, the ratings beside 20 A
rng = [round(e / max(ctrl.values()), 1), round(e / min(ctrl.values()), 1)]
tcc = round(153.0 ** 2 * 0.01, 0)
der = {50: 0.90, 61: 0.85}                                 # p.5 rerating curve [PLOT]
def verdict(f): return "FAIL" if not f(rng[0]) and not f(min(rng[1], tcc)) else "PASS" if f(rng[0]) else "UNRESOLVED"
out = {"raw_estimate_A2s": round(e, 1), "control_ratio_by_KLDR_rating": ctrl, "control_ratio_20_30": near, "melt_range_A2s": rng,
       "melt_range_from_20_30_A2s": [round(e / max(near), 1), round(e / min(near), 1)], "tcc_upper_bound_A2s": tcc,
       "G3_nuisance_need_A2s": round(max(1.0 / 0.22, 12.2 / 0.38), 1), "G3_nuisance": verdict(lambda m: 1.0 <= 0.22 * m and 12.2 <= 0.38 * m),
       "G5_need_A2s": 2 * F2, "G5_F2_selective": verdict(lambda m: m >= 2 * F2),
       "carry_A_0p75_rule": {t: round(20 * 0.75 * d, 2) for t, d in der.items()}}
assert min(ctrl.values()) < 1 < max(ctrl.values())          # the control set brackets the method
(H.parent / "ccmr020-melt.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
