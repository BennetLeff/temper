#!/usr/bin/env python3
"""c54: touch-current (OPEN-ITEMS S1) breakdown, tolerance corners, C3/C4 options, and the EMI / HF trade.

Stdlib only for the leakage part. Imports the committed 60 Hz model read-only
(validation-results/07-conducted-emi/leakage/leakage_budget.py; its main() is never called, so its result.json is not
rewritten) and the committed EMI model's BASE dict (07-conducted-emi/s19b/emi_s19b.py, module import only) for the
HV-node parasitic capacitances. Reads the EMI / HF runs this folder made (results/emi-*/results.json from emi_y.py,
results/hf_touch.json from hf_y.py) when present.

Run: python3 -I scripts/leakage_c54.py   -> results/summary.json ; exit 1 if a control fails.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results"
PS = HERE.parents[3]
LB_PATH = PS / "validation-results/07-conducted-emi/leakage/leakage_budget.py"
LB_RESULT = PS / "validation-results/07-conducted-emi/leakage/result.json"
S19B = PS / "validation-results/07-conducted-emi/s19b/emi_s19b.py"
SCORECARD_EMI = PS / "validation-results/11-candidates/b15-proto-alternates/results/emi-B82726S2243A020_moduleDM100u/results.json"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lb = load("leakage_budget_ro", LB_PATH)
W = lb.W
LIMIT, LIMIT_STAT, BUDGET = 0.5, 0.75, lb.PASS_FRACTION * lb.LIMIT_MA
SUPPLIES = [m for _, m in lb.SYSTEMS["s38"]["supplies"]]  # MPM-20-24 (PS2), MPM-65-15ST (PS3)
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"[{'OK ' if ok else 'BAD'}] {name} {detail}")


def i_ma(c_f, v):
    return W * c_f * v * 1e3


def touch(y_nF=(2.2, 2.2), v=lb.V_LINE, ytol=lb.TOL, ffac=lb.SUPPLY_FREQ_FACTOR, coil_pF=31.0, extra_pF=0.0):
    """Open-PE touch current per polarity, the committed rule, with C3 (L) and C4 (N) separately.
    Polarity 'L hot': the meter (chassis to earth) sees the L-side Y; N is at earth, so C4 is shorted (and vice versa).
    Returns (worst, per-polarity dict, items for the worst polarity)."""
    common = [("coil-to-PE %.0f pF (+20 %%)" % coil_pF, i_ma(coil_pF * 1e-12 * 1.2, v))]
    if extra_pF:
        common.append(("HV-node parasitics %.1f pF (bound, full line V)" % extra_pF, i_ma(extra_pF * 1e-12, v)))
    for s in SUPPLIES:
        mx, vt, _ = lb.SUPPLY_MAX[s]
        common.append((f"{s} datasheet max x{v:.1f}/{vt:.0f} V x{ffac:.2f}", mx * (v / vt) * ffac))
    pol = {}
    for side, c in (("L_hot", y_nF[0]), ("N_hot", y_nF[1])):
        items = [(f"Y {c} nF (+{ytol*100:.0f} %)", i_ma(c * 1e-9 * (1 + ytol), v))] + common
        pol[side] = (sum(x for _, x in items), items)
    worst = max(pol, key=lambda k: pol[k][0])
    return pol[worst][0], {k: v_[0] for k, v_ in pol.items()}, pol[worst][1]


def main() -> int:
    out = {"basis": {"V": lb.V_LINE, "f_Hz": lb.F_LINE, "Y_tol": lb.TOL, "supply_freq_factor": lb.SUPPLY_FREQ_FACTOR,
                     "limit_portable_mA": LIMIT, "limit_stationary_mA": LIMIT_STAT, "budget_mA": BUDGET}}
    # ---------------- controls
    design = lb.evaluate("DESIGN", lb.build())
    committed = json.loads(LB_RESULT.read_text())["results"][0]["governing_touch_mA"]
    t0, pol0, items0 = touch()
    check("committed DESIGN row reproduced by the imported model", abs(design["governing_touch_mA"] - committed) < 1e-12,
          f"{design['governing_touch_mA']:.10f} vs result.json {committed:.10f}")
    check("c54 per-polarity rule == committed rule at the basis", abs(t0 - committed) < 1e-12, f"{t0:.10f}")

    # ---------------- 1. breakdown at the basis, and the same with nominal parts
    tn, _, items_n = touch(ytol=0.0, ffac=1.0)
    br = []
    for (name, ma), (_, man) in zip(items0, items_n):
        br.append({"item": name, "mA_basis": ma, "share_pct": 100 * ma / t0, "mA_nominal_tol_and_60Hz_test": man})
    br.append({"item": "SCF31X-220-2R1A011JH inlet CM choke (module, stage 38)", "mA_basis": 0.0, "share_pct": 0.0,
               "mA_nominal_tol_and_60Hz_test": 0.0,
               "note": "no PE terminal: series element, no 60 Hz path to PE (the module's four Y caps were removed at s38)"})
    out["breakdown"] = {"total_mA": t0, "per_polarity_mA": pol0, "items": br,
                        "total_nominal_Y_and_supplies_tested_at_60Hz_mA": tn,
                        "per_nF_per_line_mA": i_ma(1.2e-9, lb.V_LINE)}
    print(f"\nbreakdown at {lb.V_LINE} V / 60 Hz / Y +20 % / supplies x1.2: {t0:.4f} mA")
    for b in br:
        print(f"   {b['item']:<52s} {b['mA_basis']:.4f} mA ({b['share_pct']:4.1f} %)   nominal/x1.0: {b['mA_nominal_tol_and_60Hz_test']:.4f}")

    # ---------------- parasitic HV-node capacitance (outside the committed model): bound
    s19 = load("emi_s19b_ro", S19B)
    nomp = json.loads(SCORECARD_EMI.read_text())["inputs"]["nominal_params"]
    par = {"CBRP bus_p-PE": s19.BASE["CBRP"], "CBRN bus_n-PE": s19.BASE["CBRN"], "2 x CTABH (Q2/Q5 tabs)": 2 * nomp["CTABH"],
           "CTABA + CPOURA (sw_a)": nomp["CTABA"] + nomp["CPOURA"], "CTABB + CPOURB (sw_b)": nomp["CTABB"] + nomp["CPOURB"]}
    par_pF = sum(par.values()) * 1e12
    t_par, _, _ = touch(extra_pF=par_pF)
    out["parasitic_bound"] = {"caps_pF": {k: v * 1e12 for k, v in par.items()}, "total_pF": par_pF,
                              "mA_at_full_line_V": t_par - t0, "touch_with_bound_mA": t_par,
                              "note": "every HV node charged at the full 132 V line amplitude: an upper bound (the bus "
                                      "nodes' 60 Hz component to PE is at most the line). Coil 31 pF is already in the rule."}
    print(f"HV-node parasitics {par_pF:.1f} pF -> +{(t_par - t0)*1e3:.2f} uA (bound) -> {t_par:.4f} mA")

    # ---------------- 2. corners
    corners = []
    for v in (120.0, 127.0, 132.0, 134.62, 139.7):
        for ytol in (0.0, 0.1, 0.2):
            for ff in (1.0, 1.2):
                t, _, _ = touch(v=v, ytol=ytol, ffac=ff)
                corners.append({"V": v, "Y_tol": ytol, "supply_freq_factor": ff, "touch_mA": t,
                                "pct_of_0.5": 100 * t / LIMIT, "margin_to_budget_mA": BUDGET - t})
    out["corners"] = corners
    worst_c = max(corners, key=lambda c: c["touch_mA"])
    print(f"corners: 120 V nominal parts {corners[0]['touch_mA']:.4f} mA ... worst {worst_c['touch_mA']:.4f} mA at "
          f"{worst_c['V']} V (127 V + 10 %), Y +20 %, x1.2 = {worst_c['pct_of_0.5']:.1f} % of 0.5 mA")

    # ---------------- 3. options (60 Hz rule) + EMI + HF
    emi = {}
    for tag in ("bor-Y2.2", "bor-Y1.5", "bor-Y1.0", "prod-Y2.2", "prod-Y1.5"):
        p = RES / f"emi-{tag}" / "results.json"
        if p.exists():
            v = json.loads(p.read_text())["verdict"]
            emi[tag] = {k: v[k] for k in ("nominal_min_margin_dB", "sensitivity_min_margin_22A_dB",
                                          "sensitivity_min_margin_all_dB", "verdict")}
    if "bor-Y2.2" in emi:
        sc = json.loads(SCORECARD_EMI.read_text())["verdict"]
        check("EMI control: bor CY 2.2 reproduces the scorecard source", abs(emi["bor-Y2.2"]["nominal_min_margin_dB"] -
              sc["nominal_min_margin_dB"]) < 1e-6 and abs(emi["bor-Y2.2"]["sensitivity_min_margin_all_dB"] -
              sc["sensitivity_min_margin_all_dB"]) < 1e-6,
              f"{emi['bor-Y2.2']['nominal_min_margin_dB']:.6f} / {emi['bor-Y2.2']['sensitivity_min_margin_all_dB']:.6f} dB")
    if "prod-Y2.2" in emi:
        s19r = json.loads((PS / "validation-results/07-conducted-emi/s19b/results.json").read_text())["verdict"]
        check("EMI control: prod CY 2.2 reproduces committed s19b results.json",
              abs(emi["prod-Y2.2"]["nominal_min_margin_dB"] - s19r["nominal_min_margin_dB"]) < 1e-6,
              f"{emi['prod-Y2.2']['nominal_min_margin_dB']:.6f} vs {s19r['nominal_min_margin_dB']:.6f}")
    hf = json.loads((RES / "hf_touch.json").read_text()) if (RES / "hf_touch.json").exists() else None

    opts = []
    for name, y, emitag in (("O0 as built: C3/C4 2.2 nF", (2.2, 2.2), "bor-Y2.2"),
                            ("O1 C3/C4 -> 1.5 nF (DE1E3RA152MJ4BH01F)", (1.5, 1.5), "bor-Y1.5"),
                            ("O2 C3/C4 -> 1.0 nF (DE1E3RA102MJ4BH01F)", (1.0, 1.0), "bor-Y1.0"),
                            ("O3 delete C4 (one Y, L side only)", (2.2, 0.0), None),
                            ("O4 no Y at all", (0.0, 0.0), None)):
        t, pol, _ = touch(y_nF=y)
        o = {"option": name, "Y_nF_L_N": y, "touch_60Hz_mA": t, "per_polarity_mA": pol,
             "margin_to_budget_mA": BUDGET - t, "margin_to_budget_pct": 100 * (BUDGET - t) / BUDGET,
             "pct_of_0.5": 100 * t / LIMIT, "pct_of_0.75": 100 * t / LIMIT_STAT,
             "extra_Y_per_line_nF_before_budget_fail": (BUDGET - t) / i_ma(1.2e-9, lb.V_LINE)}
        if emitag and emitag in emi:
            o["emi_board_of_record"] = emi[emitag]
        if hf and y[0] == y[1] and f"Y{y[0]}" in hf["options"]:
            c = hf["options"][f"Y{y[0]}"]["corners"]
            ul_nom = c["nominal"]["lisn_mains_ul101"]["weighted_mA"]
            ul_worst_k = max(c, key=lambda k: c[k]["lisn_mains_ul101"]["weighted_mA"])
            ul_worst = c[ul_worst_k]["lisn_mains_ul101"]["weighted_mA"]
            iec_worst = max(c[k]["lisn_mains_iec60990"]["weighted_mA"] for k in c)
            o["hf_touch_estimate"] = {"UL_meter_nominal_mA": ul_nom, "UL_meter_worst_mA": ul_worst,
                                      "UL_meter_worst_corner": ul_worst_k, "IEC60990_worst_mA": iec_worst,
                                      "lab_reading_estimate_nominal_mA": math.hypot(t, ul_nom),
                                      "lab_reading_estimate_worst_mA": math.hypot(t, ul_worst),
                                      "lab_reading_worst_pct_of_0.5": 100 * math.hypot(t, ul_worst) / LIMIT}
        opts.append(o)
    out["options"] = opts
    print("\noptions (60 Hz rule; EMI on the board of record: L1 2243 + module DM 100 uH; HF UL-meter estimate):")
    for o in opts:
        e = o.get("emi_board_of_record", {})
        h = o.get("hf_touch_estimate", {})
        print(f"  {o['option']:<44s} {o['touch_60Hz_mA']:.4f} mA  margin {o['margin_to_budget_mA']*1e3:+6.1f} uA "
              f"({o['margin_to_budget_pct']:+5.1f} %)  EMI nom/sens {e.get('nominal_min_margin_dB', float('nan')):5.2f}/"
              f"{e.get('sensitivity_min_margin_all_dB', float('nan')):5.2f} dB {e.get('verdict', '-'):12s} "
              f"lab-est nom/worst {h.get('lab_reading_estimate_nominal_mA', float('nan')):.4f}/"
              f"{h.get('lab_reading_estimate_worst_mA', float('nan')):.4f} mA")
    check("O3 (one Y) does not lower the worst polarity", abs(opts[3]["touch_60Hz_mA"] - opts[0]["touch_60Hz_mA"]) < 1e-12)

    # ---------------- 4. basis variants (no hardware change)
    t_60, _, _ = touch(ffac=1.0)
    out["basis_variants"] = {
        "supplies_tested_at_60Hz_(factor_1.0)": {"touch_mA": t_60, "margin_to_budget_mA": BUDGET - t_60},
        "supply_scale_factor_that_fails_budget": 1 + (BUDGET - t0) / sum(
            lb.SUPPLY_MAX[s][0] * lb.V_LINE / lb.SUPPLY_MAX[s][1] * lb.SUPPLY_FREQ_FACTOR for s in SUPPLIES),
        "rated_120V_nominal_parts_supplies_x1.0": corners[0]["touch_mA"],
    }
    out["emi"] = emi
    out["checks"] = CHECKS
    (RES / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {RES / 'summary.json'}")
    return 0 if all(c["ok"] for c in CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
