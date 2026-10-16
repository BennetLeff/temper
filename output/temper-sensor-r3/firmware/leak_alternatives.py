"""DECISIONS.md D-RIMLIM, candidates B and C: what energy and a cold soak can say about Pt100 leakage.

B. Energy plausibility. A leak compresses the reading's response to the pan:
   dReading/dT_true < 1 at the operating point. Can anything the controller
   observes separate that from a heavier or less efficient pan?
   - the compression factor per leak, where the reading is 250 (and 200) degC;
   - the identified plant gain a = eta / C against its spread over the
     modelled pan classes, eta 0.82-0.92 and a food load (screen.Truth
     food_C), and against the firmware prior bounds (plant_gain.c);
   - the hold power: the steady truth-plant power that holds each pan at
     250 and at 300 degC (GlassTruth, glass delta 12 and 46 K), i.e. what a
     leak that holds a 300 degC pan at a 250 degC reading would draw,
     against what another pan draws at an honest 250 degC;
   - the rim's rise against the Pt100's: the glass follows the pan with a
     weight w of 0.646-0.955 (rim_limit.py envelope).
C. Cold-soak plausibility. After an idle soak every part is at ambient. A
   leak that conducts at room temperature reads low there:
   - the reading error at 5 / 25 / 40 degC for the sweep's leaks;
   - the check threshold from the reference's error budget (the heatsink
     NTC, the only on-board candidate: hs-ntc.json cold_soak_budget, the
     threshold the firmware's cold-soak check uses, DECISIONS D-HSNTC/D-SOAK),
     evaluated at T_EVAL = 35 degC (the point of the pre-C45 analysis, when the
     channel saturated below 28.6-35.7 degC; with the CR-8 divider, zapote C45,
     it is VALID from -40 degC and cold_soak.py covers 5-40 degC);
   - an Arrhenius leak R(T) = R_300 exp(Ea/k (1/T - 1/573.15)), equal to a
     hazardous value at 300 degC: its resistance and reading error at T_EVAL,
     and the activation energy above which C misses it.
   The implemented check, through the firmware's C, is cold_soak.py
   (cold-soak.json); this is the closed-form view.

Writes leak-alternatives.json. Run: python3 leak_alternatives.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import leak_checks as LC  # noqa: E402
import ref  # noqa: E402
import xcheck_cosim as X  # noqa: E402
from ref import es, screen  # noqa: E402

K_B_EV = 8.617333e-5
A_PRIOR = {"a0": 1.8e-3, "a_min": 5e-5, "a_max": 5e-3}   # plant_gain.c defaults, K/J
R_HAZ = 1732.1     # leak-checks.json: the largest hazardous leak (highest R), ohm
# Reference error budget: the heatsink NTC (NTCALUG01A104GA, GPIO6 / ADC1_CH5,
# 10 k pull-up), hs_ntc.py -> hs-ntc.json cold_soak_budget.
HS_NTC_BUDGET = json.loads((HERE / "hs-ntc.json").read_text(encoding="utf-8"))["cold_soak_budget"]
T_EVAL = 35.0


def t_of_reading(reading, r_leak):
    lo, hi = reading, 1500.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if X.pt100_read(mid, r_leak) < reading else (lo, mid)
    return 0.5 * (lo + hi)


def compression(r_leak, reading):
    t = t_of_reading(reading, r_leak)
    d = 0.01
    return t, (X.pt100_read(t + d, r_leak) - X.pt100_read(t - d, r_leak)) / (2 * d)


def pan_c(pan):
    tr = screen.Truth(es.PANS[pan], 1000.0, 0.82, 0)
    return float(tr.C.sum())


def hold_power(pan, t_hold, delta, t_end=2400.0):
    """Mean truth power over the last 300 s, T_c held at t_hold by an ideal PI on T_c."""
    screen.apply(ref.C1)
    h = float(np.sqrt(np.prod(screen.h_spread(ref.C1)[pan])))
    tr = X.GlassTruth(es.PANS[pan], h, 1.0, 0, delta=delta)
    tr.Tg = t_hold - delta
    tr.T[:] = t_hold
    integ, ps = 0.0, []
    n = int(t_end / es.DT_SIM)
    for k in range(n):
        e = t_hold - tr.T_c()
        integ += e * es.DT_SIM
        p = min(max(200.0 * e + 2.0 * integ, 0.0), 1e4)
        tr.step(p, h)
        if k * es.DT_SIM >= t_end - 300.0:
            ps.append(p)
    return float(np.mean(ps))


def main():
    out = {"scope": __doc__.strip()}
    # ---- B ---------------------------------------------------------------
    comp = {}
    for r in LC.R_LEAKS:
        row = {}
        for rd in (200.0, 250.0):
            t, s = compression(r, rd)
            row[f"reading_{int(rd)}"] = {"T_true_C": round(t, 1), "dReading_dT": round(s, 3)}
        comp[str(round(r, 1))] = row
    screen.apply(ref.C1)
    cls = {}
    for pan in es.PANS:
        c = pan_c(pan) + (4186.0 * es.PANS[pan]["water_kg"])
        cls[pan] = {"C_J_per_K": round(c, 0), "a_eta082": 0.82 / c, "a_eta092": 0.92 / c,
                    "a_eta082_food": 0.82 / (c + screen.Truth.food_C)}
    a_all = [v for d in cls.values() for v in (d["a_eta082"], d["a_eta092"], d["a_eta082_food"])]
    a_fry = [v for p, d in cls.items() if p != "disc_pot_water_1l5"
             for v in (d["a_eta082"], d["a_eta092"], d["a_eta082_food"])]
    hp = {}
    for pan in es.PANS:
        if pan == "disc_pot_water_1l5":
            continue
        for delta in (12.0, 46.0):
            hp[f"{pan} delta {int(delta)}"] = {str(int(t)): round(hold_power(pan, t, delta), 1) for t in (250, 300)}
    p250 = [v["250"] for v in hp.values()]
    p300 = [v["300"] for v in hp.values()]
    out["B"] = {
        "compression_dReading_dT_by_r_leak": comp,
        "plant_gain_by_class": cls,
        "a_spread_frying_ratio_max_min": round(max(a_fry) / min(a_fry), 2),
        "a_spread_all_ratio_max_min": round(max(a_all) / min(a_all), 2),
        "a_prior_bounds_ratio": A_PRIOR["a_max"] / A_PRIOR["a_min"],
        "hold_power_W_eta1": hp,
        "hold_power_250_range_W": [min(p250), max(p250)], "hold_power_300_range_W": [min(p300), max(p300)],
        "hold_power_300_over_250_same_pan": [round(min(v["300"] / v["250"] for v in hp.values()), 3),
                                             round(max(v["300"] / v["250"] for v in hp.values()), 3)],
        "rim_weight_w_range": [0.6457, 0.9554],
        "verdict": "does not separate. The hazardous leaks compress dReading/dT_true to "
                   f"{min(comp[str(round(r, 1))]['reading_250']['dReading_dT'] for r in LC.R_LEAKS if r <= R_HAZ):.2f}"
                   f"-{max(comp[str(round(r, 1))]['reading_250']['dReading_dT'] for r in LC.R_LEAKS if r <= R_HAZ):.2f}"
                   f" at a 250 degC reading; the identified a spans {max(a_fry) / min(a_fry):.1f}x over the three "
                   "modelled frying pans with eta and food alone (the prior bounds 100x), so a leak looks like a "
                   "heavier pan. Holding a pan at 300 instead of 250 degC costs "
                   f"{min(v['300'] / v['250'] for v in hp.values()):.2f}-{max(v['300'] / v['250'] for v in hp.values()):.2f}"
                   f"x the power; the honest 250 degC hold power already spans {max(p250) / min(p250):.2f}x over "
                   "three modelled pans (real pan sizes spread it further) and the firmware has only commanded "
                   "power with eta unknown (0.82-0.92). The rim follows the pan with a weight of 0.65-0.96, a "
                   "wider spread than the compression of the leaks that matter (0.77 at 1.73 kohm).",
    }
    # ---- C ---------------------------------------------------------------
    cold = {}
    for r in LC.R_LEAKS:
        cold[str(round(r, 1))] = {str(t): round(t - X.pt100_read(float(t), r), 2) for t in (5, 25, 40)}
    thr = HS_NTC_BUDGET["threshold_K"]
    thr_c = HS_NTC_BUDGET["threshold_rail_corrected_K"]

    def largest_r_caught(th, t=T_EVAL):
        lo, hi = 100.0, 1e7
        for _ in range(100):
            mid = math.sqrt(lo * hi)
            lo, hi = (mid, hi) if t - X.pt100_read(t, mid) > th else (lo, mid)
        return round(lo, -1)

    te_k = T_EVAL + 273.15
    arr = []
    for ea in (0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0):
        r_e = R_HAZ * math.exp(ea / K_B_EV * (1 / te_k - 1 / 573.15))
        low = T_EVAL - X.pt100_read(T_EVAL, r_e)
        arr.append({"Ea_eV": ea, "R_at_300C_ohm": R_HAZ, "R_at_35C_ohm": round(r_e, 0),
                    "reading_low_at_35C_K": round(low, 3),
                    "caught_at_threshold": low > thr, "caught_rail_corrected": low > thr_c})

    def ea_max(th):
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            r_e = R_HAZ * math.exp(mid / K_B_EV * (1 / te_k - 1 / 573.15))
            lo, hi = (mid, hi) if T_EVAL - X.pt100_read(T_EVAL, r_e) > th else (lo, mid)
        return round(lo, 4)

    out["C"] = {"reading_low_K_temperature_independent_leak": cold,
                "reference": "heatsink NTC (NTCALUG01A104GA, GPIO6 / ADC1_CH5, components/sensors/hs_ntc.c; "
                             "DECISIONS D-HSNTC), through the CR-8 divider (zapote C45): VALID from -40 degC, so C "
                             "runs at room temperature; the check is implemented "
                             "(components/control/pan_cold_soak.c, D-SOAK) and run through the C in cold_soak.py",
                "t_eval_C": T_EVAL,
                "threshold_budget_K": {"source": "hs-ntc.json cold_soak_budget", "band_C": HS_NTC_BUDGET["band_C"]},
                "threshold_K": thr, "threshold_rail_corrected_K": thr_c,
                "largest_r_caught_at_35C_ohm": largest_r_caught(thr),
                "largest_r_caught_at_35C_rail_corrected_ohm": largest_r_caught(thr_c),
                "hazardous_r_leak_reading_low_at_25C_K": cold[str(R_HAZ)]["25"],
                "hazardous_r_leak_reading_low_at_35C_K": round(T_EVAL - X.pt100_read(T_EVAL, R_HAZ), 2),
                "arrhenius_equal_to_hazardous_at_300C": arr,
                "arrhenius_Ea_max_caught_eV": ea_max(thr),
                "arrhenius_Ea_max_caught_rail_corrected_eV": ea_max(thr_c)}
    Path(HERE / "leak-alternatives.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out["B"].items() if k not in ("compression_dReading_dT_by_r_leak",
                                                                      "plant_gain_by_class")}, indent=1))
    print({r: v["reading_250"] for r, v in comp.items()})
    print(json.dumps({k: v for k, v in out["C"].items() if k != "reading_low_K_temperature_independent_leak"},
                     indent=1))
    print(cold)
    return 0


if __name__ == "__main__":
    sys.exit(main())
