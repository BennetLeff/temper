import pcbnew, sys
b=pcbnew.LoadBoard(sys.argv[1]); mm=pcbnew.ToMM
want=sys.argv[2].split(",")
for z in b.Zones():
    if z.GetNetname() not in want: continue
    o=z.Outline()
    lay=",".join(b.GetLayerName(l) for l in z.GetLayerSet().Seq())
    print("ZONE",z.GetNetname(),lay,"prio",z.GetAssignedPriority(),"clr",mm(z.GetLocalClearance() or 0) if hasattr(z,'GetLocalClearance') else '', "minw",mm(z.GetMinThickness()))
    for i in range(o.OutlineCount()):
        ch=o.Outline(i)
        pts=[(round(mm(ch.CPoint(k).x),2),round(mm(ch.CPoint(k).y),2)) for k in range(ch.PointCount())]
        print("  outline",pts[:60])
