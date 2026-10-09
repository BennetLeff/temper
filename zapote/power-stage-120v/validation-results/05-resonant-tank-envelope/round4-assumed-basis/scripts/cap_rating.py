#!/usr/bin/env python3
"""Conservative allowable-current bound for the CDE 942C tank-bank parts at 30-60 kHz, hot.

ASSUMED-BASIS evidence; this is a bound derived from the catalogue, not a CDE rating.

Inputs (CDE 942C catalogue, ../../sources/942C.pdf, SHA-256 f9939544...):
  p.1  operating -55..105 C; full rated voltage to 85 C, linear to 50 % at 105 C;
       1200 Vdc parts are 430 Vac (60 Hz).
  p.3  1200 Vdc table: I_rms at 70 C / 100 kHz and typical ESR:
       942C12P1K-F 0.10 uF 9.2 A, 5 mOhm, D19.0 x L34.0 mm
       942C12P22K-F 0.22 uF 10.3 A, 6 mOhm, D26.5 x L34.0 mm
       942C12P33K-F 0.33 uF 11.0 A, 6 mOhm, D24.5 x L46.0 mm
  p.4  1200 Vdc 'RMS Voltage vs Frequency @ 25 C' for 0.1 / 0.33 / 0.9 uF
       (digitized: outputs/digitized-cde-942c-1200vdc.csv). No 0.22 uF trace.

Bound T (thermal, frequency transfer of the 70 C / 100 kHz table value):
  Allowable self-heating P_max = I_100k^2 * ESR(100k) at CDE's 70 C rating condition.
  ESR(f) = R_s(f) + DF(f)/(2 pi f C). Metal/terminal R_s does not fall as f rises
  (skin/proximity), and polypropylene DF does not fall with f in this band, so ESR(f)*f
  is non-decreasing in f, i.e. ESR(f) <= ESR(100k)*(100k/f) for f <= 100 kHz. Hence
      I_allow(f, 70 C) >= I_100k * sqrt(f / 100 kHz).
  This is the worst case 'all ESR is dielectric' assumption: a lower bound.

Estimate S (shape transfer from the 25 C curves of the bracketing parts):
  I_allow(f, 70 C) ~ I_100k * I_25C(f)/I_25C(100k), using each bracketing part's own
  25 C curve shape (0.1 uF and 0.33 uF). Below ~40 kHz the 0.1 uF curve is on its
  430 V voltage limit, so its shape there under-states thermal capacity (conservative).
  Reported for comparison; the bound used for verdicts is min(T, S).

Hot ambient above 70 C (ESTIMATE): with the 105 C category limit taken as the hot-spot
ceiling, I^2 ~ (105 - T_amb), so I(T) = I(70 C) * sqrt((105 - T)/35). Reported at 85 C.

Bank sharing: C21 = C22 = 0.22 uF, C23 = 0.10 uF in parallel (same voltage): current
splits by capacitance. Nominal share 0.22/0.54 = 40.7 % and 0.10/0.54 = 18.5 %. Worst
share under +/-10 % (942C 'K'): the part +10 %, the others -10 %: 45.7 % and 21.7 %.
"""
import csv
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "outputs")

TABLE = {  # part: (C_F, I_rms_70C_100k, ESR_typ_ohm, D_mm, L_mm)
    "942C12P1K-F": (0.10e-6, 9.2, 0.005, 19.0, 34.0),
    "942C12P22K-F": (0.22e-6, 10.3, 0.006, 26.5, 34.0),
    "942C12P33K-F": (0.33e-6, 11.0, 0.006, 24.5, 46.0),
}
BANK = {"C21": "942C12P22K-F", "C22": "942C12P22K-F", "C23": "942C12P1K-F"}
FREQS = [30000, 35000, 40000, 45000, 50000, 55000, 60000]


def curves():
    d = {}
    with open(os.path.join(OUT, "digitized-cde-942c-1200vdc.csv")) as fh:
        for r in csv.DictReader(fh):
            d[(r["series"], int(r["f_hz"]))] = float(r["Irms_implied_25C"])
    return d


