"""KiCad-python half of bank_mark52.py: dump the bank-fit mark and its neighbours as polygons (run by bank_mark52.py
with KiCad's bundled python; prints JSON on stdout). argv: board.kicad_pcb x0 y0 x1 y1 (search window, mm)."""
import json
import sys

import pcbnew

MM = 1e-6


def polys(ps):
    out = []
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        out.append([(o.CPoint(j).x * MM, o.CPoint(j).y * MM) for j in range(o.PointCount())])
    return out


def item_poly(it, layer, clr=0):
    ps = pcbnew.SHAPE_POLY_SET()
    it.TransformShapeToPolygon(ps, layer, clr, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    return polys(ps)


b = pcbnew.LoadBoard(sys.argv[1])
x0, y0, x1, y1 = (float(v) for v in sys.argv[2:6])
win = pcbnew.BOX2I(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0)),
                   pcbnew.VECTOR2I(pcbnew.FromMM(x1 - x0), pcbnew.FromMM(y1 - y0)))
F_SILK, F_MASK, F_CU, F_CRT, EDGE = pcbnew.F_SilkS, pcbnew.F_Mask, pcbnew.F_Cu, pcbnew.F_CrtYd, pcbnew.Edge_Cuts
mark, silk, mask, crt, edge, cu_text = [], [], [], [], [], []
for d in b.GetDrawings():
    lay = d.GetLayer()
    if lay == EDGE:
        edge += item_poly(d, EDGE)
        continue
    if lay != F_SILK or not d.GetBoundingBox().Intersects(win):
        continue
    txt = d.GetText() if hasattr(d, "GetText") and d.GetClass() in ("PCB_TEXT", "PTEXT") else None
    rec = {"kind": d.GetClass(), "text": txt, "poly": item_poly(d, F_SILK)}
    if txt and (txt.startswith("BANK FIT") or txt.startswith("H  B32643H") or txt.startswith("B  B32643B")):
        rec["size_mm"] = d.GetTextHeight() * MM
        rec["stroke_mm"] = d.GetTextThickness() * MM
        mark.append(rec)
    elif d.GetClass() == "PCB_SHAPE":
        bb = d.GetBoundingBox()
        rec["bbox"] = [bb.GetX() * MM, bb.GetY() * MM, bb.GetRight() * MM, bb.GetBottom() * MM]
        rec["stroke_mm"] = d.GetWidth() * MM
        silk.append(rec)
    else:
        silk.append(rec)
for fp in b.GetFootprints():
    ref = fp.GetReference()
    for p in fp.Pads():
        if p.GetBoundingBox().Intersects(win) and (p.IsOnLayer(F_MASK) or p.IsOnLayer(F_CU)):
            mask.append({"ref": ref, "pad": p.GetNumber(), "poly": item_poly(p, F_MASK if p.IsOnLayer(F_MASK) else F_CU)})
    for g in fp.GraphicalItems():
        if not g.GetBoundingBox().Intersects(win):
            continue
        if g.GetLayer() == F_SILK:
            silk.append({"ref": ref, "kind": g.GetClass(), "poly": item_poly(g, F_SILK)})
        elif g.GetLayer() == F_CRT:
            crt.append({"ref": ref, "poly": item_poly(g, F_CRT)})
        elif g.GetLayer() == F_MASK:
            mask.append({"ref": ref, "pad": "graphic", "poly": item_poly(g, F_MASK)})
    for t in (fp.Reference(), fp.Value()):
        if t.IsVisible() and t.GetLayer() == F_SILK and t.GetBoundingBox().Intersects(win):
            silk.append({"ref": ref, "kind": "field", "poly": item_poly(t, F_SILK)})
    cy = fp.GetCourtyard(F_CRT)
    if cy.OutlineCount() and fp.GetBoundingBox().Intersects(win):
        crt.append({"ref": ref, "poly": polys(cy), "courtyard": True})
for d in b.GetDrawings():
    if d.GetLayer() == F_MASK and d.GetBoundingBox().Intersects(win):
        mask.append({"ref": "board", "pad": "graphic", "poly": item_poly(d, F_MASK)})
print(json.dumps({"mark": mark, "silk": silk, "mask": mask, "courtyards": crt, "edge": edge}))
