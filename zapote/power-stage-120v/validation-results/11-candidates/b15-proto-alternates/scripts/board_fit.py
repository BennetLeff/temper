#!/usr/bin/env python3
"""Read-only footprint-fit check on the stage-50 board of record (e842d9c8, runs-native21/s50/c50int/section.kicad_pcb).

For each target reference: footprint name, position, pads (hole size / pad size / net), and the clearance from a
candidate body outline (circle or rectangle, centred on the footprint as the fitted part's body is) to every other
footprint's courtyard on the same side, plus the nearest copper pad of another net.
Usage: /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 -I board_fit.py BOARD OUT.json
(KiCad's pcbnew module, read only; the board is never saved.)
"""
import json
import math
import sys

import pcbnew

board_path, out = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(board_path)
MM = 1e6
fps = {f.GetReference(): f for f in b.GetFootprints()}


def crt(f):
    """courtyard bbox (mm) of a footprint on its side, or the fab bbox when no courtyard."""
    side = pcbnew.F_CrtYd if f.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
    try:
        poly = f.GetCourtyard(side)
        bb = poly.BBox()
        if bb.GetWidth() > 0:
            return (bb.GetX() / MM, bb.GetY() / MM, (bb.GetX() + bb.GetWidth()) / MM, (bb.GetY() + bb.GetHeight()) / MM)
    except Exception:
        pass
    bb = f.GetBoundingBox(False, False)
    return (bb.GetX() / MM, bb.GetY() / MM, (bb.GetX() + bb.GetWidth()) / MM, (bb.GetY() + bb.GetHeight()) / MM)


def rect_dist(a, r):
    dx = max(r[0] - a[2], a[0] - r[2], 0)
    dy = max(r[1] - a[3], a[1] - r[3], 0)
    return math.hypot(dx, dy) if (dx or dy) else -min(a[2] - r[0], r[2] - a[0], a[3] - r[1], r[3] - a[1])


def body_box(f, shape):
    """candidate body footprint on the board (mm bbox), centred between the pads (radial disc: D x T along pad axis)."""
    pads = list(f.Pads())
    cx = sum(p.GetPosition().x for p in pads) / len(pads) / MM
    cy = sum(p.GetPosition().y for p in pads) / len(pads) / MM
    if len(pads) >= 2:
        p0, p1 = pads[0].GetPosition(), pads[1].GetPosition()
        horiz = abs(p1.x - p0.x) >= abs(p1.y - p0.y)
    else:
        horiz = True
    w, h = shape
    if not horiz:
        w, h = h, w
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), (cx, cy), horiz


TARGETS = {
    # ref: list of (label, (along-pad-axis mm, across mm)) candidate body outlines
    "C3": [("fitted DE1E3RA222MA4BP01F D9.0 x T4.0", (9.0, 4.0)), ("Murata H01F / P01F same body D9.0 x T4.0", (9.0, 4.0)),
           ("Murata Q01F D11.0 x T6.0", (11.0, 6.0)), ("Vishay VY1222M47 D12.0 x T5.0", (12.0, 5.0)),
           ("TDK CD45-E2GA222M D? (see README)", (10.0, 5.0))],
    "C4": [("fitted DE1E3RA222MA4BP01F D9.0 x T4.0", (9.0, 4.0)), ("Murata Q01F D11.0 x T6.0", (11.0, 6.0)),
           ("Vishay VY1222M47 D12.0 x T5.0", (12.0, 5.0))],
    "L1": [], "D6": [], "D7": [], "D8": [], "D9": [],
}
res = {"board": board_path, "parts": {}}
for ref, cands in TARGETS.items():
    f = fps[ref]
    pads = [{"num": p.GetNumber(), "net": p.GetNetname(), "x": p.GetPosition().x / MM, "y": p.GetPosition().y / MM,
             "size": [p.GetSize().x / MM, p.GetSize().y / MM],
             "drill": [p.GetDrillSize().x / MM, p.GetDrillSize().y / MM]} for p in f.Pads()]
    entry = {"footprint": str(f.GetFPID().GetUniStringLibItemName()), "x": f.GetPosition().x / MM,
             "y": f.GetPosition().y / MM, "rot_deg": f.GetOrientationDegrees(),
             "side": "F" if f.GetLayer() == pcbnew.F_Cu else "B", "courtyard": crt(f), "pads": pads}
    if len(pads) >= 2:
        entry["pad_pitch_mm"] = math.hypot(pads[0]["x"] - pads[1]["x"], pads[0]["y"] - pads[1]["y"])
    others = [(r, crt(g)) for r, g in fps.items() if r != ref and g.GetLayer() == f.GetLayer()]
    near = sorted(((rect_dist(entry["courtyard"], c), r) for r, c in others))[:6]
    entry["nearest_courtyards_mm"] = [[r, round(d, 3)] for d, r in near]
    entry["candidates"] = []
    for label, shape in cands:
        bb, c, horiz = body_box(f, shape)
        dd = sorted(((rect_dist(bb, cc), r) for r, cc in others))[:4]
        entry["candidates"].append({"label": label, "body_bbox_mm": [round(v, 3) for v in bb], "pad_axis_horizontal": horiz,
                                    "nearest_other_courtyards_mm": [[r, round(d, 3)] for d, r in dd]})
    res["parts"][ref] = entry
json.dump(res, open(out, "w"), indent=1)
for ref, e in res["parts"].items():
    print(ref, e["footprint"], e["side"], round(e["x"], 2), round(e["y"], 2), e["rot_deg"], e.get("pad_pitch_mm"),
          [(p["num"], p["net"], p["size"], p["drill"]) for p in e["pads"]][:4])
    print("   near", e["nearest_courtyards_mm"])
    for c in e["candidates"]:
        print("   ", c["label"], c["nearest_other_courtyards_mm"])
