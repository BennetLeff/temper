#!/usr/bin/env python3
"""Stage 51 datasheet-ledger edit (c51-bank-source, DECISIONS 73): the fitted bank becomes KNSCHA MMK104J3DF1KN208G2;
TDK B32643B8104J000 leaves `entries` (it is not on the BOM) and is kept under `alternates` as the documented 28 A
drop-in on the same dual-pitch footprint. Run after the s51 chain, stage51/scripts/bands51.py and bank_voltage51.py.

    python3 -I validation-results/11-candidates/c51-bank-source/stage51/scripts/ledger51.py
        -> native-21/verification/datasheet-ledger/ledger.json (in place)

KNSCHA entry, audited from:
  * spec for approval KNS20200505002 'MMKP82 104J2000V P=27.5', part MMK104J3DF1KN208G2 (LCSC C528962, sha256
    4621763054ad5e92...; c51-bank-source README 'Datasheets'): p.2 structure (PP film, sprayed-metal ends, epoxy, CP wire
    leads, PBT case), p.3 dimensions W 31.5 / H 19.5 / T 11 / P 27.5 (+-0.5), d 0.8 +-0.05 mm, p.4 GB/T 10190 (IEC
    60384-16), 40/105/56, flammability grade B, -40 .. +105 C, test 1.6 UR 5 s, tan d <= 0.1 % at 1 kHz;
  * the MMKP82 family sheet (LCSC C565696, 2026.9.16, sha256 39ea96c070da5f1e...): the 2000 VDC / 700 VAC permissible
    current chart (sine, ambient <= 85 C, internal rise 10 K; digitised in c51-bank-source/results/knscha_curves.json:
    6.2 A at 35 kHz, 6.16 A at 40 kHz for 0.1 uF P27.5), DC derating 1.25 %/C above 85 C, dV/dt 2200 V/us at P27.5 2000 V;
  * stresses: the c49 bank rows (same 0.50 uF J bank), F3 / double fault on this board's OCP band
    (stage51/results/bank-voltage-s51.json), self-heating under the declared airflow and in still air at release from
    bank28-air/results/bank_air_metric.json (this board's jetmix and release pads), body rows keyed into
    b3-ratings/margins.json (film_mmkp82, Top,max 105 C, advisory, board share 0.3).
Ceiling: on the vendor curve the part reaches the 85 % rule at 24.3 A of tank current, and bank_air (strict) crosses 1.00
at 22.9 A (c51-bank-source README 'Decision inputs'). The ledger's violation-severity current rows are therefore the
release trip and the 22 A strict ladder step; 24 A (gap credit) and the 28 A design point are gap-severity rows on the 28 A
route (the TDK alternate fitted, or a better-rated part).
Re-running it on the edited ledger gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[4]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
MARGINS = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
KELVIN = PS / "validation-results/02-protection-timing/kelvin/kelvin_plane.py"
C51 = "validation-results/11-candidates/c51-bank-source"
BV = f"{C51}/stage51/results/bank-voltage-s51.json"
AIR = "validation-results/11-candidates/bank28-air/results/bank_air_metric.json"
CANDS = f"{C51}/data/candidates.json"
DEC = f"{C51}/results/decision_inputs.json"
C34 = "validation-results/11-candidates/c34-bank-margin/README.md"
CARD = f"{C51}/stage51/README.md"
OLD, MPN = "B32643B8104J000", "MMK104J3DF1KN208G2"
BANK = ["C21", "C22", "C23", "C151", "C152"]
SPEC = "KNSCHA KNS20200505002"
FAM = "KNSCHA MMKP82 family sheet 2026.9.16 (LCSC C565696)"


def jl(rel):
    return json.loads((PS / rel).read_text())


def b3_bank():
    m = json.loads(MARGINS.read_text())
    pin = re.search(r'"native21s51": "([0-9a-f]{64})"', KELVIN.read_text())
    sha = set(m["board_sha256"].values())
    assert pin and sha == {pin.group(1)}, ("margins.json is not the s51 board", sha, pin and pin.group(1))
    out = {}
    for c, rows in m["cases"].items():
        hit = [r for r in rows if r["item"].split(":")[0] in BANK]
        assert len(hit) == 5 and all("MMKP82 Top,max" in r["item"] and r["limit_c"] == 105.0 for r in hit), (c, hit)
        out[c] = max(hit, key=lambda r: r["est_c"])
    return out, str(MARGINS.relative_to(PS)), pin.group(1)


def share(n=5, tol=0.05):
    return (1 + tol) / ((1 + tol) + (n - 1) * (1 - tol))


def bank_entry():
    b3, rel, board = b3_bank()
    key = lambda c: [{"file": rel, "b3_row": {"case": c, "item": " ".join(b3[c]["item"].split()[:3])},
                      "est_c": b3[c]["est_c"]}]
    bv = jl(BV)
    assert bv["board_sha256"] == board, (bv["board_sha256"], board)
    kv = bv["parts"][MPN]
    air = jl(AIR)["by_mpn"][MPN]
    assert air["board_sha256_of_pad_runs"] == board, (air["board_sha256_of_pad_runs"], board)
    rel_air = air["release"]
    assert rel_air["board_sha256_of_release_runs"] == board, rel_air["board_sha256_of_release_runs"]
    c = next(x for x in jl(CANDS)["candidates"] if x["id"] == "knscha")
    sh = share(c["n"], c["tol"])
    i_allow = round(c["I35"] / sh, 2)                # tank A at which the worst-share part meets the 35 kHz curve
    sh28 = round((28.0 * sh / c["I35"]) ** 2 * c["dT_v"], 2)
    w, wa = bv["worst_R0_R1"], bv["worst_any_reading"]
    aw = air["worst"]
    rr, rn = rel_air["18.375 A"]["with_radiation"], rel_air["18.375 A"]["no_radiation"]
    t_rel, t22, t28 = (round(b3[c_]["est_c"], 1) for c_ in ("c17.5_h10", "c22_h10", "c28_h10"))
    hot = {c_: b3[c_]["item"].split(":")[0] for c_ in b3}
    ratings = [
        {"parameter": "VR DC", "datasheet_limit": 2000, "unit": "V", "basis": "MMKP82 104J2000V: 2000 V DC",
         "source": f"{SPEC} p.1 (specification 'MMKP82 104J2000V P=27.5'), p.4 rated voltage"},
        {"parameter": "VC at Top,max", "datasheet_limit": kv["VC_at_Top_max_V"], "unit": "V",
         "basis": "UR (dc) x (1 - 1.25 %/C x (Top - 85 C)) above 85 C, at the part's Top,max 105 C (40/105/56): 2000 x 0.75",
         "source": f"{FAM} technical data (1.25 %/C for UR dc above 85 C); {SPEC} p.4 (40/105/56, -40 .. +105 C)"},
        {"parameter": "VRMS", "datasheet_limit": 700, "unit": "Vrms", "basis": "700 V AC (2000 VDC / 700 VAC chart title)",
         "source": f"{FAM} current chart (image; c51-bank-source/scripts/digitize_knscha.py)"},
        {"parameter": "I tank allowed @35kHz", "datasheet_limit": i_allow, "unit": "A",
         "basis": f"worst-share J part (share {sh:.4f}) at the 35 kHz floor on KNSCHA's curve: {c['I35']} A for a 10 K "
                  "internal rise at ambient <= 85 C (digitised, controls pass)", "source": CANDS},
        {"parameter": "Self-heating allowance", "datasheet_limit": 10, "unit": "K",
         "basis": "the curve's basis: internal temperature rise 10 C, sine, ambient <= 85 C", "source": f"{FAM} chart remark"},
        {"parameter": "Self-heating allowance at T_A (declared airflow)", "datasheet_limit": aw["dT_allowed_K"], "unit": "K",
         "basis": f"10 K at the worst column point's T_A {aw['T_A_C']} C (<= 85 C: no derating; above, ASSUMED linear to "
                  "0 at 105 C, the sheet gives no rule)", "source": f"{FAM} chart remark; bank28-air/scripts/bank_air_metric.py"},
        {"parameter": "Top,max", "datasheet_limit": 105, "unit": "C", "basis": "upper category temperature (40/105/56)",
         "source": f"{SPEC} p.4"},
        {"parameter": "dV/dt", "datasheet_limit": 2200, "unit": "V/us", "basis": "P = 27.5 mm, UR 2000 V",
         "source": f"{FAM} dV/dt table"}]
    stresses = [
        {"parameter": "V peak 28 A", "worst_case_value": 566, "unit": "V",
         "condition": "estimated peak at 28 A (268 Vrms bound x round-6 peak/rms 2.113); same 0.50 uF J bank",
         "evidence": f"{C34}:37"},
        {"parameter": "V peak no-pan fault", "worst_case_value": 775, "unit": "V",
         "condition": "no-pan fault peak, same 0.50 uF bank; checked against VC at Top,max (105 C)", "evidence": f"{C34}:186"},
        {"parameter": "V rms 28 A", "worst_case_value": 268, "unit": "Vrms",
         "condition": "bound: I <= 28 A, f >= 35 kHz, C >= 0.475 uF", "evidence": f"{C34}:33"},
        {"parameter": "I tank release trip", "worst_case_value": 18.4, "unit": "A",
         "condition": "17.5 A release ceiling at its 18.375 A firmware RMS trip (b3_ratings_gate BASIS c17.5_h10)",
         "evidence": "validation-results/04-board-current-thermal/round5-native21/b3-ratings/b3_ratings_gate.py:29-30"},
        {"parameter": "I tank ladder 22 A (strict)", "worst_case_value": 22, "unit": "A",
         "condition": "the highest commissioned ladder step this bank holds strictly: bank_air strict 0.959 and vendor ratio "
                      "0.768 at 22 A (c51-bank-source decision_inputs.py; the strict gate crosses 1.00 at 22.9 A)",
         "evidence": DEC},
        {"parameter": "I tank ladder 24 A (gap credit)", "worst_case_value": 24, "unit": "A",
         "condition": "the step the bank holds only with the gap-flow credit (bank_air +gap 0.745; vendor ratio 0.838, the "
                      "85 % rule binds at 24.3 A)", "evidence": DEC},
        {"parameter": "I tank design", "worst_case_value": 28, "unit": "A",
         "condition": "28 A Kconfig ceiling; the hardware is sized for 28 A (DECISIONS 68). With this bank 28 A needs the TDK "
                      "alternate fitted or a better-rated part (DECISIONS 73)", "evidence": "DECISIONS.md:518; DECISIONS.md:566"},
        {"parameter": "Self-heating 28 A", "worst_case_value": sh28, "unit": "K",
         "condition": "the fitted bank at 28 A / 35 kHz in KNSCHA's own terms (isolated part on the vendor curve: "
                      "(I_part / 6.2 A)^2 x 10 K)", "evidence": CANDS},
        {"parameter": "Self-heating 28 A, declared airflow", "worst_case_value": aw["dT_col_K"], "unit": "K",
         "condition": f"bank_air_metric.py on this board's jetmix pads (board {board[:8]}), strict (no gap-flow credit): worst "
                      f"of the declared design flow (base h 20 + jets) at 61 / 55 C air, interior / end positions, both "
                      f"G_board bounds: {aw['point']}, {aw['position']}, G_board {aw['g_board_bound']}, {aw['v_bank_m_s']} m/s, "
                      f"T_A {aw['T_A_C']} C (bank_air_ratio_28A_35k {air['bank_air_ratio_28A_35k']})", "evidence": AIR},
        {"parameter": "Case temperature 28 A, declared airflow", "worst_case_value": air["T_op_max_C"], "unit": "C",
         "condition": "T_A + dT_col, hottest column point of the same run", "evidence": AIR},
        {"parameter": "Self-heating release, still air", "worst_case_value": rr["dT_K"], "unit": "K",
         "condition": f"bank_air_metric.py release rows on this board's own B3 release solve (c17.5_h10, bay 61 C, air "
                      f"bay + 15 K) at the 18.375 A trip, natural convection with radiation: {rr['position']}, G_board "
                      f"{rr['g_board_bound']}, T_A {rr['T_A_C']} C, allowed {rr['dT_allowed_K']} K (eff {rr['eff_ratio']}); "
                      f"without radiation {rn['dT_K']} K (eff {rn['eff_ratio']})", "evidence": AIR},
        {"parameter": "V third fault", "worst_case_value": w["F3_V"], "unit": "V",
         "condition": f"F3 (CT-failed third fault, quasi-steady just under the shunt band top, no f floor; outside IEC "
                      f"60335-1 19.11's one-fault analysis): 1683 V x top / 118.74 A at the s51 OCP top {w['ocp_top_A']} A "
                      f"({w['network']}, TLV3201 {w['reading']}, HOT5 {w['hot5']}); spec-literal R4 reading {wa['F3_V']} V",
         "evidence": [BV, "DECISIONS.md:853", "validation-results/02-protection-timing/bank-ov-double-fault/results.json"]},
        {"parameter": "V double fault Z0max x OCP top", "worst_case_value": wa["Z0max_x_top_V"], "unit": "V",
         "condition": f"CT-failed double fault bank rule (stage15-28A fault_check.py form): Z0,max {bv['z0_max_ohm']} ohm x "
                      f"the highest s51 OCP top of any TLV3201 reading ({wa['ocp_top_A']} A, {wa['network']} {wa['reading']} "
                      f"{wa['hot5']})", "evidence": BV},
        {"parameter": "dV/dt at turn-off", "worst_case_value": bv["dVdt"]["V_per_us"], "unit": "V/us",
         "condition": "bank-ov-double-fault clamp sizing at the largest turn-off current (155.4 A)",
         "evidence": "validation-results/02-protection-timing/bank-ov-double-fault/results.json"},
        {"parameter": "Body temperature c17.5 (release)", "worst_case_value": t_rel, "unit": "C",
         "condition": f"B3 ratings model s51, release case c17.5_h10 (18.4 A trip, still air, bay 61 C), hottest bank part "
                      f"{hot['c17.5_h10']} (advisory row, board fraction 0.3 assumed; film_mmkp82 spec, ESR 39.8 mOhm worst "
                      "at 40 kHz ASSUMED)", "evidence": key("c17.5_h10")},
        {"parameter": "Body temperature c22", "worst_case_value": t22, "unit": "C",
         "condition": f"context: c22_h10, {hot['c22_h10']}, bay 55 C", "evidence": key("c22_h10")},
        {"parameter": "Body temperature c28", "worst_case_value": t28, "unit": "C",
         "condition": f"context: c28_h10 (28 A, 29.4 A trip), still air, bay 55 C, {hot['c28_h10']}", "evidence": key("c28_h10")}]
    S = {s["parameter"]: s["worst_case_value"] for s in stresses}
    R = {r["parameter"]: r["datasheet_limit"] for r in ratings}

    def chk(cid, rating, stress, mx, sev, rule):
        return {"id": cid, "rating": rating, "stress": stress, "max_ratio": mx, "severity": sev, "rule": rule,
                "ratio": round(S[stress] / R[rating], 4)}
    vc = R["VC at Top,max"]
    checks = [
        chk("V 28 A", "VR DC", "V peak 28 A", 0.8, "violation", "566 <= 1600 V (0.8 x 2000 V)"),
        chk("V no-pan fault hot", "VC at Top,max", "V peak no-pan fault", 0.8, "violation",
            f"775 <= {0.8 * vc:g} V (0.8 x VC {vc:g} V at 105 C)"),
        chk("Vrms", "VRMS", "V rms 28 A", 0.8, "violation", "268 <= 560 Vrms (0.8 x 700 V AC)"),
        chk("I release", "I tank allowed @35kHz", "I tank release trip", 0.85, "violation",
            f"18.4 A <= 0.85 x {i_allow} A (DECISIONS 37's 85 % rule at the commissioned ceiling)"),
        chk("I ladder 22 A (strict)", "I tank allowed @35kHz", "I tank ladder 22 A (strict)", 0.85, "violation",
            f"22 A <= 0.85 x {i_allow} A on the vendor curve: the bank's strict ladder cap (DECISIONS 73)"),
        chk("I ladder 24 A (gap credit)", "I tank allowed @35kHz", "I tank ladder 24 A (gap credit)", 0.85, "gap",
            f"24 A <= 0.85 x {i_allow} A; the step is open only if the bench shows the gap-flow credit (S24 / S25)"),
        chk("I design 28 A", "I tank allowed @35kHz", "I tank design", 0.85, "gap",
            f"28 A <= 0.85 x {i_allow} A fails on this part (0.978): the 28 A route is the TDK B32643B8104J000 alternate "
            "(0.831) on the same footprint, or a better-rated part (OPEN-ITEMS 28 A bank route)"),
        chk("self-heating 28 A", "Self-heating allowance", "Self-heating 28 A", 1.0, "gap",
            f"{sh28} K <= 10 K in KNSCHA's terms (isolated part, vendor curve; the 28 A route row)"),
        chk("self-heating 28 A, declared airflow", "Self-heating allowance at T_A (declared airflow)",
            "Self-heating 28 A, declared airflow", 1.0, "gap",
            f"airflow route (S24 / S25): {aw['dT_col_K']} K <= {aw['dT_allowed_K']} K in the column under the declared flow, "
            f"strict (bank_air_ratio_28A_35k {air['bank_air_ratio_28A_35k']}); the gap-flow credit (3.5 mm gaps) gives "
            "0.869 and is a bench item"),
        chk("case 28 A, declared airflow", "Top,max", "Case temperature 28 A, declared airflow", 1.0, "gap",
            f"airflow route: {air['T_op_max_C']} C <= 105 C"),
        chk("self-heating release, still air", "Self-heating allowance", "Self-heating release, still air", 1.0, "gap",
            f"S25 pre-lot gate: {rr['dT_K']} K <= 10 K at the 18.375 A trip in still air with radiation (eff {rr['eff_ratio']}); "
            f"without radiation {rn['dT_K']} K (eff {rn['eff_ratio']}); the bench closes it"),
        chk("V third fault", "VR DC", "V third fault", 0.85, "violation",
            f"F3 {w['F3_V']} V <= 1700 V (0.85 x 2000 V; audit.rs S49_BANK_VR)"),
        chk("V double fault", "VR DC", "V double fault Z0max x OCP top", 1.0, "violation", f"{wa['Z0max_x_top_V']} V <= 2000 V"),
        chk("dV/dt", "dV/dt", "dV/dt at turn-off", 1.0, "violation", f"{bv['dVdt']['V_per_us']} <= 2200 V/us"),
        chk("body c17.5 (release)", "Top,max", "Body temperature c17.5 (release)", 1.0, "violation",
            f"{t_rel} <= 105 C at the release case"),
        chk("body c22", "Top,max", "Body temperature c22", 1.0, "gap", f"context: {t22} <= 105 C"),
        chk("body c28", "Top,max", "Body temperature c28", 1.0, "gap",
            f"airflow route (c22/c28): {t28} C vs 105 C in still air at bay 55 C")]
    return {
        "mpn": MPN, "designators": BANK, "class": "POWER",
        "function": "Resonant tank bank C21-C23/C151/C152, 5 x 100 nF +/-5 %, 2000 VDC MMKP82, 27.5 mm, on the dual-pitch "
                    "footprint (stage 51, DECISIONS 73; TDK B32643B8104J000 is the not-fitted 28 A alternate)",
        "status": "PARTIAL",
        "datasheet": {
            "url": "https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2005081108_KNSCHA-MMK104J3DF1KN208G2_C528962.pdf",
            "revision": f"{SPEC} specification for approval, MMKP82 104J2000V P=27.5 (2020-05-05)",
            "fetched": "2026-10-16", "repo_copy": None, "sha256_prefix16": "4621763054ad5e92",
            "note": "c51-bank-source lane download (dl/ not committed). p.2 structure: PP film core, sprayed tin-zinc ends, "
                    "epoxy fill, CP wire leads, PBT case. p.3: W 31.5 / H 19.5 / T 11 / P 27.5 (+-0.5), d 0.8 +-0.05, L 20 +-2 "
                    "mm; marking 104J2000V, no polarity. p.4: GB/T 10190 (IEC 60384-16), climatic 40/105/56, flammability "
                    "grade B (passive flammability), rated 630-2000 V, -40 .. +105 C, 1.6 UR 5 s, tan d <= 0.1 % at 1 kHz "
                    "20 C, IR >= 30000 MOhm. Current / VRMS / derating / dV/dt from the MMKP82 family sheet (LCSC C565696, "
                    "2026.9.16, sha256 39ea96c070da5f1e). Approval basis: a HOT-side tank part, not a safety capacitor, so "
                    "no UL / ENEC file is required; KNSCHA lists no UL file and no AEC qualification. The case is reported "
                    "UL 94 V-0 by the sourcing study (README candidates table); that grade is not in the text layer of "
                    "KNS20200505002, whose own row is flammability grade B. LCSC C528962, JLC Extended THT, 4,952 in stock "
                    "on 2026-10-16."},
        "ratings": ratings, "stresses": stresses,
        "derating_rule": "Peak voltage <= 80 % of VR (of VC at Top,max for the no-pan fault); AC voltage <= 80 % of VRMS; "
                         "tank RMS current <= 85 % of the worst-share KNSCHA curve at the release trip and at the 22 A strict "
                         "ladder step; F3 <= 85 % of VR and the CT-failed Z0,max x OCP top <= VR; dV/dt <= the family "
                         "table; body <= Top,max at the B3 release case. 24 A (gap credit), 28 A (vendor curve and "
                         "column self-heating) and the still-air release self-heating are gaps (DECISIONS 73; S24 / S25).",
        "checks": checks,
        "layout_guidance": [
            {"item": "27.5 mm pitch (the dual-pitch footprint's 27.5 mm pad-2 hole; the 22.5 mm hole stays empty), 0.8 mm "
                     "leads in 1.2 mm drills; bodies at 15.0 mm row pitch (about 3.5 mm air gaps) in the bank column "
                     "x 161-193, y 46-119 kept open for the >= 3 m/s airflow (DECISIONS 68)",
             "enforced_by": "UNCHECKED (bench S25; enclosure airflow S24)"},
            {"item": "pad pattern / mains-side separation", "enforced_by": "native-21/verification/d5_audit.py"},
            {"item": "non-polar THT CPL rotation (0 / 180 equivalent) on the 27.5 mm hole pair",
             "enforced_by": "validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/audit.py"}],
        "gaps": [
            "bench: current rating basis. The curve is digitised from an embedded JPEG (6.2 A at 35 kHz, 6.16 A at 40 kHz, "
            "10 K internal rise at ambient <= 85 C); confirm the rise at 6.2 A / 35 kHz sine on a single part in still air "
            "(case, or core by a thermocouple through the lead).",
            "bench: ESR / tan d at 35 and 40 kHz, at 25 C and about 80 C. The rating implies ESR <= 10.7 mOhm at 35 kHz; "
            "bank_air scales as sqrt(ESR / 10.7 mOhm) (the strict 22 A step tolerates 11.6 mOhm, the +gap 28 A row 14.1). "
            "B3's worst heat row ASSUMES 39.8 mOhm at 40 kHz (the 1 kHz tan d limit held flat).",
            "bench / vendor: behaviour above 85 C ambient. The sheet gives no current derating above 85 C; the model "
            "ASSUMES it linear to 0 at Top,max 105 C (and a 1.25 %/C DC derating); confirm 40/105/56 and the rule with "
            "KNSCHA or by a hot soak with a bench current.",
            f"bench (S24 / S25): gap-flow credit. Strict bank_air at 28 A is {air['bank_air_ratio_28A_35k']} (crosses 1.00 at "
            "22.9 A); with the 3.5 mm gap-channel credit 0.869. The worst interior part (C22 / C23 / C151) at 28 A under the "
            "S24 flow must show <= 10 K internal rise over its local air (model: 7.6 K with the credit, 14.9 K strict); "
            "measure the gap velocity too (model 2.5 m/s). This decides 22 A (strict) vs 24 A (+gap) for the ladder.",
            "bench: body dimensions. The datasheet gives 31.5 x 19.5 x 11 +-0.5 mm; the model uses 32 x 20 x 11.5 and the "
            "gap width (3.5-4 mm) drives the credit: measure 10 bodies.",
            "owner: ceiling. The bank caps the commissioned ladder at 22 A strict, 24 A if the bench shows the gap credit "
            "(vendor ratio 0.838, the 85 % rule binds at 24.3 A); 28 A needs the TDK B32643B8104J000 alternate fitted "
            "(28-week, MOQ 2080) or a better-rated part (DECISIONS 73; OPEN-ITEMS 28 A bank route).",
            "owner: sourcing. Single source (JLC C528962, 4,952 on 2026-10-16 against 2,500 for 500 boards; Unikey broker "
            "400); no second stocked 2 kV part qualifies (c51-bank-source).",
            "desk: approval basis. HOT-side tank part, no UL / ENEC file needed or listed, no AEC; flammability grade B "
            "(p.4); the UL 94 V-0 case grade the sourcing study reports is not in the spec's text layer (confirm with "
            "KNSCHA if a V-0 claim is ever needed)."],
        "finding": None,
        "notes": f"S51 (2026-10-16, {CARD}): replaces B32643B8104J000 (JLC 0, 28 weeks, MOQ 2080; owner rejected) on a "
                 "dual-pitch footprint that keeps the TDK part as the 28 A drop-in (ledger `alternates`). Voltage rows "
                 "pass with the same F3 as c34 (both 2000 V); the current rows set a 22 A strict / 24 A +gap ladder cap."}


def main():
    led = json.loads(LEDGER.read_text())
    E = led["entries"]
    bank = bank_entry()
    out = {}
    for k, v in E.items():
        if k in (OLD, MPN):
            if MPN not in out:
                out[MPN] = bank
        else:
            out[k] = v
    alt = dict(led.get("alternates", {}))
    if OLD in E:
        a = dict(E[OLD])
        a["status_as_alternate"] = ("NOT FITTED. Stage 51 (DECISIONS 73): documented drop-in alternate for the 28 A route on "
                                    "the dual-pitch footprint's 22.5 mm hole; this is its stage-49 / 50 audit on board "
                                    "4876c42e (s50), kept for the 28 A decision; not on the pre-order list. The gate does "
                                    "not read `alternates`.")
        alt[OLD] = a
    if alt:
        led["alternates"] = alt
    led["entries"] = out
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print("ledger: entries", len(out), "alternates", sorted(led.get("alternates", {})))
    for c in out[MPN]["checks"]:
        print(f"  {MPN:20} {c['id']:38} {c['ratio']:.4f} <= {c['max_ratio']} {c['severity']:9} {c['rule'][:90]}")


if __name__ == "__main__":
    main()
