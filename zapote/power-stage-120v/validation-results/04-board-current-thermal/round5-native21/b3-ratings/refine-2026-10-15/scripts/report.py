#!/usr/bin/env python3
"""Margins tables for tasks 1-3 -> results/summary.json and results/TABLES.md (generated; every number from runs/).

Configs (runs/<config>/, solve.py): A0 committed model; L* committed heat + lead path; Hdeck_nolead / HLdeck* the
corrected heat of record (as-built deck gate charge 382.6 nC) without / with the lead path; H_nolead / HL* the same with
the 740 nC allocation (upper bound); HLdsq the datasheet-Q heat (374.1 nC); corners central / hot (G low, sink at the
95 C trip) / cool (G high, R_SA sink).
Lead-temperature variants at central G come from two-point superposition in t_rise (t_shift()).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BOARD, PITCHES, RESULTS, RUNS, pinned  # noqa: E402
import evaluate as E  # noqa: E402
import sink_model  # noqa: E402
import superposition as S  # noqa: E402

CASES = {"c22_h10": 22.0, "c28_h10": 28.0}
COLS = [("lam_block", "laminate 1 mm block"), ("lam_fet_row", "laminate FET row"), ("R5_el", "R5 element"),
        ("R5_term", "R5 terminal"), ("U26", "U26 Tj"), ("U42", "U42 Tj"), ("C38", "C38 110"), ("C40", "C40 110"),
        ("gateR_el", "gate R element"), ("gateR_der", "gate R derating"), ("min_gated", "min gated"),
        ("min_gated_ext", "min gated + proposed")]


def t_shift(cfg55, cfg61, name, t_case_by_case, bay=55.0):
    """Synthetic runs with the lead tie temperature moved (same G, same heat): F(t) = F55 + (t - t55) (F55 - F61) / 6."""
    for case in CASES:
        per = {}
        for p in PITCHES:
            j55, r55 = S.load(cfg55, case, p)
            j61, r61 = S.load(cfg61, case, p)
            t55 = j55["job"]["leads"]["t_case_c"]["Q3"] - 55.0
            t = t_case_by_case[case] - bay
            c = (t - t55) / 6.0
            rise = r55 + c * (r55 - r61)
            b1, fet = S.metrics(rise, p)
            heat = {q["ref"]: q for q in json.loads(pinned(j55["job"]["heat"]).read_text())["parts"]}
            parts = []
            for a, b in zip(j55["parts"], j61["parts"]):
                q = dict(a)
                if "tj_c" in a:
                    q["tj_c"] = a["tj_c"] + c * (a["tj_c"] - b["tj_c"])
                q["pad_max_cell_c"], q["pad_mean_c"] = S.part_pad_max(rise, a["ref"], heat[a["ref"]].get("pad_numbers"), p)
                parts.append(q)
            bal = {k: j55["balance"][k] + c * (j55["balance"][k] - j61["balance"][k]) for k in ("source_w", "convection_w", "body_air_w", "lead_sink_w")}
            bal["balance_rel"] = (bal["source_w"] - bal["convection_w"] - bal["body_air_w"] - bal["lead_sink_w"]) / bal["source_w"]
            per[p] = {"peak_1mm_block": b1, "fet_row_max_c": fet, "parts": parts, "balance": bal, "board_sha256": j55["board_sha256"],
                      "leads": [{"ref": "Q*", "t_case_c": t_case_by_case[case]}], "superposition": {"t_shift_from": [cfg55, cfg61]}}
        S.write(name, case, per)
    return S.SYN / name


_B = {}


def syn_q(name, t_case_by_case, q, bay=55.0):
    """Record-model rows at another lead tie temperature, from the superposition bases (superposition.py: c28 fields
    A, P, R, t, q; validated against direct solves) at the deck heat weight q: no extra solve."""
    if not _B:
        _B.update(S.bases())
    for case, ceil in CASES.items():
        k = S.k_of(ceil)
        t = t_case_by_case[case] - bay
        S.write(name, case, {p: b.combine(k, k, 1.0, t, q)[0] for p, b in _B.items()})
    return S.SYN / name


def check_syn_q(q):
    """Control: syn_q at the central case temperature must reproduce the direct HLdeck_central_b55 solves."""
    tc = {c: sink_model.t_case(v, "central")[0]["Q3"] for c, v in CASES.items()}
    d = syn_q("chk_qdeck", tc, q)
    a, b = E.compact(E.evaluate(d, 55.0)), E.compact(E.evaluate(RUNS / "HLdeck_central_b55", 55.0))
    keys = ("lam_block", "lam_fet_row", "R5_el", "R5_term", "U26", "U42", "C38", "C40", "gateR_el", "gateR_der")
    worst = max(abs(a[c][k] - b[c][k]) for c in CASES for k in keys)
    return {"max_abs_K_on_margins_0p1K_rounded": worst, "pass": worst <= 0.1 + 1e-9,
            "note": "margins are rounded to 0.1 K by the gate; the field-level check is superposition.validate()"}


def check_t_shift():
    """Control: shifting L_central_b55 to the bay-61 tie temperature (t = T_case - 61, evaluated at bay 61 means the
    same t as cfg61) must reproduce L_central_b61's own JSON."""
    tc = {c: sink_model.t_case(v, "central")[0]["Q3"] for c, v in CASES.items()}
    d = t_shift("L_central_b55", "L_central_b61", "chk_tshift", tc, bay=61.0)
    worst = 0.0
    for case in CASES:
        for p in PITCHES:
            a = json.loads((d / f"{case}_{S.tag(p)}.json").read_text())
            b = json.loads((RUNS / "L_central_b61" / f"{case}_{S.tag(p)}.json").read_text())
            worst = max(worst, abs(a["peak_1mm_block"]["temperature_c"] - b["peak_1mm_block"]["temperature_c"]),
                        abs(a["fet_row_max_c"] - b["fet_row_max_c"]),
                        max(abs(x["pad_max_cell_c"] - y["pad_max_cell_c"]) for x, y in zip(a["parts"], b["parts"])))
    return {"max_abs_K": worst, "pass": worst < 1e-4, "note": "CG rtol 1e-10 noise"}


