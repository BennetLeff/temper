#!/usr/bin/env python3
"""Margins for a folder of solves: the committed gate (b3-ratings/b3_ratings_gate.py, imported read-only) plus the
rows this study proposes to gate.

    evaluate(folder, bay, cases) -> {"gate": <committed gate run()>, "ext": {case: [rows]}, "summary": {...}}

Proposed gated rows (task 3; limits re-read on the datasheets in dl/):
  * 1206 gate resistors, MPNs verified on the s35 BOM (bom-jlcpcb.csv):
      R10/R12/R18/R20 FH RS-06L8R20FT (General Thick Film Chip, V11.0 2026-04-28, p.2: 1206 rated 1/4 W at 70 C, derating
      curve 2 to 0 W at 155 C, operating range -55..155 C);
      R53/R54/R57/R58 UniRoyal 1206W4F100KT5E (Thick Film Chip Resistors V.3 2019-02-12, p.4/9 1206 1/4 W at 70 C,
      p.5/9 operating temperature -55..155 C, Figure 1 derating 70 -> 155 C).
    element (model junction node, 33 K/W derived path) <= 155 C; and the derating line taken on the terminal (pad max
    cell): T_term <= 155 - 85 x P / (0.8 x 0.25 W) - the same 20 % power-margin rule the gate applies to R5 (G6).
  * HF film caps C38-C41 TDK B32652A0104K000 (B3265* June 2026: p.2 / p.35 Top,max +110 C, Top = TA + dT (p.64, p.78)):
    body node <= 110 C. The bank caps (board share only) stay advisory.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RATINGS  # noqa: E402

_spec = importlib.util.spec_from_file_location("b3_ratings_gate", RATINGS / "b3_ratings_gate.py")
G = importlib.util.module_from_spec(_spec)
sys.dont_write_bytecode = True
_spec.loader.exec_module(G)

GATE_R = {"R10", "R12", "R18", "R20", "R53", "R54", "R57", "R58"}
HF_FILM = {"C38", "C39", "C40", "C41"}
R1206_W, R1206_TMAX, R1206_KNEE = 0.25, 155.0, 70.0


def ext_rows(r25, r05, bay):
    p05 = {p["ref"]: p for p in r05["parts"]}
    rows = []
    for p in r25["parts"]:
        q = p05.get(p["ref"])
        if q is None or "tj_c" not in p:
            continue
        if p["ref"] in GATE_R:
            rows.append(dict(item=f"{p['ref']}: 1206 element 155 C (FH V11.0 p.2 / UniRoyal V.3 p.5/9)", limit_c=R1206_TMAX,
                             est_c=G.est(p["tj_c"], q["tj_c"], bay)))
            lim = R1206_TMAX - (R1206_TMAX - R1206_KNEE) * p["watts_into_model"] / (0.8 * R1206_W)
            rows.append(dict(item=f"{p['ref']}: 1206 terminal derating at {p['watts_into_model']:.3f} W (20 % margin)",
                             limit_c=lim, est_c=G.est(p["pad_max_cell_c"], q["pad_max_cell_c"], bay)))
        elif p["ref"] in HF_FILM:
            rows.append(dict(item=f"{p['ref']}: MKP Top,max 110 C (TDK B3265* p.35)", limit_c=110.0,
                             est_c=G.est(p["tj_c"], q["tj_c"], bay)))
    for r in rows:
        r["gated"] = "proposed"
        r["margin_k"] = round(r["limit_c"] - r["est_c"], 1)
        r["est_c"], r["limit_c"] = round(r["est_c"], 1), round(r["limit_c"], 1)
    return sorted(rows, key=lambda r: r["margin_k"])


def pick(rows, prefix):
    hit = [r for r in rows if r["item"].startswith(prefix)]
    return min(hit, key=lambda r: r["margin_k"]) if hit else None


def evaluate(folder: Path, bay: float, cases=("c22_h10", "c28_h10")):
    folder = Path(folder)
    gate = G.run(folder, list(cases), bay)
    ext, summ = {}, {}
    for c in cases:
        r25 = json.loads((folder / f"{c}_p0p25.json").read_text())
        r05 = json.loads((folder / f"{c}_p0p5.json").read_text())
        ext[c] = ext_rows(r25, r05, bay)
        rows = gate["cases"][c]
        gated_parts = [r for r in rows if r["gated"] and not r["item"].startswith("laminate")]
        s = {"laminate_block": pick(rows, "laminate: 1 mm-block"), "laminate_fet_row": pick(rows, "laminate: FET-row"),
             "worst_gated_part": min(gated_parts, key=lambda r: r["margin_k"]) if gated_parts else None,
             "R5_element": pick(rows, "R5: element"), "R5_terminal": pick(rows, "R5: terminal"),
             "U26": pick(rows, "U26"), "U42": pick(rows, "U42"), "U41": pick(rows, "U41"),
             "C40": pick(ext[c], "C40"), "C38": pick(ext[c], "C38"),
             "gateR_element": min((r for r in ext[c] if "element" in r["item"]), key=lambda r: r["margin_k"], default=None),
             "gateR_derating": min((r for r in ext[c] if "derating" in r["item"]), key=lambda r: r["margin_k"], default=None),
             "block_at": r25["peak_1mm_block"], "leads": r25.get("leads"),
             "lead_sink_w": r25["balance"].get("lead_sink_w"), "balance_rel_max": max(abs(r25["balance"]["balance_rel"]), abs(r05["balance"]["balance_rel"]))}
        s["min_gated_committed"] = min(r["margin_k"] for r in rows if r["gated"])
        s["min_gated_with_proposed"] = min([s["min_gated_committed"]] + [r["margin_k"] for r in ext[c]])
        summ[c] = s
    return {"folder": str(folder), "bay_c": bay, "gate": gate, "ext": ext, "summary": summ}


def compact(ev):
    """One line per case: the numbers the report quotes."""
    out = {}
    for c, s in ev["summary"].items():
        f = lambda r: None if r is None else r["margin_k"]  # noqa: E731
        out[c] = {"lam_block": f(s["laminate_block"]), "lam_fet_row": f(s["laminate_fet_row"]),
                  "block_est_c": s["laminate_block"]["est_c"], "fet_row_est_c": s["laminate_fet_row"]["est_c"],
                  "worst_part": None if s["worst_gated_part"] is None else (s["worst_gated_part"]["item"], s["worst_gated_part"]["margin_k"]),
                  "R5_el": f(s["R5_element"]), "R5_term": f(s["R5_terminal"]), "U26": f(s["U26"]), "U42": f(s["U42"]),
                  "C40": f(s["C40"]), "C38": f(s["C38"]), "gateR_el": f(s["gateR_element"]),
                  "gateR_der": f(s["gateR_derating"]), "gateR_der_item": None if s["gateR_derating"] is None else s["gateR_derating"]["item"],
                  "min_gated": s["min_gated_committed"], "min_gated_ext": s["min_gated_with_proposed"],
                  "lead_sink_w": s["lead_sink_w"], "balance_rel_max": s["balance_rel_max"]}
    return out


if __name__ == "__main__":
    ev = evaluate(Path(sys.argv[1]), float(sys.argv[2]) if len(sys.argv) > 2 else 55.0)
    print(json.dumps(compact(ev), indent=1))
