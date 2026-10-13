#!/usr/bin/env python3 -I
"""F5 leakage / touch-current budget, Temper native-21 power stage (120 V, 60 Hz, NEMA 5-15P, Class I).

Desk calculation, stdlib only.  Run:  python3 -I leakage_budget.py
Writes result.json next to this file and prints PASS/FAIL (exit 0 = design verdict PASS
and control FAIL as required; exit 1 otherwise).  See README.md for sources and caveats.
"""
import json, math, os, sys

V_LINE = 132.0          # V rms, 120 V + 10 %  (task spec)
F_LINE = 60.0           # Hz
W = 2 * math.pi * F_LINE
LIMIT_MA = 0.5          # UL 1026 grounded portable cord-connected appliance (secondary source, see README)
LIMIT_IEC_MA = 0.75     # IEC 60335-1 cl. 13.2/16.2 Class I portable (reference only; secondary source)
PASS_FRACTION = 0.5     # fixed pass rule: total <= 50 % of chosen limit
TOL = 0.20              # +20 % capacitor tolerance (all Y parts here are +/-20 %)

def i_ma(c_f, v=V_LINE):
    """Capacitive line-frequency current in mA rms for capacitance c_f [F] at v volts."""
    return W * c_f * v * 1e3

# ---- per-line capacitance sources (each entry counts on EACH of L and N unless 'side' says otherwise)
# board Y: C3 L_FILT-PE, C4 N_FILT-PE, Murata DE1E3RA222MA4BP01F 2.2 nF +/-20 %
#   (elec/src/power_stage_120v.ato:346-351,992-993; parts.ato:117-123 CapY1_2n2)
# module Y: D-22 inlet module, per conductor 4.7 nF || 2.2 nF, TDK B32021A3472M000 + B32021A3222M000, +/-20 %
#   (out-D22/PARTS.md "Main Y capacitors", "HF Y capacitors"; s19b README sec 9.2)
# supplies: MEAN WELL datasheet MAX leakage 0.25 mA @ 277 Vac (IRM-20-SPEC 2025-11-21 and IRM-60-SPEC
#   2025-11-21, PDF p.2 spec table, row LEAKAGE CURRENT).  Class II, no FG pin.  Datasheet gives no test
#   frequency: scale linearly in V and assume the test was 50 Hz (conservative x60/50).  Datasheet is a
#   per-line bound (a single measured line-to-output current), so it is charged to each line.
# coil-PE: 31.0 pF, pan floating (DECISIONS.md item 20, 2026-10-13 update; enclosure study 16); one end of the
#   coil; at 60 Hz it is charged to a line via the bus (conservative: to both).
SUPPLY_LEAK_MA_277 = 0.25
SUPPLY_FREQ_FACTOR = 60.0 / 50.0

def supply_ma(n=1):
    return n * SUPPLY_LEAK_MA_277 * (V_LINE / 277.0) * SUPPLY_FREQ_FACTOR

def build(extra_y_per_line_f=0.0, supply_mode="datasheet_max"):
    """Return per-line contributions (mA) at V_LINE, tolerance applied."""
    items = []
    def cap(name, c_nom, src):
        items.append(dict(name=name, c_nom_nF=c_nom * 1e9, mA=i_ma(c_nom * (1 + TOL)), src=src))
    cap("C3/C4 board Y (2.2 nF, +20 %)", 2.2e-9, "power_stage_120v.ato:346-351; parts.ato:117")
    cap("D-22 module Y (4.7+2.2 nF, +20 %)", 6.9e-9, "out-D22/PARTS.md Main/HF Y")
    if extra_y_per_line_f:
        cap("CONTROL extra Y per line", extra_y_per_line_f, "hypothetical")
    cap("coil-to-PE 31 pF (+20 %)", 31e-12, "DECISIONS.md item 20")
    for ps, mpn in (("PS1", "IRM-20-15"), ("PS2", "IRM-20-24"), ("PS3", "IRM-60-15ST")):
        if supply_mode == "datasheet_max":
            ma = supply_ma()
        else:  # measured typical, informational only: Simpex IRM-20-15 test report 0.015 mA @ 240 V
            ma = 0.015 * (V_LINE / 240.0) * SUPPLY_FREQ_FACTOR
        items.append(dict(name=f"{ps} {mpn} leakage", c_nom_nF=None, mA=ma,
                          src="IRM-20/60-SPEC 2025-11-21 p.2" if supply_mode == "datasheet_max"
                              else "Simpex IRM-20-15 report (typical, 1 unit)"))
    return items

