#!/usr/bin/env python3
"""Stage 52 datasheet-ledger edit (s52-proto-bom, DECISIONS-DRAFT 74): the prototype BOM.

    python3 -I validation-results/11-candidates/s52-proto-bom/scripts/ledger52.py
        -> native-21/verification/datasheet-ledger/ledger.json (in place)

Run after the s52 chain and s52-proto-bom/scripts/bands52.py, bank_voltage52.py and steps52.py.

Three entries change, and each displaced part moves to `alternates` with a status note:
  * C21-C23 / C151 / C152: TDK B32643H8104J000 replaces KNSCHA MMK104J3DF1KN208G2 (now the in-stock fallback). Audited
    from the owner-supplied TDK B3264*H data sheet, June 2026, 31 pp. (sha256 69b56e62c5603222..., c51-bank-source
    results/b32643h.json `pdf_sha256`; not committed). PDF page = footer page. p.2: Top,max 125 C (case), climatic
    55/110/56, PP dielectric on metallised PET, UL 94 V-0 case, AEC-Q200. p.3: B32643H lead spacing 22.5 +-0.4 mm,
    d1 0.8 +-0.05. p.14 (2000 V DC / 700 V AC, 22.5 mm table): B32643H8104+***, 100 nF, 14.5 x 29.5 x 26.5 mm,
    IRMS,max 11.03 A at 60 C (self-heating <= 30 C) / 9.17 A at 85 C (<= 20 C) at 100 kHz, ESRtyp 10.9 mOhm at 100 kHz,
    untaped MOQ 2080. p.15: TR 105 C, Top,max 125 C (TA + self-heating), Tmax 110 C, tan d <= 0.3e-3 at 1 kHz and
    1.0e-3 at 100 kHz, VR,DC 2000 V and VR,AC 700 V at 105 C, 1.25 %/C Vop derating for 105 < T <= 125 C, 1.6 VR 2 s
    terminal-terminal, 2000 V AC 60 s terminal-case. p.16: dV/dt 3800 V/us, k0 15e6 V^2/us (22.5 mm, 2000 V).
    p.19: permissible IRMS vs f, 2000 V / 22.5 mm, TA 85 C, dT <= 20 C (6.155 A at 35 kHz, 6.481 A at 40 kHz for
    100 nF, digitised in c51-bank-source/scripts/b32643h.py). p.21: permissible VRMS vs f. p.22: F_T(TA), applied as
    IRMS(TA) = IRMS(85 C) x F_T(TA) and Top <= 125 C (F_T 1.22 at 60 C). The c51 study cites the ordering table as
    p.13; on the sheet's own footer it is p.14.
    Stresses: the c34 bank rows (same 0.50 uF J bank), F3 / double fault on this board's OCP band
    (s52-proto-bom/results/bank-voltage-s52.json), self-heating under the declared airflow and in still air at release
    from bank28-air/results/bank_air_metric.json (this board's jetmix and release pads), the ladder steps from
    s52-proto-bom/results/steps-s52.json, and body rows keyed into b3-ratings/margins.json (film_mmkp_h, Top,max 125 C).
    Ceiling: the vendor ratio reaches the 85 % rule at 24.2 A and the strict gate is 1.006 at 28 A, so the
    violation-severity current rows are the release trip and the 24 A ladder step (vendor 0.844, strict 0.862); 26 A
    and 28 A are gap rows on the 28 A route (B32643B8104J000 on the same hole, or the 11-body re-floorplan, S28).
  * L1: TDK B82726S2243A020 (24 A, 0.75 mH, Lstray 8 uH, 3.2 mOhm) replaces B82726S2203A020 for the prototype lot; the
    2203 stays the production part (owner pre-order) and moves to `alternates`. Same TDK B82726S22*3A020 sheet (May 2026,
    sha256 e8002bfe4af13edf) and the same p.5 derating curve (datasheet_gap_calcs.py DERATE).
  * C3 / C4: Murata DE1E3RA222MJ4BH01F (Type RA, H01F: Y1 AC400 V / X1 AC440 V, J4 crimped leads, same body and
    certificates) replaces DE1E3RA222MA4BP01F. LCSC copy of Murata's Type RA reference specification EGD08G, as of
    Jun. 2023, 18 pp. (sha256 c959488a2523ac21). PDF pages, the printed n/17 footer is one less: p.6 approvals and
    rated voltage, p.9 the J4 part list (2200 pF +-20 %, D 9.0, T 4.0, F 10.0, d 0.6), p.11 dielectric strength,
    p.14 life test preceded by 8 kV impulses.
Re-running it on the edited ledger gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import copy
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
MARGINS = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
KELVIN = PS / "validation-results/02-protection-timing/kelvin/kelvin_plane.py"
S52 = "validation-results/11-candidates/s52-proto-bom"
BV = f"{S52}/results/bank-voltage-s52.json"
STEPS = f"{S52}/results/steps-s52.json"
S1 = f"{S52}/results/s1-s52.json"
AIR = "validation-results/11-candidates/bank28-air/results/bank_air_metric.json"
H = "validation-results/11-candidates/c51-bank-source/results/b32643h.json"
L1R = "validation-results/11-candidates/b15-proto-alternates/results/l1_rating.json"
EMI = "validation-results/11-candidates/b15-proto-alternates/results/emi-B82726S2243A020_moduleDM100u/results.json"
EMI_FIT = "validation-results/11-candidates/b15-proto-alternates/results/emi-B82726S2243A020/results.json"
MODREQ = "validation-results/11-candidates/c23-supply-topology/MODULE-REQUEST.md"
C34 = "validation-results/11-candidates/c34-bank-margin/README.md"
CARD = f"{S52}/README.md"
BANK = ["C21", "C22", "C23", "C151", "C152"]
MPN, KN, TB = "B32643H8104J000", "MMK104J3DF1KN208G2", "B32643B8104J000"
L1N, L1O = "B82726S2243A020", "B82726S2203A020"
YN, YO = "DE1E3RA222MJ4BH01F", "DE1E3RA222MA4BP01F"
TDK = "TDK B3264*H June 2026"
BOARD_KEY = "native21s52"
DERATE = [(60, 1.00), (65, 0.964), (67, 0.945), (70, 0.916), (75, 0.865), (78, 0.834), (80, 0.809),
          (85, 0.754), (90, 0.690), (100, 0.543), (110, 0.365), (120, 0.160), (125.6, 0.0)]   # datasheet_gap_calcs.py:32


def jl(rel):
    return json.loads((PS / rel).read_text())


def board_pin():
    pin = re.search(rf'"{BOARD_KEY}": "([0-9a-f]{{64}})"', KELVIN.read_text())
    assert pin, "kelvin_plane.py has no native21s52 board pin"
    return pin.group(1)


def b3_rows(refs, tag, limit, n):
    m = json.loads(MARGINS.read_text())
    board = board_pin()
    sha = set(m["board_sha256"].values())
    assert sha == {board}, ("margins.json is not the s52 board", sha, board)
    out = {}
    for c, rows in m["cases"].items():
        hit = [r for r in rows if r["item"].split(":")[0] in refs]
        assert len(hit) == n and all(tag in r["item"] and r["limit_c"] == limit for r in hit), (c, hit)
        out[c] = max(hit, key=lambda r: r["est_c"])
    rel = str(MARGINS.relative_to(PS))
    key = lambda c: [{"file": rel, "b3_row": {"case": c, "item": " ".join(out[c]["item"].split()[:3])},
                      "est_c": out[c]["est_c"]}]
    return out, key, board


def share(n=5, tol=0.05):
    return (1 + tol) / ((1 + tol) + (n - 1) * (1 - tol))


def mk_checks(ratings, stresses, rows):
    S = {s["parameter"]: s["worst_case_value"] for s in stresses}
    R = {r["parameter"]: r["datasheet_limit"] for r in ratings}
    return [{"id": cid, "rating": rt, "stress": st, "max_ratio": mx, "severity": sev, "rule": rule,
             "ratio": round(S[st] / R[rt], 4)} for cid, rt, st, mx, sev, rule in rows]


def bank_entry():
    b3, key, board = b3_rows(BANK, "MMKP Top,max 125 C case (TDK B3264*H", 125.0, 5)
    bv = jl(BV)
    assert bv["board_sha256"] == board, (bv["board_sha256"], board)
    kv = bv["parts"][MPN]
    air = jl(AIR)["by_mpn"][MPN]
    assert air["board_sha256_of_pad_runs"] == board, (air["board_sha256_of_pad_runs"], board)
    rel_air = air["release"]
    assert rel_air["board_sha256_of_release_runs"] == board, rel_air["board_sha256_of_release_runs"]
    st = jl(STEPS)
    assert st["board_sha256_of_pad_runs"] == board and not st["control_failed"], st["control_failed"]
    s24 = next(x for x in st["steps"] if x["I_tank_A"] == 24.0)
    s26 = next(x for x in st["steps"] if x["I_tank_A"] == 26.0)
    assert s24["strict_ok"] and st["highest_step_strict_A"] == 24.0, (s24, st["highest_step_strict_A"])
    h = jl(H)
    assert h["pdf_sha256"].startswith("69b56e62"), h["pdf_sha256"]
    i35 = h["irms_chart_100nF_A"]["35k"]
    sh = share()
    i_allow = round(i35 / sh, 2)
    sh28 = round((28.0 * sh / i35) ** 2 * 20.0, 2)
    w, wa = bv["worst_R0_R1"], bv["worst_any_reading"]
    aw = air["worst"]
    rr, rn = rel_air["18.375 A"]["with_radiation"], rel_air["18.375 A"]["no_radiation"]
    t_rel, t22, t28 = (round(b3[c_]["est_c"], 1) for c_ in ("c17.5_h10", "c22_h10", "c28_h10"))
    hot = {c_: b3[c_]["item"].split(":")[0] for c_ in b3}
    vc = kv["VC_at_Top_max_V"]
    w24 = s24["worst"]
    ratings = [
        {"parameter": "VR DC", "datasheet_limit": 2000, "unit": "V", "basis": "B32643H8104: VR,DC 2000 V at 105 C",
         "source": f"{TDK} p.14 ordering table (2000 V DC / 700 V AC), p.15 technical data"},
        {"parameter": "VC at Top,max", "datasheet_limit": vc, "unit": "V",
         "basis": "Vop derated 1.25 %/C above 105 C (105 < T <= 125 C): 2000 x (1 - 0.0125 x 20) at Top,max 125 C",
         "source": f"{TDK} p.15 technical data (continuous operating voltage)"},
        {"parameter": "VRMS", "datasheet_limit": 700, "unit": "Vrms", "basis": "VR,AC 700 V AC at 105 C, f <= 1 kHz "
         "(the p.21 chart gives 280 V at 35 kHz for 100 nF, which is the current limit in voltage form)",
         "source": f"{TDK} p.14, p.15; p.21 VRMS vs f"},
        {"parameter": "I tank allowed @35kHz", "datasheet_limit": i_allow, "unit": "A",
         "basis": f"worst-share J part (share {sh:.4f}) at the 35 kHz floor on the p.19 curve: {i35} A for dT <= 20 K at "
                  "TA 85 C (digitised, controls pass: 100 kHz 0.989 x the table's 9.17 A)", "source": H},
        {"parameter": "Self-heating allowance", "datasheet_limit": 20, "unit": "K",
         "basis": "the p.19 curve's basis: sine, TA = 85 C, dT <= 20 C (p.14 note 3)", "source": f"{TDK} p.14 note 3, p.19"},
        {"parameter": "Self-heating allowance at T_A (declared airflow)", "datasheet_limit": aw["dT_allowed_K"], "unit": "K",
         "basis": f"20 K x F_T(T_A)^2 at the worst column point's T_A {aw['T_A_C']} C (p.22 F_T, digitised; Top = TA + dT "
                  "<= 125 C)", "source": f"{TDK} p.22; {H} F_T; bank28-air/scripts/bank_air_metric.py"},
        {"parameter": "Self-heating allowance at T_A (declared airflow, 24 A step)", "datasheet_limit": w24["dT_allowed_K"],
         "unit": "K", "basis": f"20 K x F_T(T_A)^2 at the 24 A step's worst column point, T_A {w24['T_A_C']} C",
         "source": f"{TDK} p.22; {STEPS}"},
        {"parameter": "Self-heating allowance at T_A (release, still air)", "datasheet_limit": rr["dT_allowed_K"],
         "unit": "K", "basis": f"20 K x F_T(T_A)^2 at the release worst point, T_A {rr['T_A_C']} C",
         "source": f"{TDK} p.22; {AIR} release"},
        {"parameter": "Top,max", "datasheet_limit": 125, "unit": "C", "basis": "max. operating temperature (case, TA + "
         "self-heating)", "source": f"{TDK} p.2 climatic; p.15 technical data"},
        {"parameter": "dV/dt", "datasheet_limit": 3800, "unit": "V/us", "basis": "22.5 mm, 2000 V DC / 700 V AC",
         "source": f"{TDK} p.16 dV/dt values"}]
    stresses = [
        {"parameter": "V peak 28 A", "worst_case_value": 566, "unit": "V",
         "condition": "estimated peak at 28 A (268 Vrms bound x round-6 peak/rms 2.113); same 0.50 uF J bank",
         "evidence": f"{C34}:37"},
        {"parameter": "V peak no-pan fault", "worst_case_value": 775, "unit": "V",
         "condition": "no-pan fault peak, same 0.50 uF bank; checked against VC at Top,max (125 C)", "evidence": f"{C34}:186"},
        {"parameter": "V rms 28 A", "worst_case_value": 268, "unit": "Vrms",
         "condition": "bound: I <= 28 A, f >= 35 kHz, C >= 0.475 uF", "evidence": f"{C34}:33"},
        {"parameter": "I tank release trip", "worst_case_value": 18.4, "unit": "A",
         "condition": "17.5 A release ceiling at its 18.375 A firmware RMS trip (b3_ratings_gate BASIS c17.5_h10)",
         "evidence": "validation-results/04-board-current-thermal/round5-native21/b3-ratings/b3_ratings_gate.py:29-30"},
        {"parameter": "I tank ladder 24 A (strict)", "worst_case_value": 24, "unit": "A",
         "condition": f"the highest commissioned ladder step this bank holds strictly on this board: vendor ratio "
                      f"{s24['vendor_85C']}, bank_air strict {s24['gate_strict']} at 24 A (the 85 % rule binds at "
                      f"{st['tank_A_at_vendor_0.85']} A)", "evidence": STEPS},
        {"parameter": "I tank ladder 26 A", "worst_case_value": 26, "unit": "A",
         "condition": f"the next step: bank_air strict {s26['gate_strict']} passes, the vendor ratio {s26['vendor_85C']} does "
                      "not (85 % rule)", "evidence": STEPS},
        {"parameter": "I tank design", "worst_case_value": 28, "unit": "A",
         "condition": "28 A Kconfig ceiling; the hardware is sized for 28 A (DECISIONS 68). With this bank 28 A needs "
                      "B32643B8104J000 on the same 22.5 mm hole or the 11-body re-floorplan (DECISIONS-DRAFT 74, S28)",
         "evidence": "DECISIONS.md:518"},
        {"parameter": "Self-heating 28 A", "worst_case_value": sh28, "unit": "K",
         "condition": f"the fitted bank at 28 A / 35 kHz in TDK's own terms (isolated part on the p.19 curve at TA 85 C: "
                      f"(I_part / {i35} A)^2 x 20 K)", "evidence": H},
        {"parameter": "Self-heating 24 A, declared airflow", "worst_case_value": w24["dT_col_K"], "unit": "K",
         "condition": f"bank_air_metric.py at a 24 A tank on this board's jetmix pads (board {board[:8]}), strict: "
                      f"{w24['point']}, {w24['position']}, G_board {w24['g_board_bound']}, T_A {w24['T_A_C']} C "
                      f"(gate {s24['gate_strict']})", "evidence": STEPS},
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
                      f"60335-1 19.11's one-fault analysis): 1683 V x top / 118.74 A at the s52 OCP top {w['ocp_top_A']} A "
                      f"({w['network']}, TLV3201 {w['reading']}, HOT5 {w['hot5']}); spec-literal R4 reading {wa['F3_V']} V",
         "evidence": [BV, "DECISIONS.md:853", "validation-results/02-protection-timing/bank-ov-double-fault/results.json"]},
        {"parameter": "V double fault Z0max x OCP top", "worst_case_value": wa["Z0max_x_top_V"], "unit": "V",
         "condition": f"CT-failed double fault bank rule (stage15-28A fault_check.py form): Z0,max {bv['z0_max_ohm']} ohm x "
                      f"the highest s52 OCP top of any TLV3201 reading ({wa['ocp_top_A']} A, {wa['network']} {wa['reading']} "
                      f"{wa['hot5']})", "evidence": BV},
        {"parameter": "dV/dt at turn-off", "worst_case_value": bv["dVdt"]["V_per_us"], "unit": "V/us",
         "condition": "bank-ov-double-fault clamp sizing at the largest turn-off current (155.4 A)",
         "evidence": "validation-results/02-protection-timing/bank-ov-double-fault/results.json"},
        {"parameter": "Body temperature c17.5 (release)", "worst_case_value": t_rel, "unit": "C",
         "condition": f"B3 ratings model s52, release case c17.5_h10 (18.4 A trip, still air, bay 61 C), hottest bank part "
                      f"{hot['c17.5_h10']} (advisory row, board fraction 0.3 assumed; film_mmkp_h spec, ESR 22.9 mOhm worst "
                      "at 40 kHz from the p.15 tan d limits)", "evidence": key("c17.5_h10")},
        {"parameter": "Body temperature c22", "worst_case_value": t22, "unit": "C",
         "condition": f"context: c22_h10, {hot['c22_h10']}, bay 55 C", "evidence": key("c22_h10")},
        {"parameter": "Body temperature c28", "worst_case_value": t28, "unit": "C",
         "condition": f"context: c28_h10 (28 A, 29.4 A trip), still air, bay 55 C, {hot['c28_h10']}", "evidence": key("c28_h10")}]
    checks = mk_checks(ratings, stresses, [
        ("V 28 A", "VR DC", "V peak 28 A", 0.8, "violation", "566 <= 1600 V (0.8 x 2000 V)"),
        ("V no-pan fault hot", "VC at Top,max", "V peak no-pan fault", 0.8, "violation",
         f"775 <= {0.8 * vc:g} V (0.8 x VC {vc:g} V at 125 C)"),
        ("Vrms", "VRMS", "V rms 28 A", 0.8, "violation", "268 <= 560 Vrms (0.8 x 700 V AC)"),
        ("I release", "I tank allowed @35kHz", "I tank release trip", 0.85, "violation",
         f"18.4 A <= 0.85 x {i_allow} A (DECISIONS 37's 85 % rule at the commissioned ceiling)"),
        ("I ladder 24 A (strict)", "I tank allowed @35kHz", "I tank ladder 24 A (strict)", 0.85, "violation",
         f"24 A <= 0.85 x {i_allow} A on the vendor curve: the bank's strict ladder cap (DECISIONS-DRAFT 74)"),
        ("self-heating 24 A, declared airflow", "Self-heating allowance at T_A (declared airflow, 24 A step)",
         "Self-heating 24 A, declared airflow", 1.0, "violation",
         f"{w24['dT_col_K']} K <= {w24['dT_allowed_K']} K in the column at 24 A (strict gate {s24['gate_strict']})"),
        ("I ladder 26 A", "I tank allowed @35kHz", "I tank ladder 26 A", 0.85, "gap",
         f"26 A <= 0.85 x {i_allow} A fails ({s26['vendor_85C']}): 26 A is above this bank's strict cap (S28)"),
        ("I design 28 A", "I tank allowed @35kHz", "I tank design", 0.85, "gap",
         f"28 A <= 0.85 x {i_allow} A fails on this part ({round(28 / i_allow, 3)}): the 28 A route is B32643B8104J000 "
         "(0.831) on the same hole, or the 11-body re-floorplan (OPEN-ITEMS S28)"),
        ("self-heating 28 A", "Self-heating allowance", "Self-heating 28 A", 1.0, "gap",
         f"{sh28} K <= 20 K in TDK's terms at TA 85 C (isolated part; the 28 A route row)"),
        ("self-heating 28 A, declared airflow", "Self-heating allowance at T_A (declared airflow)",
         "Self-heating 28 A, declared airflow", 1.0, "gap",
         f"28 A route (S24 / S28): {aw['dT_col_K']} K <= {aw['dT_allowed_K']} K in the column under the declared flow, "
         f"strict (bank_air_ratio_28A_35k {air['bank_air_ratio_28A_35k']})"),
        ("case 28 A, declared airflow", "Top,max", "Case temperature 28 A, declared airflow", 1.0, "gap",
         f"airflow route: {air['T_op_max_C']} C <= 125 C"),
        ("self-heating release, still air", "Self-heating allowance at T_A (release, still air)",
         "Self-heating release, still air", 1.0, "gap",
         f"S25 pre-lot gate: {rr['dT_K']} K <= {rr['dT_allowed_K']} K at the 18.375 A trip in still air with radiation (eff "
         f"{rr['eff_ratio']}); without radiation {rn['dT_K']} K (eff {rn['eff_ratio']}); the bench closes it"),
        ("V third fault", "VR DC", "V third fault", 0.85, "violation",
         f"F3 {w['F3_V']} V <= 1700 V (0.85 x 2000 V; audit.rs S49_BANK_VR)"),
        ("V double fault", "VR DC", "V double fault Z0max x OCP top", 1.0, "violation", f"{wa['Z0max_x_top_V']} V <= 2000 V"),
        ("dV/dt", "dV/dt", "dV/dt at turn-off", 1.0, "violation", f"{bv['dVdt']['V_per_us']} <= 3800 V/us"),
        ("body c17.5 (release)", "Top,max", "Body temperature c17.5 (release)", 1.0, "violation",
         f"{t_rel} <= 125 C at the release case"),
        ("body c22", "Top,max", "Body temperature c22", 1.0, "gap", f"context: {t22} <= 125 C"),
        ("body c28", "Top,max", "Body temperature c28", 1.0, "gap", f"airflow route (c22/c28): {t28} C vs 125 C in still air "
         "at bay 55 C")])
    return {
        "mpn": MPN, "designators": BANK, "class": "POWER",
        "function": "Resonant tank bank C21-C23/C151/C152, 5 x 100 nF +/-5 %, 2000 VDC MMKP (TDK B3264*H), 22.5 mm, on the "
                    "dual-pitch footprint's 22.5 mm hole (stage 52 prototype BOM, DECISIONS-DRAFT 74; KNSCHA "
                    "MMK104J3DF1KN208G2 is the in-stock fallback, B32643B8104J000 the 28 A part)",
        "status": "PARTIAL",
        "datasheet": {
            "url": None,
            "revision": "TDK B3264*H 'Capacitors for snubbering, resonant circuits, power factor correction (PFC)', June "
                        "2026 (31 pp.); owner-supplied copy",
            "fetched": "2026-10-16", "repo_copy": None, "sha256_prefix16": "69b56e62c5603222",
            "note": "Owner-supplied PDF (c51-bank-source lane; not committed, sha256 69b56e62c56032229f60dd419c301ba1"
                    "6028da245fcbd56dc440abcf4f8ad663). PDF page = footer page. p.2: Top,max 125 C (case), climatic "
                    "55/110/56, PP dielectric on double-sided metallised PET electrodes, plastic case UL 94 V-0, epoxy "
                    "seal, AEC-Q200 compliant. p.3: B32643H lead spacing 22.5 +-0.4, d1 0.8 +-0.05 mm. p.14: B32643H8104+***, "
                    "100 nF, 14.5 x 29.5 x 26.5 mm, IRMS,max 100 kHz 11.03 A at TA 60 C (<= 30 C) / 9.17 A at 85 C (<= 20 C), "
                    "ESRtyp 10.9 mOhm at 100 kHz, untaped MOQ 2080; J = +-5 %, 000 = untaped, lead 6-1 mm (the c51 study "
                    "calls this table p.13). p.15: IEC 60384-16:2019 and AEC-Q200D; TR 105 C, Top,max 125 C (TA + self-"
                    "heating), Tmax 110 C, tan d <= 0.3e-3 at 1 kHz / 1.0e-3 at 100 kHz, 2000 V DC and 700 V AC at 105 C, "
                    "1.25 %/C Vop derating above 105 C, 1.6 VR 2 s terminal-terminal, 2000 V AC 60 s to case. p.16: dV/dt "
                    "3800 V/us, k0 15e6 V^2/us. p.19: IRMS vs f (2000 V, 22.5 mm, TA 85 C, dT <= 20 C). p.22: F_T(TA). "
                    "p.24: damp heat 85 C / 85 % RH, 1000 h at VR (THB). Not a safety capacitor; a HOT-side tank part, so "
                    "no UL / ENEC file is required. DigiKey 306 on 2026-10-16 (sourcing/STOCK-2026-10-16-bank-s52.csv); "
                    "no JLC / LCSC stock: consigned."},
        "ratings": ratings, "stresses": stresses,
        "derating_rule": "Peak voltage <= 80 % of VR (of VC at Top,max for the no-pan fault); AC voltage <= 80 % of VRMS; "
                         "tank RMS current <= 85 % of the worst-share TDK curve at the release trip and at the 24 A strict "
                         "ladder step, and the column self-heating at 24 A within 20 K x F_T(T_A)^2; F3 <= 85 % of VR and "
                         "the CT-failed Z0,max x OCP top <= VR; dV/dt <= p.16; body <= Top,max at the B3 release case. "
                         "26 A, 28 A (vendor curve and column self-heating) and the still-air release self-heating are gaps "
                         "(DECISIONS-DRAFT 74; S24 / S25 / S28).",
        "checks": checks,
        "layout_guidance": [
            {"item": "22.5 mm pitch (the dual-pitch footprint's 22.5 mm pad-2 hole; the 27.5 mm hole stays empty), 0.8 mm "
                     "leads in 1.2 mm drills; 14.5 mm bodies at 15.0 mm row pitch (about 0.5 mm gaps) in the bank column "
                     "x 161-193, y 46-119 kept open for the >= 3 m/s airflow (DECISIONS 68)",
             "enforced_by": "UNCHECKED (bench S25; enclosure airflow S24)"},
            {"item": "pad pattern / mains-side separation", "enforced_by": "native-21/verification/d5_audit.py"},
            {"item": "non-polar THT CPL rotation (0 / 180 equivalent) on the 22.5 mm hole pair; centroid at pad 1 + "
                     "the 22.5 mm hole (bom_cpl_jlc.py DUAL_PITCH)",
             "enforced_by": "validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/audit.py"},
            {"item": "bank-variant fit mark (F.SilkS, tick H = B32643H8104J000 24 A max / B = B32643B8104J000 28 A) "
                     "beside the bank column; the fitted part is recorded per board",
             "enforced_by": "native-21/layout/plan_board_only21.py"}],
        "gaps": [
            "bench: current rating basis. The p.19 curve is digitised (6.155 A at 35 kHz, 6.481 A at 40 kHz; 100 kHz "
            "reads 0.989 x the table's 9.17 A); confirm the rise at 6.2 A / 35 kHz sine on a single part (case, or core "
            "by a thermocouple through the lead).",
            "bench: ESR / tan d at 35 and 40 kHz, at 25 C and about 80 C. ESRtyp 10.9 mOhm is at 100 kHz; the p.15 upper "
            "limits fit R_s 11.25 mOhm + D 2.93e-4 / (2 pi f C), 22.9 mOhm at 40 kHz (B3's worst heat row). The rating "
            "already contains TDK's own ESR, so bank_air depends on it only through the column model.",
            f"desk: the F_T credit. The ladder's T_A is below 85 C, so F_T(T_A) > 1 raises the allowance (1.22 at 60 C, "
            f"p.22 digitised; the 60 C table point gives 1.203). The 24 A step uses {w24['dT_allowed_K']} K at T_A "
            f"{w24['T_A_C']} C.",
            f"bench (S24 / S25): the strict bank_air at 28 A is {air['bank_air_ratio_28A_35k']} on this board and the "
            f"release self-heating in still air without radiation is eff {rn['eff_ratio']}; the S25 pre-lot gate (C151 "
            "interior hot spot + unpowered dummy) confirms the column model before the lot ships.",
            "bench: body dimensions. The datasheet gives 14.5 x 29.5 x 26.5 mm at 15.0 mm row pitch (0.5 mm gaps, no "
            "gap-flow credit): measure 10 bodies.",
            "owner: ceiling. This bank caps the commissioned ladder at 24 A strict (vendor 0.844, gate 0.862; 26 A fails "
            "the 85 % rule at 0.915). 28 A needs B32643B8104J000 on the same hole (vendor 0.831) or the 11-body "
            "re-floorplan (S28). A board marked H, or with no bank-fit mark, is never commissioned above 24 A.",
            "owner: sourcing. Single source (DigiKey 306 on 2026-10-16 against 25 for 5 boards and 2,500 for 500); TDK "
            "lead 28 weeks, untaped MOQ 2080; not on JLC: consigned. Prototype part; the production bank is S28.",
            "desk: approval basis. HOT-side tank part, no UL / ENEC file needed or listed; case UL 94 V-0 (p.2); "
            "AEC-Q200D and IEC 60384-16:2019 (p.15); THB 85 C / 85 % RH 1000 h (p.24)."],
        "finding": None,
        "notes": f"S52 (2026-10-16, {CARD}): replaces KNSCHA MMK104J3DF1KN208G2 (stage 51; in stock, kept as the "
                 "fallback in `alternates`) on the same dual-pitch footprint's 22.5 mm hole. Voltage rows pass with the "
                 "same F3 as c34 (both 2000 V); the current rows set a 24 A strict ladder cap (s51: 22 A)."}


def interp(t):
    for (t0, f0), (t1, f1) in zip(DERATE, DERATE[1:]):
        if t0 <= t <= t1:
            return f0 + (f1 - f0) * (t - t0) / (t1 - t0)
    return 1.0


def l1_entry(old):
    e = copy.deepcopy(old)
    e.pop("status_as_alternate", None)   # a re-run takes the old part from `alternates` (integration fix)
    b3, key, board = b3_rows(["L1"], "B82726 climatic", 125.0, 1)
    lr = jl(L1R)[L1N]
    IR = 24.0
    i61 = round(IR * interp(61.0), 2)
    t_rel, t22, t28 = (round(b3[c]["est_c"], 1) for c in ("c17.5_h10", "c22_h10", "c28_h10"))
    t80, tir = lr["15.0A_80pct_holds_to_local_air_C"], lr["15.0A_IR_holds_to_local_air_C"]
    e.update(mpn=L1N, function="Mains common-mode choke L1, 24 A 0.75 mH (stage 52 prototype lot; B82726S2203A020 20 A "
                               "1.6 mH stays the production part)")
    e["datasheet"]["note"] = ("Same TDK B82726S22*3A020 sheet (May 2026, sha256 e8002bfe4af13edf) as the 2203. p.2: "
                              "polycarbonate base and pressboard spacer UL 94 V-0; clearance >= 2.5 mm, creepage >= 3 mm; "
                              "'Design complies with EN 60938-2 (VDE 0565-2)'; no UL / CSA component file listed. p.3: the "
                              "same dimensional drawing and pin configuration for both codes. p.4: B82726S2243A020 IR 24 A, "
                              "LN 0.75 mH (-30/+50 %), Lstray,typ 8 uH, Rtyp 3.2 mOhm per winding; TR 60 C, 40/125/56. "
                              "p.5: the shared Iop/IR derating curve (IND0372-K-E) and |Z| curves for both codes.")
    R = {r["parameter"]: r for r in e["ratings"]}
    R["I_rated"].update(datasheet_limit=IR, source="p.4 Technical data; Characteristics and ordering codes (B82726S2243A020)")
    R["I_op at 50 C design inlet air"]["datasheet_limit"] = IR
    old67 = R.pop("I_op at 67.7 C")
    R["I_op at 61 C release bay"].update(datasheet_limit=i61, basis=f"Iop/IR {interp(61.0):.4f} at 61 C, linear between "
                                         "the digitised 60 C (1.000) and 65 C (0.964) points; 61 C = the B3 release bay "
                                         "(c18_h10, DECISIONS 56), taken as L1's local air (unmeasured)")
    R["Stray inductance"].update(datasheet_limit=8, basis="Lstray typ, 5 mA, 100 kHz (LR <= 1 mH)",
                                 source="p.4 ordering-code table; Technical data (measuring frequency)")
    b80 = {"parameter": f"I_op at {t80} C", "datasheet_limit": round(15.0 / 0.8, 2), "unit": "A",
           "basis": f"digitised derating (Iop/IR {15.0 / 0.8 / IR:.4f}): the hottest local air at which 15 A stays at 80 %",
           "source": old67["source"]}
    e["ratings"] = [R["I_rated"], R["I_op at 50 C design inlet air"], b80, R["I_op at 61 C release bay"]] + \
                   [r for k, r in R.items() if k not in ("I_rated", "I_op at 50 C design inlet air", "I_op at 61 C release bay")]
    S = {s["parameter"]: s for s in e["stresses"]}
    S["Body temperature c17.5 (release)"].update(
        worst_case_value=t_rel, evidence=key("c17.5_h10") + ["DECISIONS.md:2033-2037"],
        condition=f"B3 ratings body model s52 (board {board[:8]}), release case c17.5_h10: 17.5 A release ceiling at its "
                  "18.375 A trip, still air h 10, bay 61 C; L1 heat 2 x 3.2 mOhm x I^2 (1.44 W at 15 A, scaled to the "
                  "13.5 A firmware inlet bound; DECISIONS 56)")
    S["Body temperature c22"].update(worst_case_value=t22, evidence=key("c22_h10"))
    S["Body temperature c28"].update(worst_case_value=t28, evidence=key("c28_h10"))
    S["Copper loss 15 A"] = {"parameter": "Copper loss 15 A", "worst_case_value": lr["15.0A_copper_loss_W"], "unit": "W",
                             "condition": "2 windings x 3.2 mOhm (Rtyp, 20 C) x 15 A^2 (2203: 2.03 W)", "evidence": L1R}
    e["stresses"] = list(S.values())
    e["checks"] = mk_checks(e["ratings"], e["stresses"], [
        ("I at TR", "I_rated", "I inlet trip", 0.8, "violation", "15 A <= 19.2 A (80 % of IR at 60 C)"),
        ("I at 50 C inlet", "I_op at 50 C design inlet air", "I inlet trip", 0.8, "violation", "DECISIONS.md:66 design inlet 50 C"),
        ("I at 61 C (release bay)", "I_op at 61 C release bay", "I inlet trip", 0.8, "violation",
         f"15 A <= {0.8 * i61:.1f} A (80 % of Iop at the 61 C release bay)"),
        (f"I at {t80} C", f"I_op at {t80} C", "I inlet trip", 0.8, "gap",
         f"boundary case: 15 A is 80 % of Iop only up to {t80} C local air (2203: 67.7 C)"),
        ("envelope at TR", "I_rated", "I inlet envelope", 1.0, "gap", "16.5 A <= IR at 60 C; above 90.2 C it exceeds Iop"),
        ("V", "Rated voltage", "Line high corner", 0.8, "violation", "139.7 <= 200 Vrms"),
        ("body c17.5 (release)", "Climatic upper temperature", "Body temperature c17.5 (release)", 1.0, "violation",
         f"{t_rel} <= 125 C at the release case"),
        ("body c22", "Climatic upper temperature", "Body temperature c22", 1.0, "gap", f"context: {t22} <= 125 C"),
        ("body c28", "Climatic upper temperature", "Body temperature c28", 1.0, "gap", f"context: {t28} <= 125 C")])
    emi, fit = jl(EMI), jl(EMI_FIT)
    e["gaps"] = [
        f"bench: L1 local air is not evidenced; the B3 body ({t_rel} C at the release case, bay 61 C; {t22} / {t28} C at "
        f"c22 / c28; inlet 13.5 A) is a body, not the TDK ambient TA. At the 61 C release bay taken as local air, 15 A is "
        f"{lr['15.0A_at_61C_ratio'] * 100:.0f} % of Iop. 15 A meets 80 % of Iop up to {t80} C local air, and IR itself "
        f"up to {tir} C (13.5 A: {lr['13.5A_80pct_holds_to_local_air_C']} / {lr['13.5A_IR_holds_to_local_air_C']} C).",
        "desk: derating curve digitised from the p.5 figure (+/-3 % of full scale); the boundary moves about +/-2 C.",
        "certifier: TDK lists EN 60938-2 design compliance only, no UL / CSA recognition, so the end-product evaluation "
        "must cover L1.",
        "owner / EMI deviation: the 8 uH stray (2203: 18 uH) loses the DM pole with C2. On the stage-38 EMI model with the "
        f"board alone it is INCONCLUSIVE ({fit_margin(fit)}); with a supply module that brings >= 100 uH DM per line "
        f"at 21 A it passes ({fit_margin(emi)}). MODULE-REQUEST.md item 3 now states that requirement "
        f"({MODREQ}). Prototype lot only: the production part stays the 2203 (owner pre-order).",
        "bench: measure a sample's stray inductance (8 uH typical) and the 70 kHz DM line.",
        "desk: the ALT-D3 surge model carries the CMC's 18 uH DM stray inside a 250-500 uH line-inductance sensitivity "
        "range; 8 uH moves the total by under 4 % (not re-run).",
        "owner: stock. DigiKey 29 / Mouser 62 on 2026-10-16 (sourcing/STOCK-2026-10-13-addendum-s52.csv), JLC C7084710 "
        "0: consigned for the prototype lot."]
    e["notes"] = (f"S52 (2026-10-16, {CARD}): prototype-lot swap from B82726S2203A020 (0 stock, 29 weeks; production, "
                  "owner pre-order, kept in `alternates`) to the 24 A code on the same sheet, drawing and footprint "
                  "(temper:B82726S2_ReviewOnly). Rated 250 V AC, test 1500 V AC line/line, 3.2 mOhm per winding "
                  "(1.44 W at 15 A against 2.03 W), inductance drop < 10 % at IR DC bias. The 80 % rule holds to "
                  f"{t80} C local air (2203: 67.7 C).")
    return e


def fit_margin(r):
    v = r["verdict"]
    return (f"nominal {v['nominal_min_margin_dB']:.2f} dB, worst sensitivity {v['sensitivity_min_margin_all_dB']:.2f} dB, "
            f"{v['verdict']}")


def ycap_entry(old):
    e = copy.deepcopy(old)
    e.pop("status_as_alternate", None)   # a re-run takes the old part from `alternates` (integration fix)
    s1 = jl(S1)
    assert s1["fitted_mpn"] == YN and s1["fitted_verdict"] == "PASS" and not s1["failed"], s1
    e.update(mpn=YN, function="Y1 line-to-PE capacitors C3/C4, 2.2 nF (Murata Type RA H01F, J4 crimped leads)")
    e["datasheet"] = {
        "url": "https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2308111527_Murata-Electronics-DE1E3RA222MJ4BH01F_C7170908.pdf",
        "revision": "Murata Reference Specification 'Safety Standard Certified Lead Type Disc Ceramic Capacitors for General "
                    "Purpose, Type RA', EGD08G, as of Jun. 2023 (18 pp.), H01F individual specification; LCSC copy",
        "fetched": "2026-10-16", "repo_copy": None, "sha256_prefix16": "c959488a2523ac21",
        "note": "b15-proto-alternates download (not committed). PDF pages; the printed n/17 footer is one less. p.6 (5/17): "
                "UL/cUL UL60384-14 / CSA E60384-14 file E37921; ENEC (VDE) EN60384-14 40043033; CQC CQC16001138225; X1 "
                "AC440 V, Y1 AC400 V, DC1,000 V; -40..125 C. p.9 (8/17): DE1E3RA222MJ4BH01F, char. E, 2200 pF +/-20 %, "
                "D 9.0, T 4.0, F 10.0 (+/-0.8), d 0.6 mm, J4 crimped leads, 500 pcs. p.11: dielectric strength AC4000 V "
                "between leads. p.14 (13/17): life test preceded by 8 kV impulses (1.7/50 us). The A4 / J4 forms differ "
                "only below the body (the J4 crimp seats it); same hole and pad (cpl pin-evidence C7170908)."}
    R = {r["parameter"]: r for r in e["ratings"]}
    R["Y1 rated voltage"].update(datasheet_limit=400, basis="Class Y1 AC400 V(r.m.s.); UL/cUL UL60384-14 / CSA "
                                 "E60384-14 file E37921; ENEC (VDE) EN60384-14 40043033; CQC IEC60384-14",
                                 source="p.6 Approval standard and certified number, 2-2 Rated voltage")
    for k in ("X1 rated voltage", "DC rated voltage"):
        R[k]["source"] = "p.6 2-2"
    R["Operating temperature max"]["source"] = "p.6 2-1"
    R["Y1 impulse"]["source"] = "p.14 item 18 Life"
    S = {s["parameter"]: s for s in e["stresses"]}
    S["Touch current PE open, 132 V"].update(
        worst_case_value=round(s1["fitted_mA"], 4),
        condition=f"stage 52: the stage-38 budget with C3/C4 = {YN} (2200 pF +20 %): {s1['fitted_mA']} mA, margin "
                  f"{s1['fitted_margin_uA']} uA (the A4 part's value; control +-30 % {s1['control_pm30_mA']} mA FAIL)",
        evidence=[S1, "validation-results/07-conducted-emi/leakage/README.md:12"])
    e["checks"] = mk_checks(e["ratings"], e["stresses"], [
        ("V", "Y1 rated voltage", "Line high corner to PE", 0.8, "violation", "<= 320 V"),
        ("surge", "Y1 impulse", "Surge voltage bound line-PE", 0.5, "violation", "2.2 kV <= 4 kV"),
        ("touch current", "Touch-current budget (requirement, not a datasheet limit)", "Touch current PE open, 132 V", 1.0,
         "violation", f"{s1['fitted_mA']:.4f} <= 0.25 mA (margin {s1['fitted_margin_uA']:.1f} uA)")])
    e["layout_guidance"] = [{"item": "PE branch via J6; Y-cap footprint pad 1.5 mm, P10 (same pads and drill as the A4 "
                                     "part; J4 leads protrude 1.35-2.85 mm from the board: trim to ASSEMBLY.md's 2.5 mm)",
                             "enforced_by": "validation-results/13-external-review-2026-10-13/FINDINGS.md:28"}]
    e["gaps"] = [
        "certifier: the 0.5 mA limit clause (UL 1026 portable) is unconfirmed; owner: the 0.2412 mA pass depends on the "
        "off-board D-22 module Y removal and PS3 = MPM-65-15ST, and fails with +0.15 nF Y per line.",
        "owner: the spec is Murata's Jun 2023 reference specification from a distributor; Murata asks buyers to consult "
        "the approval sheet before ordering.",
        "bench: surface temperature (125 C limit incl. self-heating) is not evidenced; B3 has no C3/C4 row."]
    e["notes"] = (f"S52 (2026-10-16, {CARD}): replaces {YO} (Y1 300 V, A4 long leads; JLC 6, kept in `alternates`) "
                  "with the H01F code (Y1 400 V, J4 crimp; JLC C7170908 104): same body, P10 pads and certificates, "
                  "S1 unchanged, creepage unchanged (same pads).")
    return e


def main():
    led = json.loads(LEDGER.read_text())
    E = led["entries"]
    alt = dict(led.get("alternates", {}))
    src = {MPN: (KN, E.get(KN) or alt.get(KN)), L1N: (L1O, E.get(L1O) or alt.get(L1O)), YN: (YO, E.get(YO) or alt.get(YO))}
    new = {MPN: bank_entry(), L1N: l1_entry(src[L1N][1]), YN: ycap_entry(src[YN][1])}
    swap = {o: n for n, (o, _) in src.items()}
    out = {}
    for k, v in E.items():
        if k in swap:
            out[swap[k]] = new[swap[k]]
        elif k in new:
            out[k] = new[k]
        else:
            out[k] = v
    notes = {
        KN: "NOT FITTED. Stage 52 (DECISIONS-DRAFT 74): the in-stock fallback bank (JLC C528962) on the dual-pitch "
            "footprint's 27.5 mm hole; this is its stage-51 audit on the s51 board (0b0ebcf7): 22 A strict ladder cap. "
            "The gate does not read `alternates`.",
        L1O: "NOT FITTED on the prototype lot. Stage 52 (DECISIONS-DRAFT 74): the production L1 (owner pre-order, 29 "
             "weeks); this is its s51 audit (0b0ebcf7). Same footprint and sheet as B82726S2243A020. The gate does not "
             "read `alternates`.",
        YO: "NOT FITTED. Stage 52 (DECISIONS-DRAFT 74): the A4 long-lead form of the same Y1 disc (Y1 300 V on its own "
            "P01F spec; Mouser 773 on 2026-10-16); same pads, S1 unchanged. The gate does not read `alternates`."}
    for o, _ in src.values():
        if o in E:
            alt[o] = dict(E[o])
        alt[o]["status_as_alternate"] = notes[o]
    if TB in alt:
        alt[TB]["status_as_alternate"] = (
            "NOT FITTED. Stage 52 (DECISIONS-DRAFT 74): the 28 A bank on the dual-pitch footprint's 22.5 mm hole (the same "
            "hole as the fitted B32643H8104J000; tick B on the bank-fit mark); this is its stage-49 / 50 audit on the s50 "
            "board (integration build e842d9c8; lane 4876c42e). 28-week lead, MOQ 2080; the 28 A route of OPEN-ITEMS S28. "
            "The gate does not read `alternates`.")
    led["alternates"] = alt
    led["entries"] = out
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print("ledger: entries", len(out), "alternates", sorted(alt))
    for m in (MPN, L1N, YN):
        for c in out[m]["checks"]:
            print(f"  {m:20} {c['id']:38} {c['ratio']:.4f} <= {c['max_ratio']} {c['severity']:9} {c['rule'][:80]}")


if __name__ == "__main__":
    main()
