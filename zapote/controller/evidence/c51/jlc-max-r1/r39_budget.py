#!/usr/bin/env python3
"""R39 (pan MAX31865 Rref) candidates against the CR-2 budget and the hardware trips. Offline, no network.

Runs the committed sensor-r3 checks (../../sensor-r3-checks/checks.py on the as-built netlist, the same
path run_as_built.py takes) with only R39's value / tolerance / TCR changed:
  1a  range and resolution (-20..320 C)
  1b  CR-2 front-end error after single-point gain cal, 40-250 C, board |dT| 60 K (gate: board terms <= 0.30 K
      AND RSS <= 0.30 K)
  8   hardware runaway band (20 k / 10 k divider from BIAS; depends on Rref) vs 270-325 C
plus the MAX31865 threshold words (tools/controller_calcs.max31865_thresholds), the error with NO gain cal
(firmware today divides by a fixed 430.0), and the largest board |dT| at which 1b still passes.

usage: python3 r39_budget.py   -> r39-budget.json
"""
import json, math, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
UNIT = HERE.parents[2]
sys.path.insert(0, str(UNIT / "evidence/sensor-r3-checks"))
sys.path.insert(0, str(UNIT / "tools"))
import run_as_built  # noqa: E402  (imports checks.py the same way the as-built run does)
import checks  # noqa: E402
from controller_calcs import max31865_thresholds  # noqa: E402

G1B = "1b front-end error after single-point cal, 40-250 C"
G1A = "1a range -20..320 C and resolution <=0.05 K"
G8 = "8 hardware trips vs 250 C max setpoint"

# (label, LCSC, rref ohm, tolerance, TCR /K, package); TCR and tolerance are JLC's attributes (reads/detail_*.json),
# PTFR checked against the RESI PTFR datasheet ordering code (README).
VARIANTS = [
    ("RG2012V-431-W-T1 (fitted, consigned)", "C4260028", 430.0, 5e-4, 5e-6, "0805"),
    ("PTFR0805B430RN9", "C351565", 430.0, 1e-3, 10e-6, "0805"),
    ("PTFR0603B430RN9", "C2692824", 430.0, 1e-3, 10e-6, "0603"),
    ("RT0805BRD07430RL (C35 swap, reverted by C37)", "C865488", 430.0, 1e-3, 25e-6, "0805"),
    ("PTFR0402B402RN9", "C2692962", 402.0, 1e-3, 10e-6, "0402"),
    ("RN73C2A402RBTDF", "C4093972", 402.0, 1e-3, 10e-6, "0805"),
]


def run(built, rref, tol, tc, items):
    checks.CHECKS.clear()
    checks.RREF = rref
    checks.DESIGNS["proposed"] = dict(built, rref=rref, rref_tol=tol, rref_tc=tc)
    for fn in items:
        fn()
    return {k: v for k, v in checks.CHECKS.items()}


def max_dt(built, rref, tol, tc):
    """Largest board |dT| (K, 1 K steps) at which 1b passes: the Rref term is tc x dT x R, so dT enters as tc x dT / 60."""
    lo = 0
    for dt in range(0, 61):
        c = run(built, rref, tol, tc * dt / 60.0, [checks.item1_accuracy])[G1B]
        if not c["pass"]:
            break
        lo = dt
    return lo


def main():
    built, _ = run_as_built.as_built()
    out = {"source": "sensor-r3 checks.py (as built) with R39 substituted; controller_calcs.max31865_thresholds",
           "board_dT_K_in_gate": 60.0, "variants": []}
    for label, lcsc, rref, tol, tc, pkg in VARIANTS:
        c = run(built, rref, tol, tc, [checks.item1_range_resolution, checks.item1_accuracy, checks.item8_trips])
        p = c[G1B]["detail"]["proposed"]
        a250 = p["at_250C"]
        r250, d250 = checks.pt(250.0), checks.dpt(250.0)
        th = max31865_thresholds(rref=rref)
        row = {"part": label, "lcsc": lcsc, "rref_ohm": rref, "tol": tol, "tcr_per_K": tc, "package": pkg,
               "1a_pass": c[G1A]["pass"], "R320_over_Rref_min": c[G1A]["detail"]["R320_over_Rref_min"],
               "worst_LSB_K": c[G1A]["detail"]["worst_LSB_K"],
               "1b_pass": c[G1B]["pass"], "1b_worst_board_terms_K": p["worst_board_terms_K"],
               "1b_worst_rss_K": p["worst_rss_K"], "1b_worst_linear_K": p["worst_linear_K"],
               "Rref_tempco_K_at_250C": a250["Rref_tempco_K"], "Rref_tempco_K_at_100C": p["at_100C"]["Rref_tempco_K"],
               "no_gain_cal_tolerance_K_at_250C": round(tol * r250 / d250, 3),
               "no_gain_cal_tolerance_plus_tempco_K_at_250C": round((tol + tc * 60) * r250 / d250, 3),
               "8_pass": c[G8]["pass"], "runaway_band_C": c[G8]["detail"]["rtd_runaway_band_C"],
               "threshold_words": {"high": th["high_word"], "low": th["low_word"],
                                   "high_trip_C": round(th["high_trip_C"], 3), "low_trip_C": round(th["low_trip_C"], 3)},
               "1b_max_board_dT_K": max_dt(built, rref, tol, tc)}
        out["variants"].append(row)
        print(json.dumps(row))
    (HERE / "r39-budget.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
