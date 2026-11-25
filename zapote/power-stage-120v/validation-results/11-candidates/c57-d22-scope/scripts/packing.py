#!/usr/bin/env python3
"""Do the D-22 parts fit one side of a board in the reserved 110 x 80 mm, and with what gap between every pair of bodies?

    python3 packing.py      (needs ortools; CP-SAT, 0.1 mm grid, 90 degree rotation, deterministic single worker)

Body rectangles only: the gap stands in for creepage, courtyard and routing, the same on every side and to the board edge it is
EDGE. It is a necessary check, not a layout. Bodies: out-D22/PARTS.md; SCF31X and WE-HCFT from MODULE-REQUEST / c53 s3. The M4
pattern is R20's 96 x 62 (centres 7 / 103 and 9 / 71 mm). ASSUMED (no part selected): terminals 2 x (20.3 x 12.6) mm L-N blocks
and one 10 x 12.6 PE block, M4 washer keepout 10 x 10 mm, bleed resistors lying flat 12 x 4.
Controls: one oversized part must be infeasible; the caps alone must be feasible at 5 mm.
"""
import json
import sys
from pathlib import Path

from ortools.sat.python import cp_model

OUT = Path(__file__).resolve().parents[1] / "results/packing.json"
EDGE = 1.0
CAPS = [("CXIN", 26.5, 14.5), ("CXNEW", 31.5, 21.0), ("CDAMP", 31.5, 21.0), ("RDAMP", 18.0, 7.5), ("BLEED1", 12.0, 4.0), ("BLEED2", 12.0, 4.0)]
TERM = [("TB_IN", 20.3, 12.6), ("TB_OUT", 20.3, 12.6), ("PE", 10.0, 12.6)]
SCF = [("SCF31X-JH", 45.0, 42.0)]   # flat part, 33 mm tall (KEMET LF0101 table: 45.0 / 42.0 / 33.0, Fig. 2)
SCF_UP = [("SCF31X-JV", 45.0, 31.0)]   # vertical sibling, 42 mm tall, pin pitch 18 / 22 (LF0101 Fig. 1)
COD = [("LDM_L", 32.8, 31.0), ("LDM_N", 32.8, 31.0)]   # Codaca CPER3231-101MC (compared, not proposed)
W3635 = [("LDM_L", 36.0, 35.7), ("LDM_N", 36.0, 35.7)]
TOR = [("LDM_L", 52.4, 26.1), ("LDM_N", 52.4, 26.1)]   # 0077439A7 wound on edge (52.4 mm tall: over the 50 mm height anyway)


def fits(parts, W, H, gap, m4, tmax=60):
    U = lambda v: int(round(v * 10))
    m = cp_model.CpModel()
    X, Y = [], []
    for n, a, b in parts:
        r = m.NewBoolVar(n)
        w, h = m.NewIntVar(U(min(a, b)), U(max(a, b)), n + "w"), m.NewIntVar(U(min(a, b)), U(max(a, b)), n + "h")
        m.Add(w == U(a)).OnlyEnforceIf(r.Not()); m.Add(h == U(b)).OnlyEnforceIf(r.Not())
        m.Add(w == U(b)).OnlyEnforceIf(r); m.Add(h == U(a)).OnlyEnforceIf(r)
        x, y = m.NewIntVar(U(EDGE), U(W), n + "x"), m.NewIntVar(U(EDGE), U(H), n + "y")
        m.Add(x + w <= U(W - EDGE)); m.Add(y + h <= U(H - EDGE))
        g = U(gap)
        wg, hg = m.NewIntVar(0, U(W) + g, n + "wg"), m.NewIntVar(0, U(H) + g, n + "hg")
        m.Add(wg == w + g); m.Add(hg == h + g)
        ex, ey = m.NewIntVar(0, U(W) * 2, n + "ex"), m.NewIntVar(0, U(H) * 2, n + "ey")
        X.append(m.NewIntervalVar(x, wg, ex, n + "ix")); Y.append(m.NewIntervalVar(y, hg, ey, n + "iy"))
    if m4:
        for cx in (W / 2 - 48, W / 2 + 48):
            for cy in (H / 2 - 31, H / 2 + 31):
                X.append(m.NewFixedSizeIntervalVar(U(cx - 5), U(10 + gap), "kx")); Y.append(m.NewFixedSizeIntervalVar(U(cy - 5), U(10 + gap), "ky"))
    m.AddNoOverlap2D(X, Y)
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = tmax
    s.parameters.num_search_workers = 4
    s.parameters.random_seed = 1
    return {cp_model.OPTIMAL: "fits", cp_model.FEASIBLE: "fits", cp_model.INFEASIBLE: "infeasible"}.get(s.Solve(m), "undecided")


assert fits([("X", 111, 10)], 110, 80, 0, False) == "infeasible" and fits(CAPS, 110, 80, 5, True) == "fits"
res = {"area_mm2": {}, "cases": {}}
for nm, L, S in (("2x WE-HCFT 3635, SCF31X-JH", W3635, SCF), ("2x WE-HCFT 3635, SCF31X-JV", W3635, SCF_UP), ("2x CPER3231, SCF31X-JV", COD, SCF_UP), ("2x toroid on edge, SCF31X-JV", TOR, SCF_UP)):
    parts = CAPS + TERM + S + L
    res["area_mm2"][nm] = round(sum(a * b for _, a, b in parts) + 400)
    for W, H in ((110, 80), (120, 80), (130, 85)):
        row = {}
        for gap in (0, 1, 2, 3, 4, 5, 6):
            row[f"{gap}mm"] = fits(parts, W, H, gap, True)
            if row[f"{gap}mm"] == "infeasible":
                break
        res["cases"][f"{nm} | {W}x{H}"] = row
        print(nm, W, H, row, flush=True)
OUT.write_text(json.dumps(res, indent=1) + "\n")
print(res["area_mm2"])