def scenarios(items):
    side = sum(i["mA"] for i in items)           # one line's capacitance/leakage to PE
    # Blower: DC fan on PS3 15 V output (stage16 PLAN-16 fan law) -> no extra mains-referred path.
    return {
        # UL 1026 leakage test is run with the attachment-plug ground open, both polarities
        # (IAEI UL Question Corner).  Chassis shorted to earth via the meter: the other line's Y caps are
        # shorted by N=earth, so touch current = V*w*C of the HOT-side line.  Symmetric board -> same per polarity.
        "open_PE_touch_per_polarity_mA": side,
        # PE intact: earthed accessible parts see ~0 touch current; PE conductor carries both lines.
        "normal_PE_intact_PE_conductor_mA": 2 * side,
        # Open neutral, PE intact: internal N node floats to ~line potential; both sides drive PE.
        "open_N_PE_intact_PE_conductor_mA": 2 * side,
    }

def evaluate(label, items):
    sc = scenarios(items)
    gov = sc["open_PE_touch_per_polarity_mA"]            # governing touch current
    budget = PASS_FRACTION * LIMIT_MA
    verdict = "PASS" if gov <= budget else "FAIL"
    return dict(label=label, items=items, scenarios=sc, governing_touch_mA=gov,
                budget_mA=budget, limit_mA=LIMIT_MA, margin_mA=budget - gov,
                margin_pct_of_budget=100 * (budget - gov) / budget,
                pct_of_limit=100 * gov / LIMIT_MA,
                vs_iec_0p75_pct=100 * gov / LIMIT_IEC_MA, verdict=verdict)

def main():
    design = evaluate("DESIGN (datasheet-max supplies)", build())
    typical = evaluate("INFORMATIONAL (typical-measured supplies)", build(supply_mode="typical"))
    control = evaluate("CONTROL (+10 nF Y per line; must FAIL)", build(extra_y_per_line_f=10e-9))
    ysplit = evaluate("INFORMATIONAL (no module Y, board Y only, typical supplies)",
                      [i for i in build(supply_mode="typical") if "module" not in i["name"]])
    # Discriminating control: the passing variant (board Y only) plus 10 nF/line must flip to FAIL.
    ctl2_items = [i for i in build(extra_y_per_line_f=10e-9, supply_mode="typical") if "module" not in i["name"]]
    control2 = evaluate("CONTROL 2 (board-only variant + 10 nF Y per line; must FAIL)", ctl2_items)
    # Max total C per line allowed at the 50 % budget, 132 V, 60 Hz (including +20 % on Y):
    c_budget_nF = PASS_FRACTION * LIMIT_MA * 1e-3 / (W * V_LINE) * 1e9
    out = dict(V=V_LINE, f=F_LINE, limit_mA=LIMIT_MA, pass_fraction=PASS_FRACTION,
               budget_mA=PASS_FRACTION * LIMIT_MA, max_total_C_per_line_nF_at_budget=c_budget_nF,
               results=[design, typical, ysplit, control, control2])
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "result.json"), "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print(f"Limit {LIMIT_MA} mA (UL 1026 grounded portable; IEC 60335-1 ref {LIMIT_IEC_MA} mA); "
          f"budget = {PASS_FRACTION:.0%} = {PASS_FRACTION*LIMIT_MA:.3f} mA; {V_LINE} V {F_LINE} Hz")
    print(f"Max total C-to-PE per line at budget: {c_budget_nF:.2f} nF (incl. tolerance)")
    for r in (design, typical, ysplit, control, control2):
        print(f"\n== {r['label']}")
        for i in r["items"]:
            print(f"   {i['name']:<36s} {i['mA']:7.4f} mA   [{i['src']}]")
        s = r["scenarios"]
        print(f"   open-PE touch current, per polarity (governing): {r['governing_touch_mA']:.3f} mA "
              f"= {r['pct_of_limit']:.0f} % of limit, {r['vs_iec_0p75_pct']:.0f} % of IEC 0.75 mA")
        print(f"   PE-intact PE-conductor current (info): normal {s['normal_PE_intact_PE_conductor_mA']:.3f} mA, "
              f"open-N {s['open_N_PE_intact_PE_conductor_mA']:.3f} mA")
        print(f"   budget {r['budget_mA']:.3f} mA, margin {r['margin_mA']:+.3f} mA "
              f"({r['margin_pct_of_budget']:+.0f} % of budget) -> {r['verdict']}")
    ok_control = control["verdict"] == "FAIL" and control2["verdict"] == "FAIL" and ysplit["verdict"] == "PASS"
    print(f"\nCONTROL check (both controls FAIL, board-only reference PASSes): {'OK' if ok_control else 'BROKEN'}")
    print(f"F5 DESIGN VERDICT: {design['verdict']}")
    return 0 if (design["verdict"] == "PASS" and ok_control) else 1

if __name__ == "__main__":
    sys.exit(main())
