import pcbnew, sys
b=pcbnew.LoadBoard(sys.argv[1]); mm=pcbnew.ToMM
X0,Y0,X1,Y1=[float(v) for v in sys.argv[2:6]]
out=[]
for f in b.GetFootprints():
    try:
        cy=f.GetCourtyard(pcbnew.F_CrtYd); bb=cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False,False)
    except Exception: bb=f.GetBoundingBox(False,False)
    l,t,r,bo=mm(bb.GetLeft()),mm(bb.GetTop()),mm(bb.GetRight()),mm(bb.GetBottom())
    if r>X0 and l<X1 and bo>Y0 and t<Y1:
        nets=sorted({p.GetNetname() for p in f.Pads() if p.GetNetname()})
        out.append((t,l,f.GetReference(),f.GetValue(),round(l,1),round(t,1),round(r,1),round(bo,1),nets[:4]))
for o in sorted(out): print(*o[2:])
