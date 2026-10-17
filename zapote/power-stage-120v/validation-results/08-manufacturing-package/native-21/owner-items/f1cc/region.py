import pcbnew, sys
b=pcbnew.LoadBoard(sys.argv[1])
mm=pcbnew.ToMM
bb=b.GetBoardEdgesBoundingBox()
print("edge bbox", mm(bb.GetX()),mm(bb.GetY()),mm(bb.GetRight()),mm(bb.GetBottom()))
X0,X1,Y0,Y1=[float(v) for v in sys.argv[2:6]]
for fp in b.GetFootprints():
    r=fp.GetBoundingBox(False)
    x0,y0,x1,y1=mm(r.GetX()),mm(r.GetY()),mm(r.GetRight()),mm(r.GetBottom())
    if x1<X0 or x0>X1 or y1<Y0 or y0>Y1: continue
    cy=fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else None
    cys=f"crtyd F {mm(cy.GetX()):.2f},{mm(cy.GetY()):.2f}..{mm(cy.GetRight()):.2f},{mm(cy.GetBottom()):.2f}" if cy else ""
    cb=fp.GetCourtyard(pcbnew.B_CrtYd)
    if cb.OutlineCount():
        c=cb.BBox(); cys+=f" B {mm(c.GetX()):.2f},{mm(c.GetY()):.2f}..{mm(c.GetRight()):.2f},{mm(c.GetBottom()):.2f}"
    p=fp.GetPosition()
    print(f"{fp.GetReference():6s} {fp.GetValue()[:22]:22s} {fp.GetFPIDAsString()[:60]:60s} pos {mm(p.x):.2f},{mm(p.y):.2f} rot {fp.GetOrientationDegrees():.0f} {'B' if fp.IsFlipped() else 'F'} bbox {x0:.2f},{y0:.2f}..{x1:.2f},{y1:.2f} {cys}")
    for pad in fp.Pads():
        pp=pad.GetPosition(); s=pad.GetSize()
        print(f"     pad {pad.GetNumber():3s} {pad.GetNetname()[:20]:20s} {mm(pp.x):.2f},{mm(pp.y):.2f} size {mm(s.x):.2f}x{mm(s.y):.2f} drill {mm(pad.GetDrillSize().x):.2f}")
