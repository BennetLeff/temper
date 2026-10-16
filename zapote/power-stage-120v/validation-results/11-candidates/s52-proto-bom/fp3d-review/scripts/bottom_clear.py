"""Bottom-side clearance around the stage-52 parts' THT pads: B-side footprints (courtyard distance) and B.Cu SMD pads
of any footprint, plus other THT pads nearby (wave/selective nozzle access). Usage: KiCad python3 -I bottom_clear.py BOARD OUT.json"""
import json, math, sys
import pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.ToMM
REFS = ["C21", "C22", "C23", "C151", "C152", "L1", "C3", "C4"]
fps = {f.GetReference(): f for f in b.GetFootprints()}
bside = [f for f in b.GetFootprints() if f.IsFlipped()]
def rect_dist(px, py, r):
    dx = max(r[0] - px, 0, px - r[2]); dy = max(r[1] - py, 0, py - r[3]); return math.hypot(dx, dy)
out = {"b_side_footprints": [f.GetReference() for f in bside], "parts": {}}
allpads = [(f.GetReference(), p) for f in b.GetFootprints() for p in f.Pads()]
for r in REFS:
    rows = []
    for p in fps[r].Pads():
        px, py = mm(p.GetPosition().x), mm(p.GetPosition().y)
        rad = mm(p.GetSizeX()) / 2
        nb = []
        for f in bside:
            c = f.GetCourtyard(pcbnew.B_CrtYd)
            bb = c.BBox() if c.OutlineCount() else f.GetBoundingBox(False, False)
            rr = [mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())]
            nb.append((round(rect_dist(px, py, rr) - rad, 3), f.GetReference(), "B-side courtyard"))
        for ref2, q in allpads:
            if ref2 == r:
                continue
            qx, qy = mm(q.GetPosition().x), mm(q.GetPosition().y)
            d = math.hypot(qx - px, qy - py) - rad - max(mm(q.GetSizeX()), mm(q.GetSizeY())) / 2
            if d < 6:
                kind = "THT pad" if q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else ("B.Cu SMD pad" if q.IsOnLayer(pcbnew.B_Cu) else "F.Cu SMD pad")
                nb.append((round(d, 3), ref2 + "." + q.GetNumber(), kind))
        nb.sort()
        rows.append({"pad": p.GetNumber(), "x": px, "y": py, "nearest": nb[:4]})
    out["parts"][r] = rows
json.dump(out, open(sys.argv[2], "w"), indent=1)
print("B-side footprints:", len(bside), out["b_side_footprints"][:20])
for r, rows in out["parts"].items():
    for row in rows:
        print(r, row["pad"], row["x"], row["y"], row["nearest"][:3])
