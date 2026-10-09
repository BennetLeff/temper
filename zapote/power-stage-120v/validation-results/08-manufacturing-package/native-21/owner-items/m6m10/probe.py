import pcbnew, sys, math
b=pcbnew.LoadBoard(sys.argv[1])
mm=pcbnew.ToMM
for r in ['J2','J5','J4','J6','T1','C21','C22','C23','C6','C5','J1','J3','PS1','PS2','R22','R23','R24','R25']:
    f=b.FindFootprintByReference(r)
    if not f: print(r,'missing'); continue
    p=f.GetPosition(); bb=f.GetBoundingBox(False)
    print(r,f.GetFPID().GetLibItemName(),f.GetValue(),'pos',round(mm(p.x),2),round(mm(p.y),2),'rot',f.GetOrientationDegrees(),'layer',f.GetLayerName(),
      'bbox',round(mm(bb.GetLeft()),2),round(mm(bb.GetTop()),2),round(mm(bb.GetRight()),2),round(mm(bb.GetBottom()),2))
    if r in ('J2','J5','J4'):
        for pd in f.Pads():
            q=pd.GetPosition(); s=pd.GetSize()
            print('   pad',pd.GetNumber(),pd.GetNetname(),round(mm(q.x),2),round(mm(q.y),2),'size',round(mm(s.x),2),round(mm(s.y),2),'drill',round(mm(pd.GetDrillSize().x),2),pd.GetShape(),pd.GetAttribute())
e=b.GetBoardEdgesBoundingBox(); print('edges',mm(e.GetLeft()),mm(e.GetTop()),mm(e.GetRight()),mm(e.GetBottom()))
for d in b.GetDrawings():
    if d.GetLayerName()=='Edge.Cuts':
        print('edge',d.GetShapeStr(),[ (round(mm(p.x),2),round(mm(p.y),2)) for p in ([d.GetStart(),d.GetEnd()])])