def interp_curve(cv, series, f):
    pts = sorted((k[1], v) for k, v in cv.items() if k[0] == series)
    for (f1, i1), (f2, i2) in zip(pts, pts[1:]):
        if f1 <= f <= f2:
            t = math.log(f / f1) / math.log(f2 / f1)
            return i1 + t * (i2 - i1)
    raise ValueError(f)


def shares(tol=0.10):
    cs = {k: TABLE[v][0] for k, v in BANK.items()}
    tot = sum(cs.values())
    nom = {k: c / tot for k, c in cs.items()}
    worst = {}
    for k in cs:
        hi = cs[k] * (1 + tol)
        others = sum(c * (1 - tol) for kk, c in cs.items() if kk != k)
        worst[k] = hi / (hi + others)
    return nom, worst


def bound(part, f, cv):
    c, i100, *_ = TABLE[part]
    t = i100 * math.sqrt(f / 100e3)
    s01 = i100 * interp_curve(cv, "0.10uF", f) / cv[("0.10uF", 100000)]
    s033 = i100 * interp_curve(cv, "0.33uF", f) / cv[("0.33uF", 100000)]
    return t, s01, s033


def main():
    cv = curves()
    nom, worst = shares()
    rows = []
    for f in FREQS:
        row = {"f_hz": f}
        tank_limits = []
        for ref, part in BANK.items():
            if ref == "C22":
                continue
            t, s01, s033 = bound(part, f, cv)
            b = min(t, s01, s033)
            row[f"{ref}_{part}_T_bound_70C_A"] = round(t, 2)
            row[f"{ref}_shape_0.1uF_70C_A"] = round(s01, 2)
            row[f"{ref}_shape_0.33uF_70C_A"] = round(s033, 2)
            row[f"{ref}_allow_70C_A"] = round(b, 2)
            row[f"{ref}_allow_85C_A"] = round(b * math.sqrt(20 / 35), 2)
            row[f"{ref}_tank_limit_70C_nomshare_A"] = round(b / nom[ref], 2)
            row[f"{ref}_tank_limit_70C_worstshare_A"] = round(b / worst[ref], 2)
            row[f"{ref}_tank_limit_85C_worstshare_A"] = round(b * math.sqrt(20 / 35) / worst[ref], 2)
            tank_limits.append(b / worst[ref])
        row["bank_tank_limit_70C_worstshare_A"] = round(min(tank_limits), 2)
        # best-estimate (not a bound): 0.22 uF via the 0.33 uF 25 C curve shape, nominal share
        s033 = bound("942C12P22K-F", f, cv)[2]
        row["C21_estimate_0.33shape_70C_A"] = round(s033, 2)
        row["bank_tank_estimate_70C_nomshare_A"] = round(s033 / nom["C21"], 2)
        # 25 C voltage-curve bracket for 0.22 uF: the 0.33 uF trace (lower) and 0.1 uF trace
        row["Vrms_allow_25C_0.33uF_trace"] = round(interp_curve(cv, "0.33uF", f) / (2 * math.pi * f * 0.33e-6), 1)
        row["Vrms_allow_25C_0.10uF_trace"] = round(interp_curve(cv, "0.10uF", f) / (2 * math.pi * f * 0.10e-6), 1)
        rows.append(row)
    with open(os.path.join(OUT, "cap-rating-bound.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    # 25 C -> 70 C ratio at 100 kHz, per part with both a curve and a table value
    hot_ratio = {"0.10uF": 9.2 / cv[("0.10uF", 100000)], "0.33uF": 11.0 / cv[("0.33uF", 100000)]}
    summary = {
        "status": "ASSUMED conservative bound from the CDE 942C catalogue; NOT a CDE rating",
        "share_nominal": nom, "share_worst_10pct": worst,
        "hot_70C_over_25C_at_100kHz": hot_ratio,
        "doc": __doc__,
    }
    with open(os.path.join(OUT, "cap-rating-bound.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    for r in rows:
        print(r)
    print(summary["share_nominal"], summary["share_worst_10pct"], hot_ratio)


if __name__ == "__main__":
    main()
