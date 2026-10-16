import pcbnew, json, sys
B=sys.argv[1]; out=sys.argv[2]
b=pcbnew.LoadBoard(B)
mm=lambda v: round(v/1e6,3)
fps=[]
for f in b.GetFootprints():
    bb=f.GetBoundingBox(False)  # without text
    cy=None
    try:
        for side in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            poly=f.GetCourtyard(side)
            if poly.OutlineCount():
                r=poly.BBox(); cy=[mm(r.GetX()),mm(r.GetY()),mm(r.GetRight()),mm(r.GetBottom())]
    except Exception as e: pass
    pads=[]
    for p in f.Pads():
        pads.append(dict(n=p.GetNumber(),net=p.GetNetname(),x=mm(p.GetPosition().x),y=mm(p.GetPosition().y),
            sx=mm(p.GetSize(pcbnew.F_Cu).x) if hasattr(p,'GetSize') else None, sy=mm(p.GetSize(pcbnew.F_Cu).y),
            drill=mm(p.GetDrillSize().x), th=p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH))
    fps.append(dict(ref=f.GetReference(),val=f.GetValue(),lib=str(f.GetFPID().GetUniStringLibId()),
        layer=b.GetLayerName(f.GetLayer()),x=mm(f.GetPosition().x),y=mm(f.GetPosition().y),rot=f.GetOrientationDegrees(),
        bbox=[mm(bb.GetX()),mm(bb.GetY()),mm(bb.GetRight()),mm(bb.GetBottom())],crt=cy,pads=pads))
zones=[]
for z in b.Zones():
    r=z.GetBoundingBox()
    zones.append(dict(net=z.GetNetname(),name=z.GetZoneName(),layers=[b.GetLayerName(l) for l in z.GetLayerSet().Seq()],
        prio=z.GetAssignedPriority(),keepout=z.GetIsRuleArea(),bbox=[mm(r.GetX()),mm(r.GetY()),mm(r.GetRight()),mm(r.GetBottom())],
        outline=[[mm(z.Outline().CVertex(i).x),mm(z.Outline().CVertex(i).y)] for i in range(z.Outline().TotalVertices())],
        clear=mm(z.GetLocalClearance() or 0) if hasattr(z,'GetLocalClearance') else None))
tracks=[]
for t in b.GetTracks():
    row=dict(c=t.GetClass(),layer=b.GetLayerName(t.GetLayer()),s=[mm(t.GetStart().x),mm(t.GetStart().y)],e=[mm(t.GetEnd().x),mm(t.GetEnd().y)],w=mm(t.GetWidth()),net=t.GetNetname())
    tracks.append(row)
dr=[]
for d in b.GetDrawings():
    r=d.GetBoundingBox()
    dr.append(dict(c=d.GetClass(),layer=b.GetLayerName(d.GetLayer()),bbox=[mm(r.GetX()),mm(r.GetY()),mm(r.GetRight()),mm(r.GetBottom())],txt=d.GetText() if hasattr(d,'GetText') else None))
json.dump(dict(fps=fps,zones=zones,tracks=tracks,drawings=dr),open(out,'w'))
print(len(fps),len(zones),len(tracks),len(dr))
