"""Checks on the coil-r1 former CAD (writes out/checks.json). Run: .venv/bin/python cad/check_former.py

1. Reconstruction: former.former() with the R43 winding and no spare turn must reproduce the frozen R43 part
   (output/temper-manufacturing-r43/STEP/parts/sensor_coil_former.step, read-only) - volume and boolean differences.
2. R1 former: every notch on the comb; tooth widths (CNC 0.2 / print 0.3 clearance) for the design bundle and for the
   stock-Litz OD 2.55 (RM Cybernetics 1000 x 0.05); spare notch inside the rim; NTC wall; print segments fit a 180 bed.
"""
from __future__ import annotations

import json
from pathlib import Path

from build123d import Pos, import_step

import former as F
import geom as K
from geom import G

R43_STEP = Path("/Users/bennet/Desktop/temper/output/temper-manufacturing-r43/STEP/parts/sensor_coil_former.step")
OUT = Path(__file__).resolve().parent / "out"


def vol(s):
    sol = list(s.solids()) if hasattr(s, "solids") else [y for r in s for y in r.solids()]
    return sum(x.volume for x in sol)


def main():
    res = {}
    if R43_STEP.exists():
        ref = import_step(str(R43_STEP))
        mine, _ = F.former(w=G.R43, spare=0.0)
        moved = Pos(0, 261, 93) * mine
        res["R43_reconstruction"] = dict(ref_volume_mm3=ref.volume, rebuilt_volume_mm3=mine.volume,
                                         ref_minus_rebuilt_mm3=vol(ref.cut(moved)), rebuilt_minus_ref_mm3=vol(moved.cut(ref)))
    rows = F.notch_list(G.R1, G.R1_SPARE_OUTER_TURNS)
    pin, pout = G.R1.sections[0].pitch, G.R1.sections[1].pitch
    res["notches"] = dict(inner=sum(r["section"] == "inner" for r in rows), outer=sum(r["section"] == "outer" and not r["spare"] for r in rows),
                          spare=sum(r["spare"] for r in rows), r_min=min(r["r_mm"] for r in rows), r_max=max(r["r_mm"] for r in rows),
                          on_comb=all(K.COMB_R0 - 2 <= r["r_mm"] <= K.GAP_R[0] or K.GAP_R[1] <= r["r_mm"] <= K.RIM_R[0] for r in rows
                                      if r["r_mm"] >= K.COMB_R0))
    res["spare_notch_outer_edge_mm"] = res["notches"]["r_max"] + 2.4 / 2 + 0.1
    res["rim_inner_r_mm"] = K.RIM_R[0]
    res["teeth_mm"] = {f"{route}_bundle{b}": dict(inner=round(pin - b - c, 3), outer=round(pout - b - c, 3))
                       for route, c in (("cnc", 0.2), ("print", 0.3)) for b in (2.40, 2.55)}
    _, info = F.former()
    res["ntc"] = info["ntc"]
    pr, _ = F.former(clearance=0.3)
    segs, _ = F.segments(pr)
    res["print_segments_mm"] = [[round(s.bounding_box().size.X, 1), round(s.bounding_box().size.Y, 1)] for s in segs]
    res["print_segments_fit_180_bed"] = all(max(xy) <= 180 for xy in res["print_segments_mm"])
    (OUT / "checks.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
