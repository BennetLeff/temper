#!/usr/bin/env python3
"""B3 ratings gate: margin of the board's hot spots to the laminate's UL temperature and to each hot part's datasheet
limit, at the declared operating basis. Proposed home: validation-results/04-board-current-thermal/round5-native21/
b3-ratings/ (thermal-ratings audit, 2026-10-15).

    python3 b3_ratings_gate.py --runs DIR [--out margins.json] [--bay-c 55] [--cases c22_h10,c28_h10]

DIR holds body-level B3 solves (b3-convergence/body_runs.run_case JSON, fill-fraction copper + package networks) named
<case>_p0p25.json and <case>_p0p5.json. The legacy thermal.py single-cell peak is NOT an input: it is a point-deposit
artefact that moves 50-80 K with the mesh (b3-convergence README section 1).

Estimate per quantity: Q(0.25) + K_MESH * |Q(0.25) - Q(0.5)| + (bay - 50 C). K_MESH = 3 reproduces the stage-19b
0.0625-0.125 mm window increments for the board block peak within ~1 K (it bounds the remaining error for observed
orders p >= 0.4); R5's element converges more slowly (p ~ 0.2) and is under-corrected by ~4 K - see the audit's
gate_control G6 table.

Basis (decided in the audit; change only with evidence):
  * cases c22_h10 (default 22 A ceiling) and c28_h10 (28 A Kconfig ceiling): h 10 W/m2K is still air - the enclosure's
    bay model has no through-flow and D-18 ducts the blower through the sink only. A forced-air case counts only once
    an enclosure record gives the board-face airflow.
  * bay air 55 C: enclosure R33 study 14, expected value at a 40 C kitchen (61 C worst with B3 heat only).
Limits (sources re-read 2026-10-15; see the audit's ratings.py for page-level quotes):
  laminate 130 C   Kingboard KB-616(X) (KB-6164 / KB-6064) UL QMTS2 E123995 (2026-02-20): multilayer Max Oper Temp 130,
                   RTI elec 130 - applied to the 1 mm-block copper peak and the FET-row copper
  RECOM R24C2T25/R junction 150 C (Rev. 1-2024 p.2; OTP 160 +/- 10 C p.8)
  TPS7A4700        junction 125 C (SBVS204G p.4, p.6)
  CSS2H-2512R      element 170 C (REV 06/17/20 p.1); terminal <= 170 - 100 * P / (0.8 * 5 W) (p.3 curve, G6 20 % rule)
  advisory (limit known, package path assumed): TDK MKP Top,max 110 C (June 2026 p.35), B82726 125 C (p.4),
                   1206 thick film 155 C (unverified)

Exit 0 if every gated margin >= 0, else 1. Advisory rows never fail the gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MOT_C = 130.0
TAMB_MODEL_C = 50.0
K_MESH = 3.0
R5_RATED_W = 5.0
GATED = {"recom": ("Tj abs max (RECOM Rev.1-2024 p.2)", 150.0), "rgw": ("TJ max (TI SBVS204G p.4)", 125.0),
         "css2h": ("element max (Bourns CSS2H p.1)", 170.0)}
ADVISORY = {"film_radial": ("MKP Top,max (TDK June 2026 p.35)", 110.0), "film_4pin": ("MKP Top,max", 110.0),
            "choke": ("B82726 climatic upper (TDK p.4)", 125.0), "chip1206": ("1206 thick film (unverified)", 155.0)}


def est(v25, v05, bay):
    return v25 + K_MESH * abs(v25 - v05) + (bay - TAMB_MODEL_C)


def evaluate(r25: dict, r05: dict, bay: float):
    p05 = {p["ref"]: p for p in r05["parts"]}
    rows = [dict(item="laminate: 1 mm-block copper peak", gated=True, limit_c=MOT_C,
                 est_c=est(r25["peak_1mm_block"]["temperature_c"], r05["peak_1mm_block"]["temperature_c"], bay),
                 at=[r25["peak_1mm_block"]["x_mm"], r25["peak_1mm_block"]["y_mm"], r25["peak_1mm_block"]["layer"]])]
    if r25.get("fet_row_max_c") is not None and r05.get("fet_row_max_c") is not None:
        rows.append(dict(item="laminate: FET-row copper", gated=True, limit_c=MOT_C,
                         est_c=est(r25["fet_row_max_c"], r05["fet_row_max_c"], bay)))
    for p in r25["parts"]:
        spec, q = p.get("spec"), p05.get(p["ref"])
        if spec is None or q is None:
            continue
        if spec in GATED:
            basis, lim = GATED[spec]
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=True, limit_c=lim, est_c=est(p["tj_c"], q["tj_c"], bay)))
            if spec == "css2h":
                lim_t = 170.0 - 100.0 * p["watts_into_model"] / (0.8 * R5_RATED_W)
                rows.append(dict(item=f"{p['ref']}: terminal derating at {p['watts_into_model']:.3f} W (20 % margin)", gated=True,
                                 limit_c=lim_t, est_c=est(p["pad_max_cell_c"], q["pad_max_cell_c"], bay)))
        elif spec in ADVISORY:
            basis, lim = ADVISORY[spec]
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=False, limit_c=lim, est_c=est(p["tj_c"], q["tj_c"], bay)))
    for r in rows:
        r["margin_k"] = round(r["limit_c"] - r["est_c"], 1)
        r["est_c"], r["limit_c"] = round(r["est_c"], 1), round(r["limit_c"], 1)
    return rows


def run(runs: Path, cases, bay: float):
    out = {"basis": {"cases": cases, "bay_c": bay, "k_mesh": K_MESH, "mot_c": MOT_C}, "cases": {}}
    lam, part, adv = [], [], []
    for c in cases:
        f25, f05 = runs / f"{c}_p0p25.json", runs / f"{c}_p0p5.json"
        if not (f25.exists() and f05.exists()):
            raise SystemExit(f"b3_ratings_gate: missing {f25.name} or {f05.name} in {runs}")
        r25, r05 = json.loads(f25.read_text()), json.loads(f05.read_text())
        shas = {r25.get("board_sha256"), r05.get("board_sha256")}
        if len(shas) != 1:
            raise SystemExit(f"b3_ratings_gate: {c} meshes come from different boards {shas}")
        out.setdefault("board_sha256", {})[c] = shas.pop()
        rows = evaluate(r25, r05, bay)
        out["cases"][c] = sorted(rows, key=lambda r: r["margin_k"])
        lam += [r["margin_k"] for r in rows if r["item"].startswith("laminate")]
        part += [r["margin_k"] for r in rows if r["gated"] and not r["item"].startswith("laminate")]
        adv += [r["margin_k"] for r in rows if not r["gated"]]
    worst = min((r for rows in out["cases"].values() for r in rows if r["gated"]), key=lambda r: r["margin_k"])
    out["metrics"] = {"b3_laminate_margin_K": min(lam), "b3_rated_part_margin_K": min(part),
                      "b3_advisory_margin_K": min(adv) if adv else None, "worst_gated": worst["item"]}
    out["pass"] = min(lam) >= 0 and min(part) >= 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out")
    ap.add_argument("--bay-c", type=float, default=55.0)
    ap.add_argument("--cases", default="c22_h10,c28_h10")
    a = ap.parse_args()
    res = run(Path(a.runs), a.cases.split(","), a.bay_c)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    m = res["metrics"]
    print(f"b3 ratings gate ({a.cases}, bay {a.bay_c} C): laminate margin {m['b3_laminate_margin_K']} K, rated-part "
          f"margin {m['b3_rated_part_margin_K']} K, advisory {m['b3_advisory_margin_K']} K; worst gated: {m['worst_gated']} "
          f"-> {'PASS' if res['pass'] else 'FAIL'}")
    raise SystemExit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
