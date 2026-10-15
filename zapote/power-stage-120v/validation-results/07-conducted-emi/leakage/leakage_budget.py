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
# Stage 38 (candidate 23, DECISIONS 47): datasheet maximum touch / leakage current per mains-connected supply:
# (mA, test V, source).  MPM rows: "LEAKAGE CURRENT (max.) Touch current <80uA/264VAC" (MPM-20) and "<100uA/264VAC"
# (MPM-65), Note 7 / Note 6 "Touch current was measured from primary input to DC output" (the path this model charges).
SUPPLY_MAX = {
    "IRM-20-15": (0.25, 277.0, "MEAN WELL IRM-20-SPEC 2025-11-21 p.2 (< 0.25mA/277Vac)"),
    "IRM-20-24": (0.25, 277.0, "MEAN WELL IRM-20-SPEC 2025-11-21 p.2 (< 0.25mA/277Vac)"),
    "IRM-60-15ST": (0.25, 277.0, "MEAN WELL IRM-60-SPEC 2025-11-21 p.2 (< 0.25mA/277Vac)"),
    "MPM-20-24": (0.080, 264.0, "MEAN WELL MPM-20-SPEC 2024-10-30 p.2 (Touch current <80uA/264VAC, Note 7)"),
    "MPM-65-15ST": (0.100, 264.0, "MEAN WELL MPM-65-SPEC 2024-10-30 p.2 (Touch current <100uA/264VAC, Note 6)"),
}
# The system as built.  s38 (stage 38): PS1 deleted (the controller logic runs from PS3 over J13), PS2 = MPM-20-24 on
# the board, PS3 = MPM-65-15ST in the chassis (controller request, addendum item 6), and the D-22 inlet module's four Y
# caps removed (its CM choke -> KEMET SCF31X 5.68 mH, an EMI change only).  s35: the committed design before stage 38,
# kept as the regression anchor (0.9741 mA).
SYSTEMS = {
    "s38": dict(module_y_nF=0.0, supplies=(("PS2", "MPM-20-24"), ("PS3", "MPM-65-15ST")),
                note="stage 38: PS1 deleted, PS2 MPM-20-24, PS3 MPM-65-15ST, D-22 module Y removed (DECISIONS 47)"),
    "s35": dict(module_y_nF=6.9, supplies=(("PS1", "IRM-20-15"), ("PS2", "IRM-20-24"), ("PS3", "IRM-60-15ST")),
                note="stage 35 / before stage 38: three IRM supplies, D-22 module Y 4.7 + 2.2 nF per conductor"),
}

def supply_ma(mpn="IRM-20-15"):
    mx, vt, _ = SUPPLY_MAX[mpn]
    return mx * (V_LINE / vt) * SUPPLY_FREQ_FACTOR

def build(extra_y_per_line_f=0.0, system="s38"):
    """Return per-line contributions (mA) at V_LINE, tolerance applied, for SYSTEMS[system]."""
    sysd = SYSTEMS[system]
    items = []
    def cap(name, c_nom, src):
        items.append(dict(name=name, c_nom_nF=c_nom * 1e9, mA=i_ma(c_nom * (1 + TOL)), src=src))
    cap("C3/C4 board Y (2.2 nF, +20 %)", 2.2e-9, "power_stage_120v.ato (cy1 / cy2 CapY1_2n2); parts.ato CapY1_2n2")
    if sysd["module_y_nF"]:
        cap("D-22 module Y (4.7+2.2 nF, +20 %)", sysd["module_y_nF"] * 1e-9, "out-D22/PARTS.md Main/HF Y")
    if extra_y_per_line_f:
        cap("CONTROL extra Y per line", extra_y_per_line_f, "hypothetical")
    cap("coil-to-PE 31 pF (+20 %)", 31e-12, "DECISIONS.md item 20")
    for ps, mpn in sysd["supplies"]:
        items.append(dict(name=f"{ps} {mpn} leakage", c_nom_nF=None, mA=supply_ma(mpn), src=SUPPLY_MAX[mpn][2]))
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

S35_DESIGN_MA = 0.9741421213647918     # the committed DESIGN row before stage 38 (result.json at 0aecdc56f)

def main():
    design = evaluate("DESIGN (datasheet-max supplies)", build())
    control = evaluate("CONTROL (+10 nF Y per line; must FAIL)", build(extra_y_per_line_f=10e-9))
    # Discriminating control: the design passes by 8.8 uA, so +0.2 nF per line (12 uA) must flip it to FAIL.
    control2 = evaluate("CONTROL 2 (design + 0.2 nF Y per line; must FAIL)", build(extra_y_per_line_f=0.2e-9))
    # Regression anchor: the stage-35 system must reproduce the committed pre-stage-38 DESIGN row and FAIL.
    s35 = evaluate("REFERENCE s35 (three IRM supplies, D-22 module Y; must reproduce 0.9741 mA and FAIL)", build(system="s35"))
    # Max total C per line allowed at the 50 % budget, 132 V, 60 Hz (including +20 % on Y):
    c_budget_nF = PASS_FRACTION * LIMIT_MA * 1e-3 / (W * V_LINE) * 1e9
    out = dict(V=V_LINE, f=F_LINE, limit_mA=LIMIT_MA, pass_fraction=PASS_FRACTION,
               budget_mA=PASS_FRACTION * LIMIT_MA, max_total_C_per_line_nF_at_budget=c_budget_nF,
               system=SYSTEMS["s38"]["note"], results=[design, control, control2, s35])
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "result.json"), "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print(f"Limit {LIMIT_MA} mA (UL 1026 grounded portable; IEC 60335-1 ref {LIMIT_IEC_MA} mA); "
          f"budget = {PASS_FRACTION:.0%} = {PASS_FRACTION*LIMIT_MA:.3f} mA; {V_LINE} V {F_LINE} Hz")
    print(f"Max total C-to-PE per line at budget: {c_budget_nF:.2f} nF (incl. tolerance)")
    for r in (design, control, control2, s35):
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
    ok_control = control["verdict"] == "FAIL" and control2["verdict"] == "FAIL" and s35["verdict"] == "FAIL" \
        and abs(s35["governing_touch_mA"] - S35_DESIGN_MA) < 1e-12
    print(f"\nCONTROL check (both controls FAIL, the s35 reference reproduces {S35_DESIGN_MA:.4f} mA and FAILs): "
          f"{'OK' if ok_control else 'BROKEN'}")
    print(f"F5 DESIGN VERDICT: {design['verdict']}")
    return 0 if (design["verdict"] == "PASS" and ok_control) else 1

if __name__ == "__main__":
    sys.exit(main())
