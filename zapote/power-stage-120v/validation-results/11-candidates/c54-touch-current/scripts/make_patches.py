#!/usr/bin/env python3
"""c54: write the proposed patches (nothing in the repo outside this folder is edited).

  results/bom-patch.json   decision (no BOM change), the fitted part's stock re-read, the rejected alternates
  results/ledger.patch     unified diff for native-21/verification/datasheet-ledger/ledger.json (DE1E3RA222MJ4BH01F)
  results/open-items.patch unified diff for OPEN-ITEMS.md row S1
Reads results/summary.json (leakage_c54.py), results/jlc-raw/*.json (jlc_fetch.py) and
results/octopart-2026-10-18.json (octopart_parse.py). Apply from the repo root with `git apply <patch>`.

Run: python3 -I scripts/make_patches.py
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results"
PS = HERE.parents[3]
REPO_PREFIX = "zapote/power-stage-120v/"
C54 = "validation-results/11-candidates/c54-touch-current"
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
OPEN = PS / "OPEN-ITEMS.md"

S = json.loads((RES / "summary.json").read_text())
OCT = json.loads((RES / "octopart-2026-10-18.json").read_text())
O = {o["option"][:2]: o for o in S["options"]}
DESIGN = O["O0"]["touch_60Hz_mA"]
HFW = O["O0"]["hf_touch_estimate"]


def jlc(code):
    d = json.loads((RES / f"jlc-raw/detail_{code}.json").read_text())
    x = d["data"]
    return {"lcsc": code, "mpn": x["componentModelEn"], "jlc_library": x.get("componentLibraryType"),
            "jlc_stock": x.get("stockCount"), "read_utc": d["_fetched_utc"],
            "jlc_usd_ladder": [[p["startNumber"], p["productPrice"]] for p in (x.get("prices") or [])][:6]}


def dist(mpn):
    r = OCT[mpn]
    return {"octopart_read_utc": r["fetched_utc"], "url": r["url"],
            "authorised_offers": [{"seller": o["seller"], "stock": o["stock"], "moq": o["moq"],
                                   "offer_updated": o["updated"], "usd_ladder": o["usd_ladder"][:4]}
                                  for o in r["offers"] if o["authorized"] and o["stock"]]}


def emi(tag):
    return S["emi"][tag]


def bom_patch():
    ds = ("Murata Reference Specification Type RA, EGD08G, as of Jun. 2023 (LCSC copy, sha256 c959488a2523ac21..., the "
          "same file for the 1.0 / 1.5 / 2.2 nF H01F parts): p.6 approvals UL/cUL UL60384-14 / CSA E60384-14 file E37921, "
          "ENEC (VDE) 40043033, CQC16001138225, Y1 AC400 V / X1 AC440 V; p.9 part list; p.11 item 7 char. E +20/-55 % "
          "(-25..85 C)")
    return {
        "candidate": "c54-touch-current", "date": "2026-10-18",
        "decision": "NO BOM CHANGE. C3 / C4 stay Murata DE1E3RA222MJ4BH01F (2.2 nF Y1). Reducing them breaks the "
                    "conducted-EMI rule (>= 6 dB in every sensitivity) and does not lower the estimated touch current "
                    "the laboratory reads (the switching-frequency term rises as Y falls). README section 4.",
        "lines": [{
            "designators": ["C3", "C4"], "action": "keep", "mpn": "DE1E3RA222MJ4BH01F", "manufacturer": "Murata",
            "value": "2200 pF +/-20 %, char. E, D 9.0 / T 4.0 / F 10.0 / d 0.6 mm, J4 (p.9)",
            "datasheet": ds, **jlc("C7170908"), **dist("DE1E3RA222MJ4BH01F"),
            "touch_60Hz_mA": DESIGN, "emi_board_of_record_dB": emi("bor-Y2.2")}],
        "rejected_alternates": [
            {"mpn": "DE1E3RA152MJ4BH01F", "value": "1500 pF +/-20 %, char. E, D 8.0 / T 4.0 / F 10.0 / d 0.6, J4 (p.9)",
             "same_footprint": True, "approvals": "as the fitted part (p.6, same specification)", **jlc("C6601328"),
             **dist("DE1E3RA152MJ4BH01F"), "touch_60Hz_mA": O["O1"]["touch_60Hz_mA"],
             "emi_board_of_record_dB": emi("bor-Y1.5"), "emi_production_L1_2203_dB": emi("prod-Y1.5"),
             "hf_touch_estimate": O["O1"]["hf_touch_estimate"],
             "why_rejected": "EMI sensitivity minimum 3.62 dB (coil + board 51 pF, CM 180 kHz) < 6 dB: INCONCLUSIVE; "
                             "production L1 gives 4.86 dB. Lab-reading estimate unchanged (0.302 vs 0.306 mA worst)."},
            {"mpn": "DE1E3RA102MJ4BH01F", "value": "1000 pF +/-20 %, char. E, D 7.0 / T 4.0 / F 10.0 / d 0.6, J4 (p.9)",
             "same_footprint": True, "approvals": "as the fitted part (p.6, same specification)", **jlc("C6601326"),
             **dist("DE1E3RA102MJ4BH01F"), "touch_60Hz_mA": O["O2"]["touch_60Hz_mA"],
             "emi_board_of_record_dB": emi("bor-Y1.0"), "hf_touch_estimate": O["O2"]["hf_touch_estimate"],
             "why_rejected": "EMI nominal 4.24 dB, sensitivity minimum -0.30 dB (chokes -30 %): INCONCLUSIVE, near FAIL."},
            {"mpn": "DE1E3RA102MA4BP01F", "note": "1.0 nF A4 long-lead P01F (Y1 300 V): the only 1.0 nF code JLC stocks",
             **jlc("C6224759"), **dist("DE1E3RA102MA4BP01F"), "why_rejected": "as DE1E3RA102MJ4BH01F (EMI)"},
            {"option": "delete C4 (single Y on L)", "touch_60Hz_mA": O["O3"]["touch_60Hz_mA"],
             "why_rejected": "UL tests both polarities; the worst polarity still sees C3, so the touch current is "
                             "unchanged (0.2412 mA) while the CM filter loses its balance."},
        ],
        "other_stock_reads": {k: jlc(c) for k, c in (("DE1E3RA152MA4BP01F", "C22264996"),
                                                      ("DE1E3RA152MJ4BP01F", "C21790117"),
                                                      ("DE1E3RA152MN4AN01F", "C3287169"))},
    }


def ledger_patch():
    src = LEDGER.read_text(encoding="utf-8")
    d = json.loads(src)
    assert json.dumps(d, indent=1, ensure_ascii=True) + "\n" == src, "ledger.json no longer round-trips"
    e = d["entries"]["DE1E3RA222MJ4BH01F"]
    lim_basis = ("UL: 0.5 mA for grounded (3-wire) portable cord-connected appliances, open ground, both polarities "
                 "(IAEI 'UL Question Corner: Leakage current', Feb 2019; the same wording in UL 982 sec. 23 as quoted by "
                 "Chroma AN 19071; AAFES TM H-13). Applies through UL 1026 (portable household cooking appliances; scope "
                 "1.1 read on shopulstandards.com); UL 858 covers floor / cabinet / wall / counter-MOUNTED equipment "
                 "(scope 1.1 read) and has its own sec. 55 test for cord-connected 120 V <= 1.75 kW units (limit not "
                 "read; 0.75 mA if the unit is classed stationary). UL 1026 clause text not read: confidence in the "
                 "value high, in the clause and classification medium. c54 README section 1.")
    for r in e["ratings"]:
        if r["parameter"].startswith("Touch-current budget"):
            r["basis"] = "50 % of the 0.5 mA UL grounded-portable limit (project rule, F5); see the limit row for the basis"
            r["source"] = f"{C54}/README.md"
    e["ratings"].append({"parameter": "Touch-current limit, grounded portable appliance (requirement, not a datasheet limit)",
                         "datasheet_limit": 0.5, "unit": "mA", "basis": lim_basis, "source": f"{C54}/README.md"})
    for s in e["stresses"]:
        if s["parameter"] == "Touch current PE open, 132 V":
            s["condition"] += ("; c54 (2026-10-18): stacked bounds (Y +20 % at 20 C, 132 V, MPM datasheet max x1.2); "
                               "C3/C4 cannot be reduced: 1.5 nF gives EMI sensitivity min 3.62 dB, 1.0 nF -0.30 dB")
            s["evidence"] = list(s["evidence"]) + [f"{C54}/results/summary.json"]
    hf_par = "Touch current incl. switching-frequency estimate, UL meter, worst corner"
    e["stresses"].append({
        "parameter": hf_par, "worst_case_value": round(HFW["lab_reading_estimate_worst_mA"], 4), "unit": "mA",
        "condition": (f"60 Hz DESIGN {DESIGN:.4f} mA (+) HF {HFW['UL_meter_worst_mA']:.4f} mA in quadrature; HF = the "
                      "co-design hf_touch.py estimator on the current s19b model, board of record (L1 2243, module DM "
                      f"100 uH), 1500 ohm || 0.15 uF meter, line-crest sources, worst corner '{HFW['UL_meter_worst_corner']}'; "
                      f"nominal {HFW['lab_reading_estimate_nominal_mA']:.4f} mA. An estimate, not a measurement"),
        "evidence": [f"{C54}/results/summary.json", f"{C54}/results/hf_touch.json"]})
    lim = 0.5
    e["checks"].append({"id": "touch total", "rating": "Touch-current limit, grounded portable appliance (requirement, "
                        "not a datasheet limit)", "stress": hf_par, "max_ratio": 0.75, "severity": "gap",
                        "rule": f"{HFW['lab_reading_estimate_worst_mA']:.3f} <= 0.375 mA (75 % of 0.5 mA)",
                        "ratio": round(HFW["lab_reading_estimate_worst_mA"] / lim, 4)})
    e["gaps"][0] = ("certifier: governing standard / clause (UL 1026 grounded portable 0.5 mA expected; UL 858 sec. 55 or "
                    "a stationary class would give 0.75 mA), test voltage and meter network are unconfirmed; bench: the "
                    "open-PE touch current with the 1500 ohm || 0.15 uF meter at 132 V, both polarities, includes the "
                    "35-60 kHz term (c54 estimate 0.06 nominal / 0.19 mA worst corner, crest); owner: the 60 Hz pass "
                    "(8.8 uA) depends on the off-board D-22 module Y removal and PS3 = MPM-65-15ST and fails with "
                    "+0.15 nF Y per line; C3/C4 cannot be reduced (c54).")
    e["gaps"].append("datasheet: the +20 % tolerance is at 20 C; char. E allows +20/-55 % over -25..85 C (p.11 item 7) "
                     "with no curve, so a cold capacitor can exceed the modelled 2.64 nF (bound 1.44 x 2.2 nF: 0.2675 mA "
                     "60 Hz, 53.5 % of 0.5 mA).")
    e["notes"] += (" C54 (2026-10-18, validation-results/11-candidates/c54-touch-current/README.md): kept at 2.2 nF; the "
                   "1.0 / 1.5 nF H01F codes (same specification and approvals) fail the EMI rule on the board of record.")
    new = json.dumps(d, indent=1, ensure_ascii=True) + "\n"
    rel = REPO_PREFIX + str(LEDGER.relative_to(PS))
    diff = difflib.unified_diff(src.splitlines(keepends=True), new.splitlines(keepends=True),
                                fromfile="a/" + rel, tofile="b/" + rel, n=3)
    (RES / "ledger.patch").write_text("".join(diff))
    (RES / "ledger-patched.json").write_text(new)  # for gate.py --ledger (verification only)


def open_items_patch():
    src = OPEN.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    idx = [i for i, l in enumerate(lines) if l.startswith("| S1 |")]
    assert len(idx) == 1, idx
    lines2 = list(lines)
    lines2[idx[0]] = (
        "| S1 | Touch leakage: was 0.974 mA. **Built in s38 (DECISIONS 50):** 0.2412 mA DESIGN (stacked bounds: Y +20 %, "
        "132 V, MPM datasheet max ×1.2; budget 0.25 mA, margin 8.8 µA) with the off-board D-22 module Y removed + SCF31X "
        "choke and PS3 → MPM-65-15ST; EMI 11.14 / 6.95 dB on the board of record (production L1 12.37 / 8.19). **c54 (2026-10-18):** the governing limit is 0.5 mA (UL grounded portable, via "
        "UL 1026; value high confidence, clause unread; 0.75 mA if classed stationary / UL 858 §55), so the margin to the "
        "limit is 0.259 mA (52 %). C3/C4 stay 2.2 nF: 1.5 nF gives EMI sensitivity min 3.62 dB (INCONCLUSIVE), 1.0 nF "
        "−0.30 dB, and the 35–60 kHz touch estimate rises as Y falls. HF-inclusive estimate (UL meter, crest, worst corner "
        "chokes −30 %) 0.306 mA = 61 % of 0.5 mA, against a new 0.375 mA (75 %) check | `c23-supply-topology/README.md`; "
        "co-design study; `11-candidates/c54-touch-current/` | Controller (J13 merge, PS3); D-22 module "
        "(`c23-supply-topology/MODULE-REQUEST.md`); certifier (standard / clause, portable vs stationary, meter, MPM "
        "approvals: IEC 60601-1 / 60335-1, no UL file) | Passes on the model (60 Hz row and HF-inclusive check) | Bench "
        "first article: open-PE touch current with the 1500 Ω ∥ 0.15 µF meter at 132 V, both polarities (≤ 0.25 mA "
        "expected, ≤ 0.375 mA release); measured supply leakage (F5 Test B); SCF31X DM leakage; MEAN WELL: MPM touch-"
        "current test frequency (60 Hz → 0.2232 mA). Robust variant (L1 → SCF31X) needs an L1-slot re-layout |\n")
    rel = REPO_PREFIX + "OPEN-ITEMS.md"
    diff = difflib.unified_diff(lines, lines2, fromfile="a/" + rel, tofile="b/" + rel, n=1)
    (RES / "open-items.patch").write_text("".join(diff))


def main() -> int:
    (RES / "bom-patch.json").write_text(json.dumps(bom_patch(), indent=1, ensure_ascii=False) + "\n")
    ledger_patch()
    open_items_patch()
    print("wrote bom-patch.json, ledger.patch (+ ledger-patched.json), open-items.patch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
