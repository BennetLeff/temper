#!/usr/bin/env python3
"""D-4 follow-up (P1, current modes): how large is the omitted bulk mode?

The FEM ports are the two local-capacitor loops (P1 C38, P2 C39) and the two
gate loops. The deck also feeds the switch node from the bulk capacitor
through LBULK, with no FEM inductance on that path, and imposes the load
through an ideal current source. Any board copper the bulk current shares with
a gate loop is therefore missing from the gate-loop EMF:

    v_missing = M_bulk,gate * di_bulk/dt          (M_bulk,gate not extracted)

The load source is ideal and its PWL is constant after 1 us (T1 = 2 us), so
its slew in the window is zero by construction: the tank inductor's current
does not change over a switching edge. Only the bulk branch is measured.

For each case this saves the branch currents, finds the largest |di/dt| in
the switching window (T1 .. T1+DT+0.75 us) for the bulk, C38 and C39
branches, and compares, for each gate loop g:
  represented   max over time of |M_1g di_1/dt + M_2g di_2/dt|  (FEM, in the deck)
  estimate      max|di_bulk/dt| * max(|M_1g|, |M_2g|)          (bulk copper coupling
                like the capacitor copper: an ESTIMATE, not a bound)
  cs_bound      max|di_bulk/dt| * sqrt(LBULK * L_gg)           (Cauchy-Schwarz; a bound
                only if LBULK is the bulk path's whole loop inductance, which is a
                round-3 heuristic, not FEM)

    bulk_mode.py --matrix legA-h0-lin12.matrix.txt [--out results/bulk-mode]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

import run_d2
from run_ngspice import read_raw

HERE = Path(__file__).resolve().parent
CASES = [  # (label, vbus, il, dir, dt_ns, esl_nH): nominal, heaviest hard switch, diode recovery
    ("S1", 170, 37, 0, 348, 10), ("S1", 170, 37, 1, 348, 10),
    ("S2", 280, 71, 0, 348, 10), ("S2", 280, 71, 1, 348, 10),
    ("S4", 198, -20, 0, 348, 10), ("S4", 198, -20, 1, 348, 10),
]
BRANCHES = {"bulk": "i(lbulk)", "c38": "i(l_p1)", "c39": "i(l_p2)"}
LBULK_NH = 21.519


def branches(n: int) -> dict[str, str]:
    """Branch currents; with 5 ports 'bulk' is the C5 path only and C6 is FEM port P5."""
    return BRANCHES if n == 4 else dict(BRANCHES, c6="i(l_p5)")


def deck_with_currents(out: Path, n: int) -> Path:
    src = run_d2.DECK if n == 4 else HERE / "leg_matrix5.cir"
    text = src.read_text()
    save = ".save v(sw) v(bus)"
    assert text.count(save) == 1
    text = text.replace(save, save + " " + " ".join(branches(n).values()))
    d = out / f"{src.stem}_currents.cir"
    d.write_text(text)
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--out", default=str(HERE / "results" / "bulk-mode"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    L = np.array(run_d2.read_L(a.matrix))
    deck = deck_with_currents(out, len(L))
    rows = []
    for c in CASES:
        s, vbus, il, d, dt, esl = c
        tag = f"{s}_v{vbus}_i{il}_d{d}_dt{dt}_esl{esl}"
        p = run_d2.matrix_params(L.tolist())
        p.update(VBUS=str(vbus), IL=str(il), DIR=str(d), LESL=f"{esl}n", LSHUNT="2n", DT=f"{dt}n", TRMAX="0.2n")
        r = run_d2.run(deck, p, keep=out / "runs" / tag, raw=True)
        if r["aborted"]:
            rows.append({"tag": tag, "aborted": True})
            continue
        w = read_raw(out / "runs" / tag / "waves.raw")
        t = np.array(w["time"])
        t1 = 2e-6
        win = (t >= t1) & (t <= t1 + dt * 1e-9 + 0.75e-6)
        slew = {}
        fem = {"c38": 0, "c39": 1, "c6": 4}             # FEM power ports present in this deck
        for k, v in branches(len(L)).items():
            i = np.array(w[v])
            didt = np.gradient(i, t)
            slew[k] = didt
        row = {"tag": tag, "aborted": False,
               "max_abs_didt_A_per_ns": {k: float(np.abs(v[win]).max() * 1e-9) for k, v in slew.items()}}
        for g, gi in (("gate_high", 2), ("gate_low", 3)):
            rep = np.abs(sum(L[fem[k], gi] * slew[k][win] for k in fem if k in slew)) * 1e-9   # nH * A/s -> V
            mb = row["max_abs_didt_A_per_ns"]["bulk"]
            row[g] = {"represented_V": float(rep.max()),
                      "bulk_estimate_V": mb * max(abs(L[fem[k], gi]) for k in fem if k in slew),
                      "bulk_cs_bound_V": mb * math.sqrt(LBULK_NH * L[gi, gi])}
        rows.append(row)
        print(json.dumps(row))
    res = {"matrix": a.matrix, "lbulk_nH": LBULK_NH, "cases": rows,
           "note": "estimate assumes bulk copper couples like the capacitor copper; cs_bound holds only if "
                   "LBULK is the bulk path's whole loop inductance (round-3 heuristic)"}
    (out / "summary.json").write_text(json.dumps(res, indent=1))
    print("RESULT " + json.dumps(res))


if __name__ == "__main__":
    main()
