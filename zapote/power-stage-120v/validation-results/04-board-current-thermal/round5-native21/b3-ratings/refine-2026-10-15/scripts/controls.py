#!/usr/bin/env python3
"""Run controls for the lead-path model (exit 1 on any failure) -> results/controls.json

  K1  the repo model on this machine reproduces the committed margins.json at the board's pin (b3-ratings/margins.json) row for row
  K2  the patched model with the lead conductance set to 0 reproduces K1's solves (every part Tj, pad, block peak and
      FET-row value within 1e-6 K) and therefore the committed margins exactly
  K3  energy: every solve closes source = convection + body air + lead-to-sink within 1e-6 (relative); in lead runs
      the receipt's lead_sink_w equals the sum of the per-lead g (pad mean - T_case) rows
  K4  analytic: a uniform disc pad on an infinite fin plate tied to a fixed temperature T_s through g, no heat:
      disc-mean rise = T_s g R_sp / (1 + g R_sp), R_sp = the exact (Bessel) disc-mean rise per watt of a uniform flux
      (thermal_body.analytic_disc's formula); within 3 % (the committed C3 tolerance)
  K5  the gate's own controls are untouched: margins in K1 come from the committed b3_ratings_gate.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MOD_CONV, RATINGS, RESULTS, RUNS  # noqa: E402
import evaluate as E  # noqa: E402

sys.path.insert(0, str(MOD_CONV))
import thermal_body as tb  # noqa: E402


def k1():
    ev = E.evaluate(RUNS / "A0_repo_committed", 55.0)
    ref = json.loads((RATINGS / "margins.json").read_text())
    bad = []
    for c, rows in ref["cases"].items():
        mine = {r["item"]: r for r in ev["gate"]["cases"][c]}
        for r in rows:
            m = mine.get(r["item"])
            if m is None or m["margin_k"] != r["margin_k"] or abs(m["est_c"] - r["est_c"]) > 0.05:
                bad.append((c, r["item"], r["margin_k"], None if m is None else m["margin_k"]))
    same_metrics = ev["gate"]["metrics"] == ref["metrics"]
    return {"pass": not bad and same_metrics, "rows_compared": sum(len(v) for v in ref["cases"].values()),
            "mismatches": bad, "metrics": ev["gate"]["metrics"], "committed_metrics": ref["metrics"]}


def k2():
    worst = 0.0
    for f in sorted((RUNS / "A0_repo_committed").glob("*.json")):
        a = json.loads(f.read_text())
        b = json.loads((RUNS / "A1_mod_g0" / f.name).read_text())
        d = [abs(a["peak_1mm_block"]["temperature_c"] - b["peak_1mm_block"]["temperature_c"]),
             abs(a["fet_row_max_c"] - b["fet_row_max_c"]), abs(a["peak"]["temperature_c"] - b["peak"]["temperature_c"])]
        for x, y in zip(a["parts"], b["parts"]):
            assert x["ref"] == y["ref"]
            for k in ("tj_c", "pad_max_cell_c", "pad_mean_c"):
                if k in x:
                    d.append(abs(x[k] - y[k]))
        worst = max(worst, max(d))
    m0 = E.evaluate(RUNS / "A1_mod_g0", 55.0)["gate"]
    m1 = E.evaluate(RUNS / "A0_repo_committed", 55.0)["gate"]
    return {"pass": worst < 1e-6 and m0["cases"] == m1["cases"], "max_abs_diff_K": worst}


def k3():
    worst, bad, n = 0.0, [], 0
    for f in sorted(RUNS.glob("*/*.json")):
        if f.parent.name in ("heat", "cache"):
            continue
        r = json.loads(f.read_text())
        if "balance" not in r:
            continue
        n += 1
        b = r["balance"]
        worst = max(worst, abs(b["balance_rel"]))
        if "leads" in r:
            s = sum(x["w_to_sink"] for x in r["leads"])
            if abs(s - b["lead_sink_w"]) > 1e-6 * max(1.0, abs(s)):
                bad.append((str(f), s, b["lead_sink_w"]))
            closed = b["source_w"] - b["convection_w"] - b["body_air_w"] - b["lead_sink_w"]
            if abs(closed) > 1e-6 * b["source_w"]:
                bad.append((str(f), "closure", closed))
    return {"pass": worst < 1e-6 and not bad, "solves": n, "worst_balance_rel": worst, "failures": bad}


def k4(pitch_mm=0.25, a_mm=3.0, half_mm=45.0, h=250.0, t_um=70.0, g=0.5, t_s=40.0):
    k, t = tb.K_CU, t_um * 1e-6
    m = math.sqrt(2 * h / (k * t))
    a = a_mm * 1e-3
    q = 1.0 / (math.pi * a * a)
    r_sp = q / (2 * h) * (1 - 2 * tb.bessel_k1(m * a) * tb.bessel_i1(m * a))     # disc-mean rise per W, uniform flux
    exact = t_s * g * r_sp / (1 + g * r_sp)
    n = round(2 * half_mm / pitch_mm)
    board = np.ones((n, n), bool)
    poly = tb.Point_buffer(half_mm, half_mm, a_mm)
    ii, jj, area = tb.pad_overlap(poly, 0.0, 0.0, pitch_mm, 0, 0, n, n)
    lk = tb.LeadLink("DISC", "1", g, t_s)
    lk.groups.append((ii * n + jj, area / area.sum(), g, "disc"))
    lk.shares.append(1.0)
    rise, _, rec = tb.solve_system(board, np.full((1, n, n), k), np.array([t]), np.zeros((1, n, n)), h, pitch_mm * 1e-3,
                                   [], [], leads=[lk])
    num = float((rise[0][ii, jj] * area / area.sum()).sum())
    flux_in = g * (t_s - num)
    return {"pass": abs(num - exact) / exact < 0.03 and abs(rec["convection_w"] - flux_in) < 1e-6 * flux_in,
            "disc_mean_exact_K": exact, "disc_mean_numeric_K": num, "rel_err": abs(num - exact) / exact,
            "lead_to_board_W": flux_in, "convection_W": rec["convection_w"], "lead_sink_w_receipt": rec["lead_sink_w"]}


def main():
    res = {"K1_repo_reproduces_committed_margins": k1(), "K2_g0_reproduces_repo": k2(), "K3_energy": k3(),
           "K4_analytic_disc_lead": k4()}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "controls.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    ok = all(v["pass"] for v in res.values())
    for k_, v in res.items():
        print(f"{k_}: {'PASS' if v['pass'] else 'FAIL'}  " + json.dumps({a: b for a, b in v.items() if a not in ('mismatches', 'failures')}, default=str)[:300])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
