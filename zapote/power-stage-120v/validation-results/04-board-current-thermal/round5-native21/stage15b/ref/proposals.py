#!/usr/bin/env python3
"""Stage 15: check proposed tank-copper outline edits against native-21 clearances and re-measure widths.

Each proposal ADDs a box to a net's copper on one layer, and may TRIM boxes out of other nets' pours
(patches21.py edit_zones style: shapely union / difference on zone outlines; KiCad refills).
Checks, on the routed copper dump (filled copper as of the dump):
  * clearance from the added copper to every other-net item on that layer (rules21.clearance), with
    trimmed pours removed first, and the 8.0 mm plan-view barrier to SELV/PE on any layer;
  * width cuts of the edited net on the same runs as sw_widths.py.
The added box is clipped to the available area first (so the result is what KiCad's refill would
give if the outline were drawn this way); the report gives both the drawn box and what survives.
usage: python3 proposals.py <copper-dump.json> <section.kicad_pcb> [UNIT] -> out/proposals.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, box
from shapely.ops import unary_union

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sww", HERE / "sw_widths.py")
W = importlib.util.module_from_spec(spec)
argv = sys.argv[:]
spec.loader.exec_module(W)          # sw_widths parses argv at import: same arguments
R = W.R

PROPOSALS = [
    # id, net, layer, add boxes, trims [(net, layer, box)], why
    ("P-A1", "sw_a", "F.Cu", [(148.6, 37.2, 152.4, 101.5)], [],
     "SW_A leg to T1: right edge 148.6 -> 152.4 (the J5 5 mm bite leaves 7.0 mm; the leg is 9.6 mm)"),
    ("P-A2", "sw_a", "F.Cu", [(100.0, 30.4, 103.6, 37.2)], [("n_filt", "F.Cu", (96.0, 26.0, 103.6, 41.0))],
     "SW_A corner x 103.6-110: fill the inside corner (6.4 mm neck)"),
    ("P-B1", "sw_b", "B.Cu", [(150.0, 46.8, 188.0, 50.0)], [],
     "SW_B band at the bank: restore y 46.8-50 where the res_a strip's 5 mm rule allows (x >~ 171)"),
    ("P-B1b", "sw_b", "B.Cu", [(150.0, 36.8, 188.0, 37.2)], [("l_filt", "B.Cu", (150.0, 33.4, 188.0, 34.2))],
     "SW_B band x 150-171: raise the top 0.4 mm; trim the l_filt pour's lower edge by 0.4 mm"),
    ("P-B2", "sw_b", "B.Cu", [(110.0, 19.7, 110.6, 37.2)], [("l_filt", "B.Cu", (112.0, 9.0, 114.0, 37.0))],
     "SW_B drop x 100.5-110: right edge +0.6 mm; trim l_filt's left edge"),
    ("P-B3", "sw_b", "B.Cu", [(83.7, 15.6, 100.5, 19.4)], [("l_filt", "B.Cu", (83.0, 12.4, 101.0, 17.0))],
     "SW_B band x 84-100: raise the top from 19.4 to 15.6; trim l_filt's lower edge to 12.4"),
]

RUNS = {r[0]: r for r in W.RUNS}


def main():
    d = json.loads(W.DUMP.read_text())
    side = W.sides()
    items = W.build(d, side)
    board = W.outline(d)
    # apply all trims first (they are independent of each other)
    trims = [(n, L, box(*b)) for _, _, _, _, tr, _ in PROPOSALS for n, L, b in tr]
    items2 = []
    for n, L, g, k, r in items:
        if k == "pour":
            for tn, tl, tb in trims:
                if n == tn and tl in L:
                    g = g.difference(tb)
        items2.append((n, L, g, k, r))
    out = {"proposals": [], "widths_after": {}}
    added = {}
    for pid, net, layer, adds, tr, why in PROPOSALS:
        obst = []
        for n, L, g, k, r in items2:
            if n == net or g.is_empty:
                continue
            if layer in L:
                obst.append((g.buffer(R.clearance(net, n) - 1e-3), k, n, r))
            elif R.barrier(net, n):
                obst.append((g.buffer(R.BARRIER - 1e-3), k + "(barrier)", n, r))
        ob_u = unary_union([o[0] for o in obst])
        for b in adds:
            bb = box(*b)
            ok = bb.intersection(board).difference(ob_u)
            hit = sorted({f"{k}:{n}:{r}" for g, k, n, r in obst if g.intersects(bb)})
            out["proposals"].append({"id": pid, "net": net, "layer": layer, "box": b, "why": why,
                                     "trims": tr, "area_drawn_mm2": round(bb.area, 1),
                                     "area_kept_mm2": round(ok.area, 1), "clipped_by": hit[:12]})
            added.setdefault((net, layer), []).append(ok)
    # re-measure the runs with the additions (and trims) applied
    for name, net, layer, flow, (c0, c1), (w0, w1), frac in W.RUNS:
        cu = unary_union([g for n, L, g, k, r in items2 if n == net and layer in L] + added.get((net, layer), []))
        rows = []
        c = c0
        while c <= c1 + 1e-9:
            line = LineString([(c, w0), (c, w1)]) if flow == "x" else LineString([(w0, c), (w1, c)])
            f = (sum(1 for ty in W.BANK_TAPS_Y if ty > c) / 5.0) if frac is None else frac
            rows.append({"at": round(c, 2), "w": round(line.intersection(cu).length, 2), "need": round(W.ipc_width(28 * f), 2)})
            c += W.STEP
        short = [x for x in rows if x["w"] < x["need"]]
        spans = []
        for x in short:
            if spans and x["at"] - spans[-1][1] <= W.STEP + 1e-6:
                spans[-1][1] = x["at"]; spans[-1][2] = min(spans[-1][2], x["w"])
            else:
                spans.append([x["at"], x["at"], x["w"]])
        out["widths_after"][name] = {"min_w_mm": min(x["w"] for x in rows), "short_cuts": len(short),
                                     "short_spans_[from,to,wmin]": spans}
    (HERE / "out/proposals.json").write_text(json.dumps(out, indent=1) + "\n")
    for p in out["proposals"]:
        print(p["id"], p["box"], "drawn", p["area_drawn_mm2"], "kept", p["area_kept_mm2"], p["clipped_by"])
    for k, v in out["widths_after"].items():
        print(f"{k:50s} {v}")


if __name__ == "__main__":
    main()