PKG = {"1206 (as fitted)": (0.25, 1), "2 x 1206 in parallel": (0.25, 2), "1210": (0.5, 1), "2010": (0.75, 1),
       "2512": (1.0, 1)}    # FH General Thick Film V11.0 p.2: rated W at 70 C, all on derating curve 2 (0 W at 155 C)


def gate_r_options():
    """The terminal-derating line T_term <= 155 - 85 P / (0.8 W_rated) for the turn-on gate resistors (R10/R12/R18/R20)
    on the record model, per package, at the terminal temperature the model gives for the fitted 1206 (a larger body or
    two parts spread the heat and run cooler, so these margins are conservative)."""
    out = {}
    for folder, bay in ((RUNS / "HLdeck_central_b55", 55.0), (RUNS / "HLdeck_central_b61", 61.0)):
        ev = E.evaluate(folder, bay)
        for case in CASES:
            rows = [r for r in ev["ext"][case] if "terminal derating" in r["item"] and r["item"].split(":")[0] in ("R10", "R12", "R18", "R20")]
            worst = max(rows, key=lambda r: r["est_c"])
            p = float(worst["item"].split(" at ")[1].split(" W")[0])
            out[f"{case}_b{bay:g}"] = {"ref": worst["item"].split(":")[0], "P_W": p, "T_term_est_c": worst["est_c"],
                                       "margin_k": {k: round(155.0 - 85.0 * (p / n) / (0.8 * w) - worst["est_c"], 1)
                                                    for k, (w, n) in PKG.items()}}
    return out


def row(folder, bay):
    return E.compact(E.evaluate(folder, bay))


