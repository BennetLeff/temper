#!/usr/bin/env python3
"""Stage 49 datasheet-ledger edit (c34 bank, S23 B'-1.02 V OCP divider): run after the s49 chain, bands49.py and
bank_voltage49.py.

    python3 -I scripts/ledger49.py    -> native-21/verification/datasheet-ledger/ledger.json (in place)

* B32654A1104J000 -> B32643B8104J000 (C21-C23, C151, C152), audited from TDK B3264*B (June 2026, 38 pp., sha256
  ab9fdca0b9676c85...; PDF page = footer page): p.2 (Top,max 125 C case, lead spacing 22.5 +-0.4 mm, d1 0.8 mm, UL 94 V-0
  case, AEC-Q200D), p.11 (B32643B8104+***: 100 nF, 14.5 x 29.5 x 26.5 mm, IRMS 8.3 A at 85 C / 100 kHz for dT <= 15 K
  (note 8), ESR 8 mOhm, VR 2000 V DC, VRMS 500 V AC, untaped MOQ 2080), p.12 (TR 85 C, Top,max 125 C, VC = VR x
  (165 - Top) / 80 above 85 C, test 1.6 VR 2 s, tan d 0.6 / 1.5 e-3 at 10 / 100 kHz), p.13 (dV/dt 3800 V/us, k0
  15e6 V^2/us, 22.5 mm, 2000 V / 500 V AC). Voltages from c34 (normal, no-pan) and from results/bank-voltage-s49.json
  (F3 at this board's OCP band, Z0,max x top); current on the vendor curve from c34 bank_margin.json; self-heating
  under the declared airflow from bank28-air/results/bank_air_metric.json (this board's jetmix pads); body rows keyed
  into b3-ratings/margins.json (the hottest bank part per case; advisory rows, board share 0.3).
* S23 B'-1.02 V: R33 RT0603BRD0710KL -> RT0603BRD077K5L (new entry), R34 RT0603BRD0712K6L -> RT0603BRD0716KL (new
  entry; the 12.6 k line leaves the BOM), R35 TNPW060311K7BEEA -> RT0603BRD0711KL (an existing line; TNPW keeps R145).
  The new entries carry the RT0603 ratings (Yageo RT V.16 p.5 Table 2, p.6 Fig. 6) and R33 / R34 local temperatures from
  results/bands-s49.json (the same B3 gate estimator, this board), at P from the divider arithmetic at REF25 2.5162 V.
Re-running it on the edited ledger gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
MARGINS = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
KELVIN = PS / "validation-results/02-protection-timing/kelvin/kelvin_plane.py"
C49 = "validation-results/11-candidates/c49-c34-bank"
BANDS, BV = f"{C49}/results/bands-s49.json", f"{C49}/results/bank-voltage-s49.json"
AIR = "validation-results/11-candidates/bank28-air/results/bank_air_metric.json"
BM = "validation-results/11-candidates/c34-bank-margin/results/bank_margin.json"
C34 = "validation-results/11-candidates/c34-bank-margin/README.md"
OLD, MPN = "B32654A1104J000", "B32643B8104J000"
BANK = ["C21", "C22", "C23", "C151", "C152"]
CARD = f"{C49}/README.md"
YAGEO = "Yageo RT series V.16 (May 06, 2025) p.5 Table 2, p.6 Fig. 6 (sha 0a729d144519a702)"
REF_MAX = 2.5162          # LM4050AEM3-2.5 VR max (SNOS455H 5.6 p.7), as ledger48 / kelvin_budget CENSUS48
SHUNT_V = 0.2             # 200 A x 1 mOhm: a bound on -V(ocp_kelvin_n) above any trip / turn-off current (I_off 155 A)


def jl(rel):
    return json.loads((PS / rel).read_text())


def b3_bank():
    m = json.loads(MARGINS.read_text())
    import re
    pin = re.search(r'"native21s49": "([0-9a-f]{64})"', KELVIN.read_text())
    sha = set(m["board_sha256"].values())
    assert pin and sha == {pin.group(1)}, ("margins.json is not the s49 board", sha, pin and pin.group(1))
    out = {}
    for c, rows in m["cases"].items():
        hit = [r for r in rows if r["item"].split(":")[0] in BANK]
        assert len(hit) == 5 and all("MMKP Top,max" in r["item"] and r["limit_c"] == 125.0 for r in hit), (c, hit)
        out[c] = max(hit, key=lambda r: r["est_c"])
    return out, str(MARGINS.relative_to(PS)), pin.group(1)


def bank_entry():
    b3, rel, board = b3_bank()
    key = lambda c: [{"file": rel, "b3_row": {"case": c, "item": " ".join(b3[c]["item"].split()[:3])},
                      "est_c": b3[c]["est_c"]}]
    bv = jl(BV)
    assert bv["board_sha256"] == board, (bv["board_sha256"], board)
    air = jl(AIR)["by_mpn"][MPN]
    assert air["board_sha256_of_pad_runs"] == board, (air["board_sha256_of_pad_runs"], board)
    row = next(r for r in jl(BM)["banks"] if r["bank"].startswith("5 x B32643B8104J"))
    i_allow, sh28 = row["tank_A_at_curve_35k"], row["self_heating_at_28A_35k_K"]
    w, wa = bv["worst_R0_R1"], bv["worst_any_reading"]
    aw = air["worst"]
    t_rel, t22, t28 = (round(b3[c]["est_c"], 1) for c in ("c17.5_h10", "c22_h10", "c28_h10"))
    hot = {c: b3[c]["item"].split(":")[0] for c in b3}
    ratings = [
        {"parameter": "VR DC", "datasheet_limit": 2000, "unit": "V", "basis": "B32643B8104: 2000 V DC",
         "source": "p.11 ordering table (VR = 2000 V DC, VRMS = 500 V AC)"},
        {"parameter": "VC at Top,max", "datasheet_limit": 1000, "unit": "V",
         "basis": "category voltage VC = VR x (165 - Top) / 80 for 85 < Top <= 125 C: 2000 x 40 / 80 at 125 C",
         "source": "p.12 technical data"},
        {"parameter": "VRMS", "datasheet_limit": 500, "unit": "Vrms", "basis": "500 V AC", "source": "p.11 ordering table"},
        {"parameter": "I tank allowed @35kHz", "datasheet_limit": i_allow, "unit": "A",
         "basis": "worst-share J part (+/-5 %) at the 35 kHz floor on TDK's 85 C permissible-current curve (dT 15 K basis; "
                  "c34 bank_margin.py, banks '5 x B32643B8104J', tank_A_at_curve_35k)", "source": BM},
        {"parameter": "Self-heating allowance", "datasheet_limit": 15, "unit": "K",
         "basis": "IRMS,max holds for dT <= 15 C (85 C, 100 kHz)", "source": "p.11 note 8"},
        {"parameter": "Self-heating allowance at T_A (declared airflow)", "datasheet_limit": aw["dT_allowed_K"], "unit": "K",
         "basis": f"15 K x F_T(T_A)^2 at the worst column point's T_A {aw['T_A_C']} C (F_T = 1 at <= 85 C; above, "
                  "(125 - T_A) / 40, the bank28-air p.25 fit)", "source": "p.11 note 8; p.25 (bank28-air fit)"},
        {"parameter": "Top,max", "datasheet_limit": 125, "unit": "C", "basis": "max. operating temperature (case)",
         "source": "p.2 climatic; p.12 technical data"},
        {"parameter": "dV/dt", "datasheet_limit": 3800, "unit": "V/us", "basis": "22.5 mm, 2000 V DC / 500 V AC, "
         "non-sinusoidal isolated pulses", "source": "p.13 dV/dt values"}]
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
        {"parameter": "I tank design", "worst_case_value": 28, "unit": "A",
         "condition": "28 A Kconfig ceiling; the hardware is sized for 28 A (DECISIONS 68)", "evidence": "DECISIONS.md:518; DECISIONS.md:566"},
        {"parameter": "Self-heating 28 A", "worst_case_value": sh28, "unit": "K",
         "condition": "the fitted bank at 28 A / 35 kHz in TDK's own terms (isolated part, vendor curve, c34 table)",
         "evidence": BM},
        {"parameter": "Self-heating 28 A, declared airflow", "worst_case_value": aw["dT_col_K"], "unit": "K",
         "condition": f"bank_air_metric.py on this board's jetmix pads (board {board[:8]}): worst of the declared design flow "
                      f"(base h 20 + jets) at 61 / 55 C air, interior / end column positions, both G_board bounds: "
                      f"{aw['point']}, {aw['position']}, G_board {aw['g_board_bound']}, {aw['v_bank_m_s']} m/s, T_A "
                      f"{aw['T_A_C']} C (bank_air_ratio_28A_35k {air['bank_air_ratio_28A_35k']})", "evidence": AIR},
        {"parameter": "Case temperature 28 A, declared airflow", "worst_case_value": air["T_op_max_C"], "unit": "C",
         "condition": "T_A + dT_col, hottest column point of the same run", "evidence": AIR},
        {"parameter": "V third fault", "worst_case_value": w["F3_V"], "unit": "V",
         "condition": f"F3 (CT-failed third fault, quasi-steady just under the shunt band top, no f floor; outside IEC "
                      f"60335-1 19.11's one-fault analysis): 1683 V x top / 118.74 A at the s49 OCP top {w['ocp_top_A']} A "
                      f"({w['network']}, TLV3201 {w['reading']}, HOT5 {w['hot5']}); 1683 V itself is "
                      f"{bv['F3_ratio_at_committed_1683_V']} of VR; spec-literal R4 reading {wa['F3_V']} V",
         "evidence": [BV, "DECISIONS.md:853", "validation-results/02-protection-timing/bank-ov-double-fault/results.json"]},
        {"parameter": "V double fault Z0max x OCP top", "worst_case_value": wa["Z0max_x_top_V"], "unit": "V",
         "condition": f"CT-failed double fault bank rule (stage15-28A fault_check.py form): Z0,max {bv['z0_max_ohm']} ohm x "
                      f"the highest s49 OCP top of any TLV3201 reading ({wa['ocp_top_A']} A, {wa['network']} {wa['reading']} "
                      f"{wa['hot5']})", "evidence": BV},
        {"parameter": "dV/dt at turn-off", "worst_case_value": bv["dVdt"]["V_per_us"], "unit": "V/us",
         "condition": "bank-ov-double-fault clamp sizing at the largest turn-off current (155.4 A)",
         "evidence": "validation-results/02-protection-timing/bank-ov-double-fault/results.json"},
        {"parameter": "Body temperature c17.5 (release)", "worst_case_value": t_rel, "unit": "C",
         "condition": f"B3 ratings model s49, release case c17.5_h10 (18.4 A trip, still air, bay 61 C), hottest bank part "
                      f"{hot['c17.5_h10']} (advisory row, board fraction 0.3 assumed; film_mmkp spec)", "evidence": key("c17.5_h10")},
        {"parameter": "Body temperature c22", "worst_case_value": t22, "unit": "C",
         "condition": f"context: c22_h10, {hot['c22_h10']}, bay 55 C", "evidence": key("c22_h10")},
        {"parameter": "Body temperature c28", "worst_case_value": t28, "unit": "C",
         "condition": f"context: c28_h10 (28 A, 29.4 A trip), still air, bay 55 C, {hot['c28_h10']}", "evidence": key("c28_h10")}]
    S = {s["parameter"]: s["worst_case_value"] for s in stresses}
    R = {r["parameter"]: r["datasheet_limit"] for r in ratings}

    def chk(cid, rating, stress, mx, sev, rule):
        return {"id": cid, "rating": rating, "stress": stress, "max_ratio": mx, "severity": sev, "rule": rule,
                "ratio": round(S[stress] / R[rating], 4)}
    checks = [
        chk("V 28 A", "VR DC", "V peak 28 A", 0.8, "violation", "566 <= 1600 V (0.8 x 2000 V)"),
        chk("V no-pan fault hot", "VC at Top,max", "V peak no-pan fault", 0.8, "violation",
            "775 <= 800 V (0.8 x VC 1000 V at 125 C)"),
        chk("Vrms", "VRMS", "V rms 28 A", 0.8, "violation", "268 <= 400 Vrms"),
        chk("I release", "I tank allowed @35kHz", "I tank release trip", 0.85, "violation",
            f"18.4 A <= 0.85 x {i_allow} A (DECISIONS 37's 85 % rule at the commissioned ceiling)"),
        chk("I design", "I tank allowed @35kHz", "I tank design", 0.85, "violation",
            f"28 A <= 0.85 x {i_allow} A on the vendor curve (c34: 0.831)"),
        chk("self-heating 28 A", "Self-heating allowance", "Self-heating 28 A", 1.0, "violation",
            f"{sh28} K <= 15 K in TDK's terms"),
        chk("self-heating 28 A, declared airflow", "Self-heating allowance at T_A (declared airflow)",
            "Self-heating 28 A, declared airflow", 1.0, "gap",
            f"airflow route (S24 / S25): {aw['dT_col_K']} K <= {aw['dT_allowed_K']} K in the 0.5 mm-gap column under the "
            f"declared flow (conservative correlation B); bench S25 confirms"),
        chk("case 28 A, declared airflow", "Top,max", "Case temperature 28 A, declared airflow", 1.0, "gap",
            f"airflow route: {air['T_op_max_C']} C <= 125 C"),
        chk("V third fault", "VR DC", "V third fault", 0.85, "violation",
            f"F3 {w['F3_V']} V <= 1700 V (0.85 x 2000 V; audit.rs S49_BANK_VR)"),
        chk("V double fault", "VR DC", "V double fault Z0max x OCP top", 1.0, "violation",
            f"{wa['Z0max_x_top_V']} V <= 2000 V"),
        chk("dV/dt", "dV/dt", "dV/dt at turn-off", 1.0, "violation", f"{bv['dVdt']['V_per_us']} <= 3800 V/us"),
        chk("body c17.5 (release)", "Top,max", "Body temperature c17.5 (release)", 1.0, "violation",
            f"{t_rel} <= 125 C at the release case"),
        chk("body c22", "Top,max", "Body temperature c22", 1.0, "gap", f"context: {t22} <= 125 C"),
        chk("body c28", "Top,max", "Body temperature c28", 1.0, "gap",
            f"airflow route (c22/c28): {t28} C vs 125 C in still air at bay 55 C")]
    return {
        "mpn": MPN, "designators": BANK, "class": "POWER",
        "function": "Resonant tank bank C21-C23/C151/C152, 5 x 100 nF +/-5 %, 2000 VDC MMKP, 22.5 mm (stage 49, candidate 34)",
        "status": "PARTIAL",
        "datasheet": {
            "url": "https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MMKP_B32641B_B32643B.pdf",
            "revision": "TDK B3264*B 'Capacitors for snubbering, resonant circuits, PFC - High frequency', June 2026 (38 pp.)",
            "fetched": "2026-10-16", "repo_copy": None, "sha256_prefix16": "ab9fdca0b9676c85",
            "note": "bank28-air download (runs-native21/bank28/dl/b3264/MMKP_B32641B_B32643B.pdf, = c34's), not committed; "
                    "PDF page = footer page. p.2: Top,max 125 C (case), climatic 55/110/56, PP dielectric, UL 94 V-0 case, "
                    "AEC-Q200D, B32643B lead spacing 22.5 +-0.4 mm, d1 0.8 +-0.05 mm. p.11 (22.5 mm table): "
                    "B32643B8104+***, 100 nF, 14.5 x 29.5 x 26.5 mm, IRMS,max 8.3 A at 85 C / 100 kHz for dT <= 15 K "
                    "(note 8), ESR 8 mOhm, ESL 11 nH, VR 2000 V DC, VRMS 500 V AC, untaped MOQ 2080; J = +-5 %, 000 = "
                    "untaped. p.12: TR 85 C, Top,max 125 C, Tmax 110 C, tan d 0.6 / 0.6 / 1.5 e-3 at 1 / 10 / 100 kHz, "
                    "test 1.6 VR 2 s terminal to terminal, 2000 V AC 60 s to case, VC = VR x (165 - Top) / 80 above "
                    "85 C, Vop 1.25 VC for 1000 h. p.13: dV/dt 3800 V/us and k0 15e6 V^2/us at 22.5 mm, 2000 V / "
                    "500 V AC. Not a safety capacitor; a HOT-side tank part (no UL / CSA file needed). LCSC C3781430 "
                    "(JLC 0 stock; ruled out by the owner 2026-10-16, interim part, DECISIONS 70)."},
        "ratings": ratings, "stresses": stresses,
        "derating_rule": "Peak voltage <= 80 % of VR (of VC at Top,max for the no-pan fault); AC voltage <= 80 % of VRMS; "
                         "tank RMS current <= 85 % of the worst-share TDK curve at the release trip and at 28 A; F3 <= 85 % "
                         "of VR and the CT-failed Z0,max x OCP top <= VR; dV/dt <= p.13; body <= Top,max at the B3 release "
                         "case. The 28 A physical self-heating (column, declared airflow) and the still-air c22 / c28 bodies "
                         "are the airflow-route gap (DECISIONS 68, S24 / S25).",
        "checks": checks,
        "layout_guidance": [
            {"item": "22.5 mm pitch, 0.8 mm leads in 1.2 mm drills; bodies at 15.0 mm row pitch (0.5 mm gaps) in the bank "
                     "column x 161-193, y 46-119 kept open for the >= 3 m/s airflow (DECISIONS 68)",
             "enforced_by": "UNCHECKED (bench S25; enclosure airflow S24)"},
            {"item": "pad pattern / mains-side separation", "enforced_by": "native-21/verification/d5_audit.py"},
            {"item": "non-polar THT CPL rotation (0 / 180 equivalent) from the p.2 drawing",
             "enforced_by": "validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/audit.py"}],
        "gaps": [
            f"owner: airflow route (S24 / S25): at 28 A the column model under the declared design flow gives "
            f"{aw['dT_col_K']} K against {aw['dT_allowed_K']} K (bank_air_ratio_28A_35k {air['bank_air_ratio_28A_35k']}, "
            f"conservative correlation, this board's pads); in still air the c28 bodies reach {t28} C. The pre-lot bench gate "
            f"(S25: C151 hot spot + unpowered dummy, TDK Fig. 26) confirms the model.",
            "owner: sourcing. JLC C3781430 shows 0 stock; untaped MOQ 2080 (p.11), 28-week lead (DECISIONS 37 / 68). The owner "
            "ruled it out on 2026-10-16 (it cannot be sourced; DECISIONS 70): this is the interim bank part of s49, not on the "
            "pre-order list. A later stage replaces it with an in-stock part that passes the same F3 / bank_air checks.",
            "desk: the TDK current curve and the F_T derating are the repo's digitisations (c34 / bank28-air), and B3's bank "
            "rows are advisory (board fraction 0.3 assumed)."],
        "finding": None,
        "notes": f"S49 (2026-10-16, {CARD}): replaces B32654A1104J000 (1600 V, 27.5 mm, Top,max 110 C, dT 20 K basis). "
                 "F3 closes at 2000 V (it was 1.05 x VR on the fitted bank); the vendor-curve 28 A rows pass (0.831); the "
                 "B3 rows are now the film_mmkp spec (lead path 50 K/W, ESR 8 mOhm typ fit of the p.12 tan d)."}


RT_FUNC = {"RT0603BRD077K5L": ("R33", 7.5e3, "7.5 k 0.1 % OCP divider bottom (ocp_node to ocp_kelvin_n; S23 B'-1.02 V)"),
           "RT0603BRD0716KL": ("R34", 16e3, "16 k 0.1 % OCP threshold top (REF25 to ocp_thresh; S23 B'-1.02 V)")}


def rt_entry(mpn):
    ref, r, func = RT_FUNC[mpn]
    b = jl(BANDS)
    if ref == "R33":       # R32 + R33 string from REF25 to ocp_kelvin_n, which sits at -I x R5 (bounded at 0.2 V)
        v = (REF_MAX + SHUNT_V) * 7.5e3 / 17.5e3
        cond = f"(REF25 max {REF_MAX} V + {SHUNT_V} V shunt bound) x 7.5 / 17.5 k"
    else:                  # R34 + R35 string from REF25 to OCP_KELVIN_P
        v = REF_MAX * 16e3 / 27e3
        cond = f"REF25 max {REF_MAX} V x 16 / 27 k"
    p = v * v / r
    lim = round(155.0 - (155.0 - 70.0) * p / (0.8 * 0.1), 1)
    t = {c: b["solved_temperatures_C"][c][ref] for c in ("c17.5_h10", "c28_h10")}
    ratings = [
        {"parameter": "Working voltage", "datasheet_limit": 75, "unit": "V", "basis": "RT0603 max. working voltage 75 V "
         "(overload 150 V)", "source": YAGEO},
        {"parameter": "Rated power at 70 C", "datasheet_limit": 0.1, "unit": "W", "basis": "RT0603 1/10 W at 70 C, linear "
         "to 0 at 155 C", "source": YAGEO},
        {"parameter": "Terminal temperature limit at P (derating line, 20 % margin)", "datasheet_limit": lim, "unit": "C",
         "basis": f"155 - (155 - 70) x {p:.4g} W / (0.8 x 0.1 W): operating -55..+155 C and the Fig. 6 derating line with "
                  "the G6 20 % power margin", "source": YAGEO}]
    stresses = [
        {"parameter": f"V across {ref}", "worst_case_value": round(v, 3), "unit": "V", "condition": cond,
         "evidence": "elec/src/power_stage_120v.ato; audit.rs"},
        {"parameter": f"P in {ref}", "worst_case_value": round(p, 6), "unit": "W", "condition": f"V^2 / {r / 1e3:g} k",
         "evidence": "elec/src/power_stage_120v.ato; audit.rs"},
        {"parameter": "Local temperature, release case (c17.5_h10 @ 61 C)", "worst_case_value": t["c17.5_h10"], "unit": "C",
         "condition": f"{ref}: pad estimate (B3 gate estimator Q(0.25) + 3 |Q(0.25) - Q(0.5)| + bay - 50 on the run "
                      "files' pad-copper probe), c17.5_h10 still air at bay 61 C; board s49", "evidence": BANDS},
        {"parameter": "Local temperature, c28_h10 @ 55 C", "worst_case_value": t["c28_h10"], "unit": "C",
         "condition": f"{ref}: same estimator, c28_h10 still air at bay 55 C; board s49", "evidence": BANDS}]
    checks = [
        {"id": "V", "rating": "Working voltage", "stress": f"V across {ref}", "max_ratio": 0.5, "severity": "violation",
         "rule": f"{v:.3f} V <= half the 75 V working voltage", "ratio": round(v / 75, 4)},
        {"id": "P", "rating": "Rated power at 70 C", "stress": f"P in {ref}", "max_ratio": 0.5, "severity": "violation",
         "rule": f"{p * 1e3:.3f} mW <= half of 0.1 W", "ratio": round(p / 0.1, 4)},
        {"id": "temperature, release case", "rating": "Terminal temperature limit at P (derating line, 20 % margin)",
         "stress": "Local temperature, release case (c17.5_h10 @ 61 C)", "max_ratio": 1.0, "severity": "violation",
         "rule": f"{t['c17.5_h10']} C <= {lim} C ({ref})", "ratio": round(t["c17.5_h10"] / lim, 4)},
        {"id": "temperature, c28", "rating": "Terminal temperature limit at P (derating line, 20 % margin)",
         "stress": "Local temperature, c28_h10 @ 55 C", "max_ratio": 1.0, "severity": "gap",
         "rule": f"{t['c28_h10']} C <= {lim} C ({ref}); an overrun is the airflow-route (c22/c28) owner gap",
         "ratio": round(t["c28_h10"] / lim, 4)}]
    return {"mpn": mpn, "designators": [ref], "class": "SIGNAL", "function": func, "status": "PARTIAL",
            "datasheet": {"url": "https://www.yageogroup.com/component-documentation/download/specsheet/RT0603BRD0710KL",
                          "revision": "Yageo RT series 0100 to 2512, V.16 (May 06, 2025)", "fetched": None, "repo_copy": None,
                          "sha256_prefix16": "0a729d144519a702",
                          "note": "the RT series sheet the temp-ratings rows cite (local copy runs-native21/pin-absmax-dl/pdf/"
                                  "yageo_rt.pdf); p.5 Table 2 RT0603: 1/10 W, 75 V working, 150 V overload, 0.1 % / 25 ppm "
                                  "1 R to 1 M; p.6 Fig. 6 derating to 0 at 155 C. LCSC "
                                  + ("C728597" if ref == "R33" else "C326732") + "."},
            "ratings": ratings, "stresses": stresses, "derating_rule": "V and P <= half the RT0603 ratings; pad <= the "
            "derating line at P with the G6 20 % margin at the release case (c28 reported)", "checks": checks,
            "layout_guidance": [],
            "gaps": ["Not audited (outside SAFETY/POWER).",
                     "the local temperature is the B3 body-model pad estimate (hot copper, still air at the BASIS bays), not a "
                     "measurement; it is the S21 estimator on this board's run files (results/bands-s49.json), so the s49 "
                     "re-base (temps_snap49.py) counts this line as rated and leaves it"],
            "finding": None, "notes": f"S49 (2026-10-16, {CARD}): S23 B'-1.02 V divider (U6 VCM 1.0185 V, nominal 92.593 A)."}


MOVE = {"RT0603BRD0710KL": ("R33", None, "stage 49: R33 moves to RT0603BRD077K5L (S23 B'-1.02 V)"),
        "TNPW060311K7BEEA": ("R35", None, "stage 49: R35 moves to RT0603BRD0711KL (S23 B'-1.02 V); this line is R145 only"),
        "RT0603BRD0711KL": (None, "R35", "stage 49: R35 is the OCP threshold bottom (ocp_thresh to OCP_KELVIN_P, S23 B'-1.02 V)")}
GAP49 = ("[stage 49] the temperature rows were computed before the S23 divider change ({}); the S21 temp-ratings re-base "
         "on s49 (integration) recounts them")
# GAP49 was the lane's gap text. On ps-integrate the S21 temperature pipeline is re-based on the s49 chain and BOM
# (temps_snap49.py; temp_ratings.py --rebase --stage s49; ledger_temps.py --board-tag s49), which recounts these lines on
# their s49 designators, so the gap no longer holds: it is removed where present and not added (as ledger48's GAP48).


def main():
    led = json.loads(LEDGER.read_text())
    E = led["entries"]
    bank = bank_entry()
    out = {}
    for k, v in E.items():
        if k in (OLD, MPN):
            if MPN not in out:
                out[MPN] = bank
        elif k in ("RT0603BRD0712K6L", "RT0603BRD077K5L", "RT0603BRD0716KL"):
            for n in RT_FUNC:
                if n not in out:
                    out[n] = rt_entry(n)
        else:
            out[k] = v
    for mpn, (drop, add, note) in MOVE.items():
        e = out[mpn]
        d = set(e["designators"]) - ({drop} if drop else set()) | ({add} if add else set())
        e["designators"] = sorted(d, key=lambda r: int(r[1:]))
        if note not in e["function"]:
            e["function"] = f"{e['function']}; {note}"
        g = GAP49.format(f"{drop or add} moved")
        e["gaps"] = [x for x in e["gaps"] if x != g]
    led["entries"] = out
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print("ledger: entries", len(out))
    for m in (MPN, *RT_FUNC):
        for c in out[m]["checks"]:
            print(f"  {m:16} {c['id']:38} {c['ratio']:.4f} <= {c['max_ratio']} {c['severity']:9} {c['rule'][:90]}")


if __name__ == "__main__":
    main()
