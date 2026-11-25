#!/usr/bin/env python3
"""Can a hand-wound Kool Mu toroid be the D-22 DM inductor (>= 100 uH at 21 A peak, <= 1.8 W at 15 A rms hot, <= 50 mm tall)?

    python3 -I validation-results/11-candidates/c57-d22-scope/scripts/toroid.py [--check]

Core data: Magnetics datasheets 0077439A7 (rev 4/21/2025) and 0077083A7 (rev 10/6/2021), read 2026-11-24: AL +-8 %, le, window,
length per turn against winding factor, wound coil size at 40 %, and the guaranteed minimum DC bias: 80 % at 39 Oe, 50 % at 87 Oe.
Permeability between and beyond those two points: 1 / (1 + (H/87)^c) through both (beyond 87 Oe it is an extrapolation, flagged).
Copper: round wire bare area and 20 C resistance (AWG); x1.314 at 100 C. Core and AC copper loss are NOT included (optimistic).
"""
import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "results/toroid.json"
I_PK, I_RMS, L_REQ, P_MAX, H_MAX, KHOT = 21.0, 15.0, 100e-6, 1.8, 50.0, 1 + 0.00393 * 80
C = math.log(4) / math.log(87 / 39)
CORES = {"0077439A7": dict(AL=135e-9, le=10.74, Wa=427, wound_od=52.4, wound_ht=26.1,
                           mlt=[(0, 62.2), (20, 68.3), (25, 69.7), (30, 71.0), (35, 72.8), (40, 74.2), (45, 76.0), (50, 77.6), (60, 81.3), (70, 85.6)]),
         "0077083A7": dict(AL=81e-9, le=9.84, Wa=427, wound_od=44.3, wound_ht=22.4,
                           mlt=[(0, 48.2), (20, 54.3), (25, 55.8), (30, 57.0), (35, 58.8), (40, 60.2), (45, 62.1), (50, 63.7), (60, 67.3), (70, 71.5)])}
WIRE = {"13 AWG": (2.624, 6.571e-3), "12 AWG": (3.309, 5.211e-3), "10 AWG": (5.261, 3.277e-3)}   # mm2, ohm/m at 20 C


def mu(h):
    return 1 / (1 + (h / 87) ** C)


def interp(tab, x):
    for (x0, y0), (x1, y1) in zip(tab, tab[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return None


assert abs(mu(39) - .8) < 1e-9 and abs(mu(87) - .5) < 1e-9
res = {}
for c, k in CORES.items():
    for al_tol in (0.0, -0.08):
        n = next((n for n in range(5, 121) if k["AL"] * (1 + al_tol) * n * n * mu(0.4 * math.pi * n * I_PK / k["le"]) >= L_REQ), None)
        r = {"turns_for_100uH_at_21A": n}
        if n:
            h = 0.4 * math.pi * n * I_PK / k["le"]
            r.update(H_Oe=round(h, 1), beyond_guaranteed_50pct_point=h > 87, mu_fraction=round(mu(h), 3))
            for w, (a, rho) in WIRE.items():
                ff = 100 * n * a / k["Wa"]
                mlt = interp(k["mlt"], ff)
                if mlt is None:
                    r[w] = {"winding_factor_pct": round(ff, 1), "fits_window": False}
                    continue
                rd = n * mlt * 1e-3 * rho
                r[w] = {"winding_factor_pct": round(ff, 1), "DCR20_mohm": round(rd * 1e3, 1),
                        "P_hot_15A_W": round(I_RMS ** 2 * rd * KHOT, 2), "within_1W8": I_RMS ** 2 * rd * KHOT <= P_MAX}
        res[f"{c} AL {al_tol:+.0%}"] = r
    # most inductance the core holds at 21 A with the winding at 40 % (the datasheet's wound size)
    res[f"{c} size"] = {"wound_OD_40pct_mm": k["wound_od"], "wound_HT_40pct_mm": k["wound_ht"],
                        "stands_on_edge_in_50mm": k["wound_od"] <= H_MAX,
                        "L_at_21A_uH_at_guaranteed_50pct_point": round(0.5 * k["AL"] * (87 * k["le"] / (0.4 * math.pi * I_PK)) ** 2 * 1e6, 1)}
text = json.dumps(res, indent=1) + "\n"
if "--check" in sys.argv:
    sys.exit(0 if OUT.read_text() == text else "toroid.json is stale")
OUT.write_text(text)
print(text)