def main():
    qd = json.loads((RESULTS / "heat-corrections.json").read_text())["q_deck_weight"]
    res = {"t_shift_control": check_t_shift(), "syn_q_control": check_syn_q(qd), "tables": {}}
    assert res["t_shift_control"]["pass"], res["t_shift_control"]
    assert res["syn_q_control"]["pass"], res["syn_q_control"]
    basisA = {c: sink_model.basis_a(v, 60e3)["T_case_at_fw_trip_C"] for c, v in CASES.items()}
    hot = {c: sink_model.t_case(v, "hot")[0]["Q3"] for c, v in CASES.items()}
    syn = {"L_basisA_b55": t_shift("L_central_b55", "L_central_b61", "L_basisA_b55", basisA),
           "L_hotsink_centralG_b55": t_shift("L_central_b55", "L_central_b61", "L_hotsink_centralG_b55", hot),
           "HL_basisA_b55": t_shift("HL_central_b55", "HL_central_b61", "HL_basisA_b55", basisA),
           "HL_hotsink_centralG_b55": t_shift("HL_central_b55", "HL_central_b61", "HL_hotsink_centralG_b55", hot),
           "HLdeck_basisA_b55": syn_q("HLdeck_basisA_b55", basisA, qd),
           "HLdeck_hotsink_centralG_b55": syn_q("HLdeck_hotsink_centralG_b55", hot, qd)}
    plan = [  # (label, folder, bay)
        ("committed model (no lead path), bay 55", RUNS / "A0_repo_committed", 55.0),
        ("committed model (no lead path), bay 61", RUNS / "A0_repo_committed", 61.0),
        ("+ lead path central, bay 55", RUNS / "L_central_b55", 55.0),
        ("+ lead path central, bay 61", RUNS / "L_central_b61", 61.0),
        ("+ lead path hot corner (G 0.020, sink 95 C), bay 55", RUNS / "L_hot_b55", 55.0),
        ("+ lead path, central G, sink at 95 C trip, bay 55", syn["L_hotsink_centralG_b55"], 55.0),
        ("+ lead path, central G, basis-A 60 kHz FET at 95 C sink, bay 55", syn["L_basisA_b55"], 55.0),
        ("+ lead path cool corner (G 0.280, R_SA sink), bay 55", RUNS / "L_cool_b55", 55.0),
        ("corrected heat of record (deck 382.6 nC) only, no lead path, bay 55", RUNS / "Hdeck_nolead", 55.0),
        ("corrected heat of record (deck 382.6 nC) only, no lead path, bay 61", RUNS / "Hdeck_nolead", 61.0),
        ("CORRECTED MODEL OF RECORD: deck heat + lead central, bay 55", RUNS / "HLdeck_central_b55", 55.0),
        ("CORRECTED MODEL OF RECORD: deck heat + lead central, bay 61", RUNS / "HLdeck_central_b61", 61.0),
        ("record model, hot corner (G 0.020, sink 95 C), bay 55", RUNS / "HLdeck_hot_b55", 55.0),
        ("record model, central G, sink at 95 C trip, bay 55", syn["HLdeck_hotsink_centralG_b55"], 55.0),
        ("record model, central G, basis-A 60 kHz FET at 95 C sink, bay 55", syn["HLdeck_basisA_b55"], 55.0),
        ("record model, cool corner (G 0.280, R_SA sink), bay 55", RUNS / "HLdeck_cool_b55", 55.0),
        ("datasheet-Q heat (374.1 nC) + lead central, bay 55", RUNS / "HLdsq_central_b55", 55.0),
        ("740 nC allocation heat (upper bound) only, no lead path, bay 55", RUNS / "H_nolead", 55.0),
        ("740 nC allocation heat (upper bound) + lead central, bay 55", RUNS / "HL_central_b55", 55.0),
        ("740 nC allocation heat (upper bound) + lead central, bay 61", RUNS / "HL_central_b61", 61.0),
        ("740 nC allocation heat, hot corner (G 0.020, sink 95 C), bay 55", RUNS / "HL_hot_b55", 55.0),
        ("740 nC allocation heat, central G, sink at 95 C trip, bay 55", syn["HL_hotsink_centralG_b55"], 55.0),
        ("740 nC allocation heat, central G, basis-A 60 kHz FET, bay 55", syn["HL_basisA_b55"], 55.0),
    ]
    for label, folder, bay in plan:
        res["tables"][label] = row(folder, bay)
    # which hot spots the lead path moves (central, bay 55; estimates incl. mesh allowance)
    a0 = E.evaluate(RUNS / "A0_repo_committed", 55.0)
    l1 = E.evaluate(RUNS / "L_central_b55", 55.0)
    moves = {}
    for case in CASES:
        ra = {r["item"].split(" at ")[0]: r for r in a0["gate"]["cases"][case] + a0["ext"][case]}
        rb = {r["item"].split(" at ")[0]: r for r in l1["gate"]["cases"][case] + l1["ext"][case]}
        moves[case] = sorted(({"item": k, "est_no_lead_c": ra[k]["est_c"], "est_lead_c": rb[k]["est_c"],
                               "delta_k": round(rb[k]["est_c"] - ra[k]["est_c"], 1)} for k in ra if k in rb),
                             key=lambda r: r["delta_k"])
    res["lead_moves_b55"] = moves
    res["gateR_package_options"] = gate_r_options()
    res["sink_model"] = json.loads((RESULTS / "sink_model.json").read_text())["cases"]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "summary.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    lines = [f"# thermal-refine margins, board {BOARD} (generated by scripts/report.py; K, negative = over the limit)", ""]
    for case in CASES:
        lines += [f"## {case}", "", "| configuration | " + " | ".join(c[1] for c in COLS) + " | lead W to sink |",
                  "|---" * (len(COLS) + 2) + "|"]
        for label, t in res["tables"].items():
            v = t[case]
            lines.append(f"| {label} | " + " | ".join("-" if v[k] is None else f"{v[k]:+.1f}" for k, _ in COLS)
                         + f" | {0 if v['lead_sink_w'] is None else v['lead_sink_w']:.2f} |")
        lines += ["", f"Hot spots moved by the lead path (central, bay 55), {case}:", "",
                  "| item | no lead C | lead C | delta K |", "|---|---|---|---|"]
        for m in moves[case][:14]:
            lines.append(f"| {m['item']} | {m['est_no_lead_c']} | {m['est_lead_c']} | {m['delta_k']:+.1f} |")
        lines.append("")
    lines += ["## Gate-resistor package options (record model; derating line at the fitted 1206's terminal temperature)", "",
              "| case | ref | P W | T_term C | " + " | ".join(PKG) + " |", "|---" * (len(PKG) + 4) + "|"]
    for k, v in res["gateR_package_options"].items():
        lines.append(f"| {k} | {v['ref']} | {v['P_W']:.3f} | {v['T_term_est_c']} | " + " | ".join(f"{v['margin_k'][x]:+.1f}" for x in PKG) + " |")
    lines.append("")
    (RESULTS / "TABLES.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
