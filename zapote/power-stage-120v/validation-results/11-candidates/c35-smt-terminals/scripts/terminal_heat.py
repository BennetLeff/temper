#!/usr/bin/env python3
"""Coil-terminal heat at J2 (coil_feed) / J5 (res_a): task 04 copper loss near each terminal and B3 temperatures there.

    python3 -I scripts/terminal_heat.py LABEL TASK04_OUTPUTS B3_OUTPUTS [--json OUT.json]

TASK04_OUTPUTS: a round5-native21/outputs directory (the res_a / coil_feed case JSON + *-heat.npz, gitignored).
B3_OUTPUTS: a round5-native21/b3/outputs directory (the operating-point JSON + .npz, gitignored).
Run it on the board-of-record outputs (s32, THR 74650074) and on the candidate's (s35, SMT 7466004R) right after each
chain, before another chain overwrites them; both must come from one board (the board_sha256 fields are checked).

Reported per terminal:
- task 04, cases res_a (bank -> J5) and coil_feed (T1.2 -> J2) at 18.7 A, 18 and 12 um plating: the whole-path
  resistance and loss, and the copper loss (sheet cells + barrel hops) within R_NEAR of the terminal centre, scaled to
  the 29.4 A trip by (29.4 / 18.7)^2 as B3 does (run_study.py, op c28);
- the largest land-via / lead current in that radius;
- B3, every operating point and pitch present: the hottest cell (any copper layer) within R_NEAR of the terminal, and
  the board peak for reference.
B3 models the terminal through its copper only: neither part has a heat-source row (make_heat_sources.py), so contact
and lug heat are outside the model for both terminals alike (Wuerth's design guide p.11 puts both on one derating curve).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

TERMINALS = {"J5": ("res_a", (132.0, 70.5)), "J2": ("coil_feed", (132.0, 85.5))}
R_NEAR = 7.0            # mm: the 9.2 mm stud land's corner (6.5 mm) plus a margin; J2 / J5 are 15 mm apart
TRIP = 29.4 / 18.7      # current scale from the 18.7 A A4 case to the 29.4 A firmware trip


def near(x, y, c, r=R_NEAR):
    return (x - c[0]) ** 2 + (y - c[1]) ** 2 <= r * r


def task04(d):
    out, boards = {}, set()
    for ref, (net, c) in TERMINALS.items():
        for pl in (18, 12):
            j = Path(d) / f"{net}-p0125-pl{pl}.json"
            if not j.exists():
                continue
            r = json.loads(j.read_text())
            boards.add(r["board_sha256"])
            npz = np.load(Path(d) / r["nodal_heat_file"])
            sheet = 0.0
            for k in npz.files:
                if k.endswith("_joule_w"):
                    lay = k[:-len("_joule_w")]
                    xs, ys = npz[f"{lay}_x_mm"], npz[f"{lay}_y_mm"]
                    X, Y = np.meshgrid(xs, ys, indexing="ij")
                    sheet += float(npz[k][near(X, Y, c)].sum())
            barrel = sum(h["joule_w"] for h in r["barrel_hop_heat"] if near(*h["xy_mm"], c))
            vias = [v for v in r["via_currents"] if near(*v["xy"], c)]
            out[f"{ref}_pl{pl}"] = {
                "net": net, "sinks": r["sinks"], "r_path_mohm": round(r["r_ohm"] * 1e3, 4),
                "path_loss_w_at_18p7A": round(r["loss_w"], 4), "path_loss_w_at_29p4A": round(r["loss_w"] * TRIP ** 2, 4),
                "near_terminal_loss_w_at_18p7A": round(sheet + barrel, 4),
                "near_terminal_loss_w_at_29p4A": round((sheet + barrel) * TRIP ** 2, 4),
                "near_sheet_w_at_29p4A": round(sheet * TRIP ** 2, 4), "near_barrel_w_at_29p4A": round(barrel * TRIP ** 2, 4),
                "near_vias_or_leads": len(vias),
                "max_via_or_lead_amps_at_29p4A": round(max((abs(v["amps"]) for v in vias), default=0.0) * TRIP, 3)}
    return out, boards


def b3(d):
    out, boards = {}, set()
    for j in sorted(Path(d).glob("*_h*_p*.json")):
        if j.stem.startswith("sweep"):
            continue
        r = json.loads(j.read_text())
        boards.add(r["board_sha256"])
        z = np.load(j.with_suffix(".npz"))
        x, y, rise, board = z["x_mm"], z["y_mm"], z["rise_k"], z["board_mask"]
        names = r["layer_names"]
        cu = [i for i, n in enumerate(names) if n.endswith(".Cu")]
        X, Y = np.meshgrid(x, y, indexing="ij")
        row = {"board_peak_c": round(r["peak"]["temperature_c"], 2),
               "board_peak_at": [r["peak"]["x_mm"], r["peak"]["y_mm"], r["peak"]["layer"]]}
        for ref, (_, c) in TERMINALS.items():
            m = near(X, Y, c) & board
            best = max(((float(rise[i][m].max()), names[i]) for i in cu), key=lambda t: t[0])
            k = np.argmax(np.where(m, rise[names.index(best[1])], -np.inf))
            row[ref] = {"max_c": round(50.0 + best[0], 2), "layer": best[1],
                        "at": [round(float(X.ravel()[k]), 2), round(float(Y.ravel()[k]), 2)],
                        "f_cu_mean_c": round(50.0 + float(rise[names.index("F.Cu")][m].mean()), 2)}
        out[j.stem] = row
    return out, boards


ap = argparse.ArgumentParser()
ap.add_argument("label"); ap.add_argument("task04"); ap.add_argument("b3")
ap.add_argument("--json")
a = ap.parse_args()
t, tb = task04(a.task04)
h, hb = b3(a.b3)
assert len(tb) == 1 and tb == hb, ("task 04 and B3 outputs are not from one board", tb, hb)
res = {"label": a.label, "board_sha256": tb.pop(), "r_near_mm": R_NEAR, "trip_A": 29.4, "task04": t, "b3": h}
for k, v in t.items():
    print(f"{k}: path {v['r_path_mohm']} mOhm, {v['path_loss_w_at_29p4A']} W at 29.4 A; near-terminal "
          f"{v['near_terminal_loss_w_at_29p4A']} W (sheet {v['near_sheet_w_at_29p4A']}, barrels {v['near_barrel_w_at_29p4A']}); "
          f"{v['near_vias_or_leads']} vias/leads, max {v['max_via_or_lead_amps_at_29p4A']} A")
for k, v in h.items():
    print(f"{k}: J5 {v['J5']['max_c']} C ({v['J5']['layer']}), J2 {v['J2']['max_c']} C ({v['J2']['layer']}); board peak {v['board_peak_c']} C")
if a.json:
    Path(a.json).write_text(json.dumps(res, indent=1) + "\n")
