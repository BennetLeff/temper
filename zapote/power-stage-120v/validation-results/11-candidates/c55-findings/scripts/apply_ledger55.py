#!/usr/bin/env python3
"""S31 ledger edit: C1 / C2 (R463N410050N1K) ripple rating on the attributed 1 uF trace and a bounded Th.

    python3 -I validation-results/11-candidates/c55-findings/scripts/r46_irms_digitize.py
    python3 -I validation-results/11-candidates/c55-findings/scripts/c2_ripple.py
    python3 -I validation-results/11-candidates/c55-findings/scripts/apply_ledger55.py   -> ledger.json (in place)

Replaces the c54 desk's 1.5 A reading (the 0.68 uF trace) by the 1 uF trace (results/r46-irms.md), rates the release
and 28 A cases at the L1-body Th bound (margins.json, keyed) and states the C2 pad / bay basis. Same number of gaps.
Re-running it on the edited ledger gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LANE = HERE.parent
REL = str(LANE.relative_to(PS))
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
MARGINS = "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
MPN = "R463N410050N1K"


def md_line(name, prefix):
    for i, t in enumerate((LANE / "results" / name).read_text().splitlines(), 1):
        if t.startswith(prefix):
            return f"{REL}/results/{name}:{i}"
    raise SystemExit(f"{name}: no line starting {prefix!r}")


def main():
    dig = json.loads((LANE / "results/r46-irms.json").read_text())
    cr = json.loads((LANE / "results/c2-ripple.json").read_text())
    i70 = cr["i70_A"]
    rel, c28 = cr["cases"]["release"], cr["cases"]["c28"]
    led = json.loads(LEDGER.read_text())
    e = led["entries"][MPN]
    v = dig["implied_test_voltage_V"]
    p8 = "KEMET F3095_R46_X2_310_110C (2026-05-13) p.8, Lead Spacing 22.5 mm graph; digitised in " + md_line("r46-irms.md", "| yellow_top")
    p6 = "KEMET F3095_R46_X2_310_110C p.6 (Maximum Irms vs Th; Maximum Overtemperature dTlim vs Th; Th definition); p.8"
    th_rel, th_28 = rel["l1_body_C"], c28["l1_body_C"]
    ratings = [r for r in e["ratings"] if not r["parameter"].startswith(("Irms max 35-100 kHz", "Th max for"))]
    ratings += [
        {"parameter": "Irms max 35-100 kHz, Th <= 70 C", "datasheet_limit": i70, "unit": "A",
         "basis": f"Maximum current vs frequency, sinusoidal, Th <= 70 C, 22.5 mm lead spacing: the 1 uF trace (top, dotted), "
                  f"minimum over 35-90 kHz. The leader lines are ambiguous; the traces are not: below the knee each is the "
                  f"voltage limit 2 pi f C V, and only the order 0.15 / 0.33 / 0.47 / 0.68 / 1 uF from the bottom gives one "
                  f"test voltage for all five ({min(v):.0f}-{max(v):.0f} V, spread {dig['voltage_spread']:.1%}; the next "
                  f"best order {dig['runner_up_spread']:.0%}). The c54 desk's 1.5 A was the 0.68 uF trace. One trace "
                  f"covers both 1 uF bodies (N1 11 x 20 mm, fitted; N2 10 x 18.5 mm)",
         "source": p8},
        {"parameter": f"Irms max 35-100 kHz, Th {th_rel} C", "datasheet_limit": rel["limit_at_l1_body_A"], "unit": "A",
         "basis": f"{i70} A x sqrt(dTlim(Th) / 20 K), dTlim 20 K to 70 C falling linearly to 0 at 110 C (p.6, both p.6 "
                  f"curves); Th {th_rel} C is the B3 L1 body at the release case (stress 'C2 Th bound, release')",
         "source": p6},
        {"parameter": f"Irms max 35-100 kHz, Th {th_28} C", "datasheet_limit": c28["limit_at_l1_body_A"], "unit": "A",
         "basis": f"as above at Th {th_28} C, the B3 L1 body at c28_h10", "source": p6},
        {"parameter": "Th max for the release ripple", "datasheet_limit": rel["th_max_C"], "unit": "C",
         "basis": f"the Th at which the p.6 derating of the {i70} A rating meets the release stress {rel['stress_A']} A: "
                  f"110 - 40 (I / {i70})^2",
         "source": p6},
    ]
    e["ratings"] = ratings
    st = [s for s in e["stresses"] if s["parameter"] != "C2 Th bound, release (L1 body)"]
    st.append({"parameter": "C2 Th bound, release (L1 body)", "worst_case_value": th_rel, "unit": "C",
               "condition": "KEMET p.6 defines Th as the hotter of the air around the capacitor and its hottest contact "
                            "point. Bound: the B3 L1 body beside C1 / C2 (the air heated by L1 cannot be hotter than L1). "
                            f"C2's own pad copper is {rel['c2_pad_C']} C and the bay {rel['bay_C']} C at the release case",
               "evidence": [{"file": MARGINS, "b3_row": {"case": "c17.5_h10", "item": "L1: B82726 climatic"}, "est_c": th_rel},
                            md_line("c2-ripple.md", "| release")]})
    e["stresses"] = st
    old = {"C2 ripple, release, Th <= 70 C", "C2 ripple, c28, Th <= 70 C", "C2 Th, release"}
    keep = [c for c in e["checks"] if c["id"] not in old and not c["id"].startswith(("C2 ripple, release, Th ", "C2 ripple, c28, Th ",
                                                                                         "C1 ripple with module, Th "))]

    def chk(cid, rating, stress, sev, rule, lim, val):
        return {"id": cid, "rating": rating, "stress": stress, "max_ratio": 1.0, "severity": sev, "rule": rule,
                "ratio": round(val / lim, 4)}
    c1 = next(s for s in e["stresses"] if s["parameter"].startswith("C1 ripple current"))["worst_case_value"]
    keep += [
        chk(f"C2 ripple, release, Th {th_rel} C", f"Irms max 35-100 kHz, Th {th_rel} C",
            "C2 ripple current, release (line-cycle RMS)", "violation",
            f"{rel['stress_A']:.3f} A <= {rel['limit_at_l1_body_A']} A at the L1-body Th bound (c55)",
            rel["limit_at_l1_body_A"], rel["stress_A"]),
        chk("C2 Th, release", "Th max for the release ripple", "C2 Th bound, release (L1 body)", "violation",
            f"{th_rel} C <= {rel['th_max_C']} C (keyed to margins.json: a re-solve that heats L1 re-opens this check)",
            rel["th_max_C"], th_rel),
        chk("C2 ripple, c28, Th <= 70 C", "Irms max 35-100 kHz, Th <= 70 C", "C2 ripple current, c28 (line-cycle RMS)", "gap",
            f"{c28['stress_A']:.3f} A <= {i70} A holds while Th <= 70 C (C2 pad {c28['c2_pad_C']} C / bay {c28['bay_C']} C; "
            f"the air beside L1 is not evidenced)", i70, c28["stress_A"]),
        chk(f"C2 ripple, c28, Th {th_28} C", f"Irms max 35-100 kHz, Th {th_28} C", "C2 ripple current, c28 (line-cycle RMS)",
            "gap", f"airflow / ceiling route: {c28['stress_A']:.3f} A > {c28['limit_at_l1_body_A']} A at the L1-body bound; "
                   f"needs Th <= {c28['th_max_C']} C", c28["limit_at_l1_body_A"], c28["stress_A"]),
        chk(f"C1 ripple with module, Th {th_rel} C", f"Irms max 35-100 kHz, Th {th_rel} C",
            "C1 ripple current with the inlet module (line-cycle RMS)", "violation",
            f"{c1:.3f} A <= {rel['limit_at_l1_body_A']} A", rel["limit_at_l1_body_A"], c1),
    ]
    e["checks"] = keep
    src = f"{REL}/scripts/c2_ripple.py"

    def swap_gap(prefix, text):
        hits = [i for i, g in enumerate(e["gaps"]) if g.startswith(prefix)]
        assert len(hits) == 1, (prefix, len(hits))
        e["gaps"][hits[0]] = text
    swap_gap("bench: C1 / C2 body temperature",
             f"bench: C1 / C2 body temperature next to L1 / BR1 is not evidenced. B3 gives C2's pad copper ({rel['c2_pad_C']} C "
             f"release, {c28['c2_pad_C']} C c28; {md_line('c2-ripple.md', '| release')}) and the L1 body that bounds the "
             f"air beside it ({th_rel} / {th_28} C, {MARGINS} rows 'L1: B82726 climatic', keyed); limit 110 C. Closing test: "
             f"thermocouple on C1 / C2 body and leads at the release ceiling.")
    swap_gap("bench: C2 ripple current",
             f"bench: C2 ripple current. {src} on c54-ledger-desk/scripts/cx_current.py (a linear crest-condition estimate "
             f"that reads high: bridge always conducting, no trace inductance between C2 and the DC link): "
             f"{rel['stress_A']:.2f} A line-cycle RMS at the release trip, within {i70} A x sqrt((110 - Th) / 40) (KEMET "
             f"p.6 / p.8, 1 uF trace) up to Th {rel['th_max_C']} C, above the {th_rel} C L1-body bound. Closing test: "
             f"current probe on a C2 lead plus a thermocouple at the release ceiling and at every commissioned ladder step; "
             f"pass if the measured RMS <= {i70} A x sqrt((110 - Th) / 40) at the measured Th.")
    swap_gap("owner (28 A route): C2's modelled ripple",
             f"owner (28 A route): C2's modelled ripple at 28 A ({c28['stress_A']:.2f} A line-cycle RMS) needs Th <= "
             f"{c28['th_max_C']} C; the L1-body bound at c28 is {th_28} C ({c28['ratio_at_l1_body']:.2f} of the derated "
             f"rating there), C2's own pad / bay basis {c28['ratio_at_local']:.2f}. Before a ladder step above the release "
             f"ceiling is commissioned: measure C2's current and Th (bench gap above), or fit a 27.5 mm part (p.8) or add "
             f"series impedance between C2 and BR1 (layout change).")
    e["finding"] = (f"c55 (2026-10-20), resolves the c54 finding at the release case: the c54 desk rated C2 on the 0.68 uF "
                    f"trace (1.5 A); the 1 uF trace reads {i70} A at 35-90 kHz ({md_line('r46-irms.md', '| yellow_top')}), "
                    f"so the modelled {rel['stress_A']:.2f} A release ripple holds up to Th {rel['th_max_C']} C, above the "
                    f"{th_rel} C L1-body bound ({rel['ratio_at_l1_body']:.2f} of the derated rating; "
                    f"{md_line('c2-ripple.md', 'release:')}). The 28 A case needs Th <= {c28['th_max_C']} C and stays with "
                    f"the airflow route. The stress is a model estimate (bench gap).")
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print(f"{MPN}: {len(e['ratings'])} ratings, {len(e['stresses'])} stresses, {len(e['checks'])} checks, {len(e['gaps'])} gaps")


if __name__ == "__main__":
    main()
