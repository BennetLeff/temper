#!/usr/bin/env python3
"""C34: can ANY TDK B3265x (A/G/J/T) part of >= 1600 V DC make a 0.45-0.55 uF bank with worst-share ratio <= 0.85 at 28 A?

    python3 -I scripts/tdk_family_bound.py     -> results/tdk_family_bound.json   (exit 1 if a control fails)

Bound: every permissible-current curve of the family at >= 1600 V rises monotonically up to 100 kHz (pp.53, 55, 57,
59, 60, 62, 63; checked by eye on the 22.5 / 27.5 / 37.5 mm charts, and numerically on the digitized p.57 chart by the
control below). So I_allow(35-50 kHz) <= I_RMS(100 kHz) from the ordering tables, and
    ratio(35 kHz) >= 28 A * s_worst / I_RMS(100 kHz)       (a LOWER bound on the ratio)
A part whose bound already exceeds 0.85 cannot pass at any frequency in the window. Bank: n equal parts of value C with
n C in 0.45-0.55 uF, J (+-5 %) share. Fit: body row n (w + 0.5) - 0.5 against the slot (slot_geometry.json: pin rows
53.2-111.5 plus half a body each end, i.e. 58.3 + w mm), height against 52.5 mm.
Table rows: TDK MKP_B32651_658.pdf (6/26) p.19 / p.20 (22.5 mm), p.23 (27.5 mm), p.31 / p.32 (37.5 mm),
p.34 (52.5 mm), values typed below (nF, w, h, l, I_RMS 85 C 100 kHz).
"""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results"
R6 = HERE.parents[2] / "05-resonant-tank-envelope/round6-full-power/outputs/tdk-p57-1600v.csv"
T = {  # (series, Vdc/Vac, pitch, page): [(nF, w, h, l, I100k)]
    ("B32653A1", "1600/500", 22.5, "p.19"): [(33, 10.5, 16.5, 26.5, 3.8), (47, 11.0, 20.5, 26.5, 5.0), (56, 12.0, 22.0, 26.5, 5.6),
                                             (68, 14.5, 29.5, 26.5, 7.1), (82, 14.5, 29.5, 26.5, 7.7), (100, 14.5, 29.5, 26.5, 8.4)],
    ("B32653A2", "2000/700", 22.5, "p.20"): [(33, 14.5, 29.5, 26.5, 6.5)],
    ("B32654A1", "1600/500", 27.5, "p.23"): [(47, 11.0, 21.0, 31.5, 4.6), (68, 11.0, 21.0, 31.5, 5.5), (100, 14.0, 24.5, 31.5, 7.3),
                                             (150, 18.0, 27.5, 31.5, 9.5), (220, 21.0, 31.0, 31.5, 12.0)],
    ("B32654A2", "2000/700", 27.5, "p.23"): [(33, 13.5, 23.0, 31.5, 4.6), (47, 18.0, 27.5, 31.5, 6.4), (68, 19.0, 30.0, 31.5, 7.8),
                                             (82, 22.0, 36.5, 31.5, 9.3), (100, 22.0, 36.5, 31.5, 10.0)],
    ("B32656J1", "1600/600", 37.5, "p.31"): [(100, 12.0, 22.0, 42.0, 6.0), (150, 14.0, 25.0, 42.0, 7.6), (220, 16.0, 28.5, 42.0, 9.5),
                                             (330, 20.0, 39.5, 42.0, 10.4), (470, 28.0, 37.0, 42.0, 12.3)],
    ("B32656T1", "1600/600", 37.5, "p.31"): [(150, 24.0, 15.0, 42.0, 7.8), (220, 24.0, 19.0, 42.0, 9.8)],
    ("B32656G1", "1600/600", 37.5, "p.31"): [(330, 20.0, 39.5, 42.0, 11.0), (470, 28.0, 37.0, 42.0, 13.4), (560, 28.0, 37.0, 42.0, 14.3)],
    ("B32656J2", "2000/700", 37.5, "p.32"): [(68, 12.0, 22.0, 42.0, 5.7), (100, 14.0, 25.0, 42.0, 7.4), (150, 18.0, 32.5, 42.0, 9.8),
                                             (220, 20.0, 39.5, 42.0, 12.7), (330, 28.0, 37.0, 42.0, 13.4), (470, 30.0, 45.0, 42.0, 14.7)],
    ("B32656T2", "2000/700", 37.5, "p.32"): [(100, 24.0, 15.0, 42.0, 7.4), (120, 24.0, 19.0, 42.0, 8.7)],
    ("B32656G2", "2000/700", 37.5, "p.32"): [(220, 20.0, 39.5, 42.0, 13.3), (330, 28.0, 37.0, 42.0, 14.3), (470, 30.0, 45.0, 42.0, 16.5)],
    ("B32658G2", "2000/700", 52.5, "p.34"): [(680, 30.0, 45.0, 57.5, 19.0)],
}
GO, I_T, TOL = 0.85, 28.0, 0.05
SLOT_PIN_SPAN, HEAD = 111.5 - 53.2, 52.5
fails = []
# control: the digitized p.57 curves are monotone non-decreasing 10-99 kHz and end at the table value
rows = list(csv.DictReader(open(R6)))
for k in rows[0]:
    if k.startswith("I_"):
        v = [float(r[k]) for r in rows]
        if any(b < a - 0.02 for a, b in zip(v, v[1:])):
            fails.append(f"p.57 {k} not monotone")
res = []
for (ser, volt, pitch, page), lst in T.items():
    for nf, w, h, l, i100 in lst:
        for n in range(1, 13):
            c = n * nf / 1000
            if not 0.45 <= c <= 0.55:
                continue
            s = (1 + TOL) / ((1 + TOL) + (n - 1) * (1 - TOL)) if n > 1 else 1.0
            lb = I_T * s / i100
            row = n * (w + 0.5) - 0.5
            res.append({"part": f"{ser}{nf}nF", "V": volt, "pitch": pitch, "page": page, "n": n, "C_uF": round(c, 3),
                        "w": w, "h": h, "I100k_A": i100, "ratio_35_50k_lower_bound": round(lb, 3),
                        "can_pass": lb <= GO, "body_row_mm": round(row, 1),
                        "fits_column": (n - 1) * (w + 0.5) <= SLOT_PIN_SPAN and h <= HEAD and pitch == 27.5})
res.sort(key=lambda r: r["ratio_35_50k_lower_bound"])
passing = [r for r in res if r["can_pass"]]
out = {"rule": "ratio >= 28 A * s / I_RMS(100 kHz table); can_pass needs the bound <= 0.85",
       "controls": {"failed": fails, "passed": not fails},
       "n_configs": len(res), "can_pass": passing,
       "can_pass_and_fit_today_copper": [r for r in passing if r["fits_column"]], "all": res}
OUT.mkdir(exist_ok=True)
(OUT / "tdk_family_bound.json").write_text(json.dumps(out, indent=1) + "\n")
for r in res[:14]:
    print(r["part"], r["V"], r["pitch"], r["n"], r["C_uF"], r["ratio_35_50k_lower_bound"], r["can_pass"], r["body_row_mm"], r["fits_column"])
print("can pass:", len(passing), "of", len(res), "; can pass and fit:", len(out["can_pass_and_fit_today_copper"]))
sys.exit(1 if fails else 0)
