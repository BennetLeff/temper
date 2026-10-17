import pcbnew, sys
b=pcbnew.LoadBoard(sys.argv[1]); mm=pcbnew.ToMM
X0,X1,Y0,Y1=map(float,sys.argv[2:6])
ds=b.GetDesignSettings()
print("thickness",mm(ds.GetBoardThickness()),"edge clr",mm(ds.m_CopperEdgeClearance), "hole clr", mm(ds.m_HoleClearance), "hole2hole", mm(ds.m_HoleToHoleMin))
print("layers", b.GetCopperLayerCount())
for t in b.GetTracks():
    bb=t.GetBoundingBox(); x0,y0,x1,y1=mm(bb.GetX()),mm(bb.GetY()),mm(bb.GetRight()),mm(bb.GetBottom())
    if x1<X0 or x0>X1 or y1<Y0 or y0>Y1: continue
    if t.GetClass()=="PCB_VIA":
        print(f"VIA {t.GetNetname():12s} {mm(t.GetPosition().x):.2f},{mm(t.GetPosition().y):.2f} d{mm(t.GetWidth(pcbnew.F_Cu)):.2f}")
    else:
        print(f"TRK {b.GetLayerName(t.GetLayer()):5s} {t.GetNetname():12s} {mm(t.GetStart().x):.2f},{mm(t.GetStart().y):.2f} -> {mm(t.GetEnd().x):.2f},{mm(t.GetEnd().y):.2f} w{mm(t.GetWidth()):.2f}")
for z in b.Zones():
    bb=z.GetBoundingBox(); x0,y0,x1,y1=mm(bb.GetX()),mm(bb.GetY()),mm(bb.GetRight()),mm(bb.GetBottom())
    if x1<X0 or x0>X1 or y1<Y0 or y0>Y1: continue
    lay=",".join(b.GetLayerName(l) for l in z.GetLayerSet().Seq())
    print(f"ZONE {z.GetNetname() or ('KEEPOUT' if z.GetIsRuleArea() else '?'):12s} {lay:20s} bbox {x0:.1f},{y0:.1f}..{x1:.1f},{y1:.1f} filled_area={z.GetFilledArea()/1e12 if z.IsFilled() else 0:.0f}mm2")
for d in b.GetDrawings():
    bb=d.GetBoundingBox(); x0,y0,x1,y1=mm(bb.GetX()),mm(bb.GetY()),mm(bb.GetRight()),mm(bb.GetBottom())
    if x1<X0 or x0>X1 or y1<Y0 or y0>Y1: continue
    ln=b.GetLayerName(d.GetLayer())
    if ln in("Edge.Cuts","Dwgs.User","Cmts.User","Eco1.User","Eco2.User","User.1","User.2","F.Fab","B.Fab") or "Cu" in ln:
        print(f"DRAW {ln:10s} {d.GetClass()} bbox {x0:.1f},{y0:.1f}..{x1:.1f},{y1:.1f} {getattr(d,'GetText',lambda:'')()[:40] if d.GetClass()=='PCB_TEXT' else ''}")
