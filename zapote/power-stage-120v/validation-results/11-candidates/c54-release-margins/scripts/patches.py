#!/usr/bin/env python3
"""Proposed BOM line changes and datasheet-ledger entries for the c54 swaps (for the integration session to apply).

    python3 -I scripts/patches.py     # after release_margins.py; offline (reads the committed JLC / LCSC caches)

Reads results/margins-c54.json (numbers), scripts/jlc-raw/detail_*.json and scripts/lcsc-raw/detail_*.json (stock and
price, with their read times) and the one distributor read that is not cacheable here (DIGIKEY_READS, a web read).
Writes results/bom-patch.json and results/ledger-patch.json, and validates every proposed ledger entry with the ledger
gate's own validate_entry() against the post-swap designators (exit 1 on any error)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
PS = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PS / "native-21/verification/datasheet-ledger"))
import lcsc_stock  # noqa: E402
import gate as ledger_gate  # noqa: E402

REL = "validation-results/11-candidates/c54-release-margins"
MARG = f"{REL}/results/margins-c54.json"
B3M = "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
DIGIKEY_READS = {  # web reads (WebFetch of the Digi-Key keyword page), not cacheable by these scripts
    "16SVPK220M": {"distributor": "Digi-Key", "part": "P124158CT-ND (cut tape)", "stock": 1420,
                   "price_usd_at_1": 1.77, "price_usd_at_10": 1.146, "price_usd_at_100": 0.8032,
                   "price_usd_at_500": 0.66154, "lead_time": "55 weeks (manufacturer standard)",
                   "read": "2026-10-18 (local), https://www.digikey.com/en/products/result?keywords=16SVPK220M"},
}


def jlc(code):
    d = json.loads((HERE / f"jlc-raw/detail_{code}.json").read_text())
    r = d["data"]
    ladder = [(p["startNumber"], p["productPrice"]) for p in r.get("prices") or []]

    def at(n):
        best = None
        for q, pr in sorted(ladder):
            if q <= n:
                best = pr
        return best
    return {"jlc_library": r["componentLibraryType"], "jlc_stock": r["stockCount"], "jlc_price_usd_at_5": at(5),
            "jlc_price_usd_at_500": at(500), "jlc_ladder": ladder, "jlc_read_utc": d["_fetched_utc"]}


def line(mpn, code, refs, footprint, role):
    e = {"mpn": mpn, "lcsc": code, "designators": refs, "footprint": footprint, "role": role}
    e.update(jlc(code))
    ls = lcsc_stock.summary(code)
    e.update({"lcsc_stock": ls["stock"], "lcsc_price_usd_at_5": ls["price_usd_at_5"],
              "lcsc_price_usd_at_500": ls["price_usd_at_500"], "lcsc_ladder": ls["ladder"], "lcsc_read_utc": ls["read_utc"]})
    if mpn in DIGIKEY_READS:
        e["distributor_read"] = DIGIKEY_READS[mpn]
    return e


def bom_patch():
    fp_r2512, fp_r0603, fp_cp = ("Resistor_SMD:R_2512_6332Metric", "Resistor_SMD:R_0603_1608Metric",
                                 "Capacitor_SMD:CP_Elec_6.3x5.9")
    changes = [
        {"from": line("25121WF680JT4E", "C50371", ["R10", "R12", "R18", "R20"], fp_r2512, "R_on 68 ohm 1 % 1 W"),
         "to": line("PS122WF680JT4E", "C2793964", ["R10", "R12", "R18", "R20"], fp_r2512, "R_on 68 ohm 1 % 2 W, PS12"),
         "second_source": line("RC2512JK-7W68RL", "C876271", ["R10", "R12", "R18", "R20"], fp_r2512,
                               "68 ohm 5 % 2 W (Yageo RC_L double power; 5 % / 200 ppm)"),
         "source_edit": "elec/src/parts.ato component R68Gate2512: mpn 25121WF680JT4E -> PS122WF680JT4E (value, footprint "
                        "unchanged)"},
        {"from": line("0603WAF4991T5E", "C23046", ["R71", "R72", "R74", "R75", "R131"], fp_r0603, "4.99 k 1 % 0.1 W"),
         "to": line("ERJ-PA3F4991V", "C4036134", ["R71", "R72", "R74", "R75", "R131"], fp_r0603,
                    "4.99 k 1 % 0.25 W (105 C ambient) / 0.33 W (130 C terminal) anti-surge"),
         "second_source": line("RCS06034K99FKEA", "C4104448", ["R71", "R72", "R74", "R75", "R131"], fp_r0603,
                               "4.99 k 1 % 0.25 W at 70 C (Vishay RCS)"),
         "source_edit": "elec/src/f6_parts.ato component Bias4k99 (and whatever component places R131): mpn "
                        "0603WAF4991T5E -> ERJ-PA3F4991V. The whole line moves (R131 too) so the BOM keeps one 4.99 k line; "
                        "0603WAF4991T5E is a JLC basic part, ERJ-PA3F4991V an extended one (one extended line either way)"},
        {"from": line("6SVPC220MV", "C128504", ["C126", "C127", "C128", "C129"], fp_cp, "220 uF 6.3 V OS-CON SVPC, 105 C"),
         "to": line("16SVPK220M", "C542293", ["C126", "C127", "C128", "C129"], fp_cp,
                    "220 uF 16 V OS-CON SVPK, 125 C, same C6 can"),
         "source_edit": "elec/src/f6_parts.ato component Bias220u: mpn 6SVPC220MV -> 16SVPK220M",
         "sourcing_flag": "JLC 0 and LCSC 0 in stock on the read date; Digi-Key 1,420 (55-week factory lead). Buy the 20 "
                          "prototype pieces at Digi-Key and consign them to JLC (or JLC global sourcing); keep 6SVPC220MV as "
                          "the stock fallback (it passes the release case, +4.8 K)"},
    ]
    for c in changes:
        qty = len(c["to"]["designators"])
        for k in ("from", "to"):
            l = c[k]
            l["per_board_usd_at_5_boards"] = round(qty * (l["jlc_price_usd_at_5"] or 0), 4)
            l["per_board_usd_at_500_boards_jlc_ladder"] = round(qty * (_ladder_at(l["jlc_ladder"], 500 * qty) or 0), 4)
        c["delta_usd_per_board_at_500_boards"] = round(c["to"]["per_board_usd_at_500_boards_jlc_ladder"]
                                                        - c["from"]["per_board_usd_at_500_boards_jlc_ladder"], 4)
    return {"study": REL, "board_of_record": "native-21 s53 82af7bd9", "rule": "same footprint, same value, no layout edit",
            "prices": "unit USD; 'at 5' / 'at 500' are the ladder step at 5 / 500 pieces; per-board figures use the JLC "
                      "ladder at 5 x qty and 500 x qty pieces (5 / 500 boards)",
            "changes": changes,
            "frozen_bom_rows_after": [
                'PS122WF680JT4E,"R10,R12,R18,R20",Resistor_SMD:R_2512_6332Metric,PS122WF680JT4E,0.00',
                'ERJ-PA3F4991V,"R71,R72,R74,R75,R131",Resistor_SMD:R_0603_1608Metric,ERJ-PA3F4991V,0.00',
                '16SVPK220M,"C126,C127,C128,C129",Capacitor_SMD:CP_Elec_6.3x5.9,16SVPK220M,0.00'],
            "not_changed": {"U26 TPS7A4700RGWR": "no BOM swap raises TJ max (TPS7A47 and TPS7A47-Q1 are both -40..125 C); "
                                                 "needs layout (README section 4)",
                            "J1": "another lane"}}


def _ladder_at(ladder, n):
    best = None
    for q, pr in sorted(ladder):
        if q <= n:
            best = pr
    return best if best is not None else (sorted(ladder)[0][1] if ladder else None)


def ledger_patch(m):
    rel = m["r_on"]["c17.5_h10"]
    c22, c28 = m["r_on"]["c22_h10"], m["r_on"]["c28_h10"]
    w = rel["R10"]["P_w"]
    t_rel, t22, t28 = rel["R10"]["terminal_est_c"], c22["R12"]["terminal_est_c"], c28["R12"]["terminal_est_c"]
    d = lambda t: round(max(0.0, 2.0 * min(1.0, (155.0 - t) / 85.0)), 4)  # noqa: E731  PS12 2 W curve
    ron = {
        "mpn": "PS122WF680JT4E", "designators": ["R10", "R12", "R18", "R20"], "class": "POWER",
        "function": "Turn-on gate resistors R10/R12/R18/R20, 68 ohm 1 % 2 W 2512 anti-surge (UniRoyal PS12; candidate 54 "
                    "BOM swap for 25121WF680JT4E, same value / footprint; DECISIONS 54 gate network unchanged)",
        "status": "PARTIAL",
        "datasheet": {"url": "https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2304140030_UNI-ROYAL-Uniroyal-Elec-"
                             "PS122WF680JT4E_C2793964.pdf",
                      "revision": "UniRoyal (Uniohm) product catalogue 2023~2024, 200 pp (PDF ModDate 2025-09-16); PS series "
                                  "pp.23-24", "fetched": "2026-10-18", "repo_copy": None, "sha256_prefix16": "ef35c54db5ef3b90",
                      "note": f"LCSC copy (redirects to datasheet.lcsc.com ...72ec9a36...pdf?productCode=C2793964); fetch: "
                              f"{REL}/scripts/fetch_datasheets.py; not committed"},
        "ratings": [
            {"parameter": "Power 70 C", "datasheet_limit": 2.0, "unit": "W", "basis": "rated power at 70 C ambient, PS12 (2512)",
             "source": "p.23 power-rating table (PS12 2W)"},
            {"parameter": "Power derated at the c17.5 terminal estimate (release)", "datasheet_limit": d(t_rel), "unit": "W",
             "basis": f"2 W x (155 - T) / 85 at T = {t_rel:.1f} C (R10 terminal, B3 release case c17.5_h10, bay 61 C); the "
                      "curve is an ambient curve, applied at the terminal (the B3 gate's convention)",
             "source": "p.23 Derating Curve (100 % at 70 C to 0 % at 155 C, 'Ambient temperature')"},
            {"parameter": "Power derated at the c22 terminal estimate", "datasheet_limit": d(t22), "unit": "W",
             "basis": f"2 W x (155 - T) / 85 at T = {t22:.1f} C (R12 terminal, B3 c22_h10, bay 55 C)",
             "source": "p.23 Derating Curve"},
            {"parameter": "Operating temperature max", "datasheet_limit": 155, "unit": "C", "basis": "-55~+155 C",
             "source": "p.23 specification table (Operating Temperature)"},
            {"parameter": "Max working voltage", "datasheet_limit": 500, "unit": "V",
             "basis": "PS12; RCWV = sqrt(P R) = 11.7 V at 68 ohm", "source": "p.23 specification table"},
            {"parameter": "One-pulse limiting power, 1-10 us", "datasheet_limit": 2000.0, "unit": "W",
             "basis": "PS12 curve read from the plot (flat ~2000 W from 1 us to 10 us; single pulse)",
             "source": "p.23 'Curve of Pulse Duration'"},
        ],
        "stresses": [
            {"parameter": "R_on dissipation, 60 kHz window top", "worst_case_value": round(w, 3), "unit": "W",
             "condition": "c28 heat file: (382.6 + 61 nC) x 17 V x 60 kHz per FET, split by resistance; unchanged by the "
                          "swap (same 68 ohm); the gate-network study simulates ~0.17 W",
             "evidence": "validation-results/04-board-current-thermal/round5-native21/b3/inputs/native21-board-heat-sources-c28.json"},
            {"parameter": "Element estimate c17.5 (release)", "worst_case_value": rel["R10"]["element_est_c"], "unit": "C",
             "condition": f"R10, B3 body model c17.5_h10 bay 61 C (chip2512 r_pad 37.6 K/W from the body dimensions, "
                          f"identical for PS12); terminal {t_rel:.1f} C",
             "evidence": [{"file": B3M, "b3_row": {"case": "c17.5_h10", "item": "R10: 2512 element"},
                           "est_c": round(rel["R10"]["element_est_c"], 1)},
                          {"file": B3M, "b3_row": {"case": "c17.5_h10", "item": "R10: 2512 terminal"},
                           "est_c": round(t_rel, 1)}, MARG]},
            {"parameter": "Element estimate c28", "worst_case_value": c28["R12"]["element_est_c"], "unit": "C",
             "condition": f"R12, c28_h10 bay 55 C; terminal {t28:.1f} C",
             "evidence": [{"file": B3M, "b3_row": {"case": "c28_h10", "item": "R12: 2512 element"},
                           "est_c": round(c28["R12"]["element_est_c"], 1)}]},
            {"parameter": "Gate-drive step across R_on", "worst_case_value": 17.0, "unit": "V",
             "condition": "driver swing at the turn-on edge (2EDR8259X, 17 V supply), well under 1 us per edge",
             "evidence": "validation-results/04-board-current-thermal/round5-native21/b3/make_heat_sources.py"},
            {"parameter": "Edge peak power", "worst_case_value": round(17.0 ** 2 / 68.0, 3), "unit": "W",
             "condition": "17 V^2 / 68 ohm (driver and Rg,int ignored: an upper bound), decaying with the gate time constant "
                          "(~1 us); energy ~3.6 uJ per edge (0.217 W / 60 kHz)",
             "evidence": MARG},
        ],
        "derating_rule": "Dissipation <= 80 % of the curve-derated power at the B3 terminal estimate and element <= 155 C at "
                         "the release case (c17.5_h10, bay 61 C; DECISIONS 56/61); c22/c28 are the airflow-route gap; "
                         "voltage <= 80 % of the working voltage.",
        "checks": [
            {"id": "power c17.5 (release)", "rating": "Power derated at the c17.5 terminal estimate (release)",
             "stress": "R_on dissipation, 60 kHz window top", "max_ratio": 0.8, "severity": "violation",
             "rule": f"<= 80 % of the derated power at the release terminal (B3 row R10 "
                     f"{rel['R10']['parts']['PS122WF680JT4E']['margin_k']:+.1f} K once the gate carries the 2 W line, "
                     f"results/b3-gate.patch)"},
            {"id": "element c17.5 (release)", "rating": "Operating temperature max", "stress": "Element estimate c17.5 (release)",
             "max_ratio": 1.0, "severity": "violation", "rule": "element <= 155 C at the release case"},
            {"id": "power c22", "rating": "Power derated at the c22 terminal estimate",
             "stress": "R_on dissipation, 60 kHz window top", "max_ratio": 0.8, "severity": "gap",
             "rule": f"airflow route (c22/c28): passes on the 2 W line (R12 {c22['R12']['parts']['PS122WF680JT4E']['margin_k']:+.1f} K)"},
            {"id": "element c28", "rating": "Operating temperature max", "stress": "Element estimate c28", "max_ratio": 1.0,
             "severity": "gap", "rule": "airflow route (c22/c28): element over 155 C at c28 in still air"},
            {"id": "voltage", "rating": "Max working voltage", "stress": "Gate-drive step across R_on", "max_ratio": 0.8,
             "severity": "violation", "rule": "<= 80 %"},
            {"id": "edge pulse", "rating": "One-pulse limiting power, 1-10 us", "stress": "Edge peak power", "max_ratio": 1.0,
             "severity": "violation", "rule": "edge peak under the single-pulse limit (repetitive heating is the power check)"},
        ],
        "layout_guidance": [
            {"item": "2512 terminal temperature (derating line, 20 % margin) and element",
             "enforced_by": "validation-results/04-board-current-thermal/round5-native21/b3-ratings/b3_ratings_gate.py"},
            {"item": "gate run clearances round the 2512 (3.2 mm to the other potential group)",
             "enforced_by": "native-21/section.kicad_dru"}],
        "gaps": [
            "bench: the terminal temperatures are B3 body-model estimates (still air); the R_on power basis (0.217 W "
            "charge-split bound against the study's ~0.17 W) is an IR bench item.",
            f"owner: airflow route (c22/c28): at c28 (28 A, bay 55 C) the R12 terminal ({t28:.1f} C) is past the curve's 155 C "
            f"zero-power point and the element is {c28['R12']['element_est_c']:.1f} C.",
            "the pulse limit is read from a log-log plot (p.23), not a table.",
            "b3_ratings_gate.py rates every 2512 R_on at 1 W until results/b3-gate.patch (GATE_R_MPN) is applied.",
        ],
        "finding": None,
        "notes": f"Candidate 54 ({REL}). JLC C2793964 extended; stock and price in results/bom-patch.json. Same body and "
                 "terminals as 25121WF680JT4E (V.3 p.4/9 vs catalogue p.23: L 6.35 W 3.20 H 0.55 A 0.60 B 0.50 mm), so "
                 "the B3 solve, heat file and terminal / element estimates are unchanged. Second source: Yageo "
                 "RC2512JK-7W68RL (2 W, 5 %, RC_L V.12 p.6/p.7).",
    }
    ron["checks"][2]["stress"] = "R_on dissipation, 60 kHz window top"

    bl = m["split_bleed"]
    r75r, r75c = bl["cases"]["c17.5_h10"]["R75"], bl["cases"]["c28_h10"]["R75"]
    lim = r75r["parts"]["ERJ-PA3F4991V"]["terminal_limit_c"]
    bleed = {
        "mpn": "ERJ-PA3F4991V", "designators": ["R71", "R72", "R74", "R75", "R131"], "class": "SIGNAL",
        "function": "4.99 k 0603 anti-surge: split bleeds R71/R72/R74/R75 (p -> src) and R131 (candidate 54 swap for "
                    "0603WAF4991T5E, same value / footprint)",
        "status": "PARTIAL",
        "datasheet": {"url": "https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2404091153_PANASONIC-ERJ-PA3F4991V_C4036134.pdf",
                      "revision": "Panasonic 'Anti-Surge Thick Film Chip Resistors ERJ P, PA, PM type', 29-Sep-23, 9 pp.",
                      "fetched": "2026-10-18", "repo_copy": None, "sha256_prefix16": "441511405b982033",
                      "note": f"LCSC copy; fetch: {REL}/scripts/fetch_datasheets.py; not committed"},
        "ratings": [
            {"parameter": "Power at rated ambient 105 C", "datasheet_limit": 0.25, "unit": "W",
             "basis": "ERJPA3 (0603) 0.25 W at rated ambient temperature 105 C", "source": "p.2 Ratings table"},
            {"parameter": "Power at rated terminal part temperature 130 C", "datasheet_limit": 0.33, "unit": "W",
             "basis": "ERJPA3 0.33 W at rated terminal part temperature 130 C; footnote *2 gives this rating priority",
             "source": "p.2 Ratings table, footnote *2"},
            {"parameter": "Terminal temperature limit at P (derating line, 20 % margin), worst ref R75", "datasheet_limit": lim,
             "unit": "C", "basis": f"155 - (155 - 105) x {bl['P_w']:.5f} W / (0.8 x 0.25 W): the ambient line read at the pad "
                                   f"(stricter than the terminal-part line, {r75r['parts']['ERJ-PA3F4991V']['terminal_line_limit_c']:.1f} C); "
                                   f"P = {bl['basis']}",
             "source": "p.3 Power derating curve (ambient: 100 % to 105 C, 0 at 155 C; terminal part: 100 % to 130 C, 0 at 155 C)"},
            {"parameter": "Limiting element voltage", "datasheet_limit": 150, "unit": "V", "basis": "ERJPA3",
             "source": "p.2 Ratings table"},
        ],
        "stresses": [
            {"parameter": "Local temperature, release case (c17.5_h10 @ 61 C)", "worst_case_value": round(r75r["pad_est_c"], 1),
             "unit": "C", "condition": "R75 pad-copper probe, B3 hot-copper estimate, s53 82af7bd9; worst of 5 refs",
             "evidence": MARG},
            {"parameter": "Local temperature, c28_h10 @ 55 C", "worst_case_value": round(r75c["pad_est_c"], 1), "unit": "C",
             "condition": "R75 pad-copper probe, c28_h10 still air bay 55 C", "evidence": MARG},
            {"parameter": "Voltage across the bleed", "worst_case_value": round((bl["P_w"] * 4990.0) ** 0.5, 2), "unit": "V",
             "condition": "V_PN - V_SPLIT (b3_ratings_gate MONITOR_SELF['tlvh431'] basis)", "evidence": MARG},
        ],
        "derating_rule": "Pad (terminal) temperature <= the derating line at P with the 20 % power margin (G6), release case; "
                         "c22/c28 the airflow-route gap; voltage <= 80 % of the limiting element voltage.",
        "checks": [
            {"id": "temperature, release case", "rating": "Terminal temperature limit at P (derating line, 20 % margin), worst ref R75",
             "stress": "Local temperature, release case (c17.5_h10 @ 61 C)", "max_ratio": 1.0, "severity": "violation",
             "rule": f"{r75r['pad_est_c']:.1f} C <= {lim:.1f} C (R75)"},
            {"id": "temperature, c28", "rating": "Terminal temperature limit at P (derating line, 20 % margin), worst ref R75",
             "stress": "Local temperature, c28_h10 @ 55 C", "max_ratio": 1.0, "severity": "gap",
             "rule": f"{r75c['pad_est_c']:.1f} C <= {lim:.1f} C (R75): passes in still air at c28"},
            {"id": "voltage", "rating": "Limiting element voltage", "stress": "Voltage across the bleed", "max_ratio": 0.8,
             "severity": "violation", "rule": "<= 80 %"},
        ],
        "layout_guidance": [],
        "gaps": [
            "the pad temperature is the B3 body-model estimate (still air), not a measurement",
            "the bleeds' own 0.048 W each is not a B3 heat row (b3-ratings/runs/heat_c17.5.json): their pads read board heat "
            "only; same for the fitted part, and the swap leaves ~40 K for it",
        ],
        "finding": None,
        "notes": f"Candidate 54 ({REL}). JLC C4036134 extended (0603WAF4991T5E, C23046, is basic). Second source Vishay "
                 "RCS06034K99FKEA (0.25 W at 70 C, doc 20065 p.1).",
    }

    cp = m["caps"]
    c129r, c129c = cp["c17.5_h10"]["C129"], cp["c28_h10"]["C129"]
    caps = {
        "mpn": "16SVPK220M", "designators": ["C126", "C127", "C128", "C129"], "class": "SIGNAL",
        "function": "220 uF polymer bias reservoir behind the 0.68 ohm damping resistor (src - n split, ~2.0 V); candidate 54 "
                    "swap for 6SVPC220MV, same C6 can and land",
        "status": "PARTIAL",
        "datasheet": {"url": "https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2205061630_PANASONIC-16SVPK220M_C542293.pdf",
                      "revision": "Panasonic OS-CON SVPK series (LCSC copy, PDF ModDate 2022-03-09, 7 pp.)",
                      "fetched": "2026-10-18", "repo_copy": None, "sha256_prefix16": "52d07f7c41c7c080",
                      "note": f"fetch: {REL}/scripts/fetch_datasheets.py; not committed"},
        "ratings": [
            {"parameter": "Temperature rating (category)", "datasheet_limit": 125.0, "unit": "C",
             "basis": "category -55 to +125 C; endurance +125 C 1000 h at rated voltage", "source": "p.1 Specifications"},
            {"parameter": "Rated voltage", "datasheet_limit": 16.0, "unit": "V", "basis": "16SVPK220M", "source": "p.2 list"},
        ],
        "stresses": [
            {"parameter": "Local temperature, release case (c17.5_h10 @ 61 C)", "worst_case_value": round(c129r["pad_est_c"], 1),
             "unit": "C", "condition": "C129 pad-copper probe (local-ambient proxy), own ripple heat negligible, s53 82af7bd9",
             "evidence": MARG},
            {"parameter": "Local temperature, c28_h10 @ 55 C", "worst_case_value": round(c129c["pad_est_c"], 1), "unit": "C",
             "condition": "C129 pad-copper probe, c28_h10 still air bay 55 C", "evidence": MARG},
            {"parameter": "Working voltage", "worst_case_value": 2.01, "unit": "V",
             "condition": "src - n split, V_SPLIT = 1.24 x (1 + 6.2 / 10) (b3_ratings_gate V_SPLIT)", "evidence": MARG},
        ],
        "derating_rule": "Local (pad) temperature <= category temperature at the release case; c22/c28 the airflow-route gap; "
                         "voltage <= 80 % of rated.",
        "checks": [
            {"id": "temperature, release case", "rating": "Temperature rating (category)",
             "stress": "Local temperature, release case (c17.5_h10 @ 61 C)", "max_ratio": 1.0, "severity": "violation",
             "rule": f"{c129r['pad_est_c']:.1f} C <= 125 C (C129)"},
            {"id": "temperature, c28", "rating": "Temperature rating (category)", "stress": "Local temperature, c28_h10 @ 55 C",
             "max_ratio": 1.0, "severity": "gap", "rule": "airflow route (c22/c28)"},
            {"id": "voltage", "rating": "Rated voltage", "stress": "Working voltage", "max_ratio": 0.8, "severity": "violation",
             "rule": "<= 80 %"},
        ],
        "layout_guidance": [],
        "gaps": [
            "the local temperature is the B3 pad estimate (still air), not a measurement; life is outside this check",
            "ESR 22 mOhm max against SVPC's 15 (both sit behind the 0.68 ohm damping resistor); leakage 704 uA max at rated "
            "16 V after 2 min (p.2), against ~3.1 mA of split bleed current: bench-confirm the split voltage at power-up",
            "sourcing: JLC / LCSC 0 in stock on the read date; Digi-Key 1,420 (results/bom-patch.json)",
        ],
        "finding": None,
        "notes": f"Candidate 54 ({REL}). Same C6 can as SVPC (p.1 dims: D 6.3, L 5.9, W = H 6.6, C 7.3, P 2.1 mm).",
    }
    for e in (ron, bleed, caps):
        for chk in e["checks"]:
            r = next(x for x in e["ratings"] if x["parameter"] == chk["rating"])
            s = next(x for x in e["stresses"] if x["parameter"] == chk["stress"])
            chk["ratio"] = round(s["worst_case_value"] / r["datasheet_limit"], 4)
    return {"study": REL, "apply": "replace the entries keyed by the 'replaces' MPN with these (ledger.json 'entries'); "
                                   "bump the README counts; no status change (all stay PARTIAL)",
            "entries": [{"replaces": "25121WF680JT4E", "entry": ron}, {"replaces": "0603WAF4991T5E", "entry": bleed},
                        {"replaces": "6SVPC220MV", "entry": caps}]}


def main():
    m = json.loads((STUDY / "results/margins-c54.json").read_text())
    bp = bom_patch()
    (STUDY / "results/bom-patch.json").write_text(json.dumps(bp, indent=1) + "\n")
    lp = ledger_patch(m)
    errs = []
    for it in lp["entries"]:
        e = it["entry"]
        er, _, checks = ledger_gate.validate_entry(e["mpn"], e, set(e["designators"]), PS, {})
        errs += er
        it["validated"] = {"errors": er, "checks": checks}
    (STUDY / "results/ledger-patch.json").write_text(json.dumps(lp, indent=1) + "\n")
    for c in bp["changes"]:
        f, t = c["from"], c["to"]
        print(f"{f['mpn']} -> {t['mpn']} ({t['lcsc']}): JLC {t['jlc_stock']} ({t['jlc_read_utc']}), LCSC {t['lcsc_stock']}, "
              f"unit $ {t['jlc_price_usd_at_5']} / {t['jlc_price_usd_at_500']} at 5 / 500 pcs; delta "
              f"${c['delta_usd_per_board_at_500_boards']:+.3f} per board at 500 boards")
    for it in lp["entries"]:
        print(it["entry"]["mpn"], "ledger checks:", [(c["id"], c["ratio"], c["ok"]) for c in it["validated"]["checks"]],
              "errors:", it["validated"]["errors"])
    raise SystemExit(1 if errs else 0)


if __name__ == "__main__":
    main()
