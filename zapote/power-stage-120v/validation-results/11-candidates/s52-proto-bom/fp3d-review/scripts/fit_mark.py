"""Independent check of the BANK H/B fit mark: board-level F.SilkS items in x 190-226, y 112-123; their size / stroke;
bounding-box distance to every F-side pad (copper + mask expansion) and courtyard. KiCad python3 -I fit_mark.py BOARD OUT.json"""
import json, math, sys
import pcbnew
b = pcbnew.LoadBoard(sys.argv[1]); mm = pcbnew.ToMM
W = (190, 112, 226, 123)
def inwin(r): return r[0] >= W[0] and r[2] <= W[2] and r[1] >= W[1] and r[3] <= W[3]
def rr(bb): return [mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())]
def gap(a, c): return math.hypot(max(c[0] - a[2], a[0] - c[2], 0), max(c[1] - a[3], a[1] - c[3], 0))
items = []
for d in b.GetDrawings():
    if d.GetLayer() != pcbnew.F_SilkS: continue
    r = rr(d.GetBoundingBox())
    if not inwin(r): continue
    e = {"class": d.GetClass(), "bbox": [round(v, 3) for v in r]}
    if d.GetClass() in ("PCB_TEXT", "PCB_TEXTBOX"):
        e.update(text=d.GetText(), h=mm(d.GetTextHeight()), w=mm(d.GetTextWidth()), stroke=mm(d.GetTextThickness()),
                 mirrored=d.IsMirrored(), angle=d.GetTextAngleDegrees())
    else:
        e.update(stroke=mm(d.GetWidth()))
    items.append(e)
U = [min(i["bbox"][0] for i in items), min(i["bbox"][1] for i in items), max(i["bbox"][2] for i in items), max(i["bbox"][3] for i in items)]
pads, crt = [], []
for f in b.GetFootprints():
    for p in f.Pads():
        if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.F_Mask):
            r = rr(p.GetBoundingBox()); m = mm(p.GetSolderMaskExpansion(pcbnew.F_Mask)) if hasattr(p, "GetSolderMaskExpansion") else 0.0
            r = [r[0] - m, r[1] - m, r[2] + m, r[3] + m]
            pads.append((round(gap(U, r), 3), f.GetReference() + "." + p.GetNumber()))
    c = f.GetCourtyard(pcbnew.F_CrtYd)
    if c.OutlineCount():
        crt.append((round(gap(U, rr(c.BBox())), 3), f.GetReference()))
pads.sort(); crt.sort()
out = {"mark_union_bbox": [round(v, 3) for v in U], "items": items, "nearest_pads_bbox_gap": pads[:5], "nearest_courtyards_bbox_gap": crt[:5]}
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(json.dumps(out, indent=1)[:3000])
