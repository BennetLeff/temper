"""Exposed-copper (ENIG) area of a board: union of solder-mask openings on F and B, over the board area.
    KPY enig_area.py board.kicad_pcb"""
import sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
outl = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outl, True)
board_mm2 = outl.Area() / 1e12
res = {}
for lname, lid in (("F", pcbnew.F_Mask), ("B", pcbnew.B_Mask)):
    ps = pcbnew.SHAPE_POLY_SET()
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.IsOnLayer(lid):
                p.TransformShapeToPolygon(ps, lid, p.GetSolderMaskExpansion(lid), 5000, pcbnew.ERROR_INSIDE)
        for g in fp.GraphicalItems():
            if g.GetLayer() == lid:
                g.TransformShapeToPolygon(ps, lid, 0, 5000, pcbnew.ERROR_INSIDE)
    for d in b.GetDrawings():
        if d.GetLayer() == lid:
            d.TransformShapeToPolygon(ps, lid, 0, 5000, pcbnew.ERROR_INSIDE)
    for z in b.Zones():
        if z.IsOnLayer(lid):
            ps.Append(z.Outline())
    ps.Simplify()
    res[lname] = ps.Area() / 1e12
tot = res["F"] + res["B"]
print(f"board {board_mm2:.0f} mm2; mask openings F {res['F']:.0f} B {res['B']:.0f} mm2; "
      f"ENIG share of top+bottom = {100*tot/(2*board_mm2):.1f} % (JLC surcharge above 30 %)")
