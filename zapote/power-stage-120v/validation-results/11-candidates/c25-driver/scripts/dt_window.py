#!/usr/bin/env python3
"""c25: dead-time window of the Infineon 2EDR8259H/X STP/DTC pin vs the audit window.

Rerun: python3 -I dt_window.py   (writes ../results/dt_window.json, prints a table)

Datasheet data (Infineon 2EDR8259H/2EDRx259X/2EDRx258X datasheet Rev 1.7, 2026-04-09, Table 19 p.15):
    RDTC 10 k: 85 / 100 / 115 ns   30 k: 255 / 300 / 345 ns   100 k: 800 / 950 / 1100 ns (100 k: design/char. only)
    min/max are "within the full operating range" (section 3.4 heading, p.12). Formula tdt = 10 x RDTC[kohm] (Table 6 p.8).
TI UCC21550 (SLUSE89C 5.8 p.10): 20 k 167/185/203, 50 k 399/443/487 ns; audit.rs `dead_time_window_ns` interpolates
those linearly (D-12) and stacks resistor tolerance and TCR over |dT| = 125 K. The same method is applied here.

Two interpolation models for the 2EDR (both reported, the window is their envelope):
  lin   : linear interpolation of the min and max columns between the bracketing table rows (the audit's method)
  ratio : min/max as a ratio of the 10 x R formula, interpolated between rows (85-115 % at 10/30 k, 80-110 % at 100 k)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "results" / "dt_window.json"
TAB = [(10.0, 85.0, 100.0, 115.0), (30.0, 255.0, 300.0, 345.0), (100.0, 800.0, 950.0, 1100.0)]
AUDIT_WINDOW = (391.0, 498.0)          # audit.rs:591 DT_WINDOW_NS (grid-best-longdt, FINDINGS F7)
TCR_DT = 125.0                          # K, as audit.rs dead_time_window_ns


def interp(r, col):
    for (r0, *a), (r1, *b) in zip(TAB, TAB[1:]):
        if r0 <= r <= r1:
            return a[col] + (r - r0) * (b[col] - a[col]) / (r1 - r0)
    raise ValueError(r)


def ratio(r, col):
    for (r0, *a), (r1, *b) in zip(TAB, TAB[1:]):
        if r0 <= r <= r1:
            q0, q1 = a[col] / (10 * r0), b[col] / (10 * r1)
            return 10 * r * (q0 + (r - r0) * (q1 - q0) / (r1 - r0))
    raise ValueError(r)


def edr_window(r_k, tol, tcr_ppm):
    drift = tcr_ppm * 1e-6 * TCR_DT
    rmin, rmax = r_k * (1 - tol) * (1 - drift), r_k * (1 + tol) * (1 + drift)
    lo = min(interp(rmin, 0), ratio(rmin, 0))
    hi = max(interp(rmax, 2), ratio(rmax, 2))
    return {"R_k": r_k, "tol": tol, "tcr_ppm": tcr_ppm, "typ_lin": round(interp(r_k, 1), 1),
            "typ_formula": round(10 * r_k, 1), "min_lin": round(interp(rmin, 0), 1), "min_ratio": round(ratio(rmin, 0), 1),
            "max_lin": round(interp(rmax, 2), 1), "max_ratio": round(ratio(rmax, 2), 1),
            "window": [round(lo, 1), round(hi, 1)],
            "fits_audit_window": lo >= AUDIT_WINDOW[0] and hi <= AUDIT_WINDOW[1]}


def ucc_window(r_k, tol, tcr_ppm):     # copy of audit.rs dead_time_window_ns (reference)
    drift = tcr_ppm * 1e-6 * 125.0
    rmin, rmax = r_k * (1 - tol) * (1 - drift), r_k * (1 + tol) * (1 + drift)
    return [round(167 + (rmin - 20) * (399 - 167) / 30, 1), round(203 + (rmax - 20) * (487 - 203) / 30, 1)]


def main():
    # Yageo RT0603BRD07 thin film, 0.1 %, 25 ppm/K (as R9/R17 today, audit.rs DT_RESISTORS); E96 values
    cands = [40.2, 42.2, 43.2, 44.2, 45.3, 46.4, 47.5, 48.7, 49.9, 51.1]
    rows = [edr_window(r, 0.001, 25.0) for r in cands]
    # the width alone: a +-15 % part spread cannot fit a +-12.0 % window at any R
    half_width_audit = (AUDIT_WINDOW[1] - AUDIT_WINDOW[0]) / (AUDIT_WINDOW[1] + AUDIT_WINDOW[0])
    res = {"source": "Infineon 2EDR8259H datasheet Rev 1.7 Table 19 p.15; audit.rs:591-605",
           "audit_window_ns": AUDIT_WINDOW, "audit_window_half_width_rel": round(half_width_audit, 4),
           "ucc21550_49k9_ref": ucc_window(49.9, 0.001, 25.0), "edr": rows}
    # minimum R that keeps the lower edge >= 391 ns, and maximum R that keeps the upper edge <= 498 ns
    lo_ok = [r["R_k"] for r in rows if r["window"][0] >= AUDIT_WINDOW[0]]
    hi_ok = [r["R_k"] for r in rows if r["window"][1] <= AUDIT_WINDOW[1]]
    res["min_R_for_lower_edge"] = min(lo_ok) if lo_ok else None
    res["max_R_for_upper_edge"] = max(hi_ok) if hi_ok else None
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(f"audit window {AUDIT_WINDOW} ns (half-width +-{100 * half_width_audit:.1f} %); "
          f"UCC21550 49.9 k reference {res['ucc21550_49k9_ref']}")
    print("| R kohm | typ (interp) | 10xR | min lin/ratio | max lin/ratio | window ns | fits 391-498 |")
    print("| ---: | ---: | ---: | ---: | ---: | --- | --- |")
    for r in rows:
        print(f"| {r['R_k']} | {r['typ_lin']} | {r['typ_formula']} | {r['min_lin']} / {r['min_ratio']} | "
              f"{r['max_lin']} / {r['max_ratio']} | {r['window'][0]}-{r['window'][1]} | {r['fits_audit_window']} |")
    print("lowest R with lower edge >= 391:", res["min_R_for_lower_edge"],
          "| highest R with upper edge <= 498:", res["max_R_for_upper_edge"])


if __name__ == "__main__":
    main()
