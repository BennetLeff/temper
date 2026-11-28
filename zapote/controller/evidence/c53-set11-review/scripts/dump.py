# dump board geometry to JSON (KiCad frame, mm)
import pcbnew, json, sys
b=pcbnew.LoadBoard('drc/controller.kicad_pcb')
mm=lambda v: v/1e6
out={'tracks':[],'vias':[],'pads':[],'fps':[],'zones':[],'drawings':[]}
for t in b.GetTracks():
    if t.GetClass()=='PCB_VIA':
        out['vias'].append(dict(x=mm(t.GetX()),y=mm(t.GetY()),net=t.GetNetname(),d=mm(t.GetWidth(pcbnew.F_Cu)),drill=mm(t.GetDrillValue()),free=t.GetIsFree() if hasattr(t,'GetIsFree') else None, top=b.GetLayerName(t.TopLayer()),bot=b.GetLayerName(t.BottomLayer())))
    else:
        out['tracks'].append(dict(x1=mm(t.GetStart().x),y1=mm(t.GetStart().y),x2=mm(t.GetEnd().x),y2=mm(t.GetEnd().y),w=mm(t.GetWidth()),layer=b.GetLayerName(t.GetLayer()),net=t.GetNetname(),cls=t.GetClass()))
for f in b.GetFootprints():
    bb=f.GetBoundingBox(False)
    try: cy=f.GetCourtyard(pcbnew.F_CrtYd).BBox(); cyb=[mm(cy.GetLeft()),mm(cy.GetTop()),mm(cy.GetRight()),mm(cy.GetBottom())]
    except Exception as e: cyb=None
    out['fps'].append(dict(ref=f.GetReference(),val=f.GetValue(),fpid=f.GetFPID().GetUniStringLibId(),x=mm(f.GetX()),y=mm(f.GetY()),rot=f.GetOrientationDegrees(),layer=b.GetLayerName(f.GetLayer()),attr=f.GetAttributes(),bbox=[mm(bb.GetLeft()),mm(bb.GetTop()),mm(bb.GetRight()),mm(bb.GetBottom())],cy=cyb,
      fields={fl.GetName():fl.GetText() for fl in f.GetFields()}))
    for p in f.Pads():
        out['pads'].append(dict(ref=f.GetReference(),num=p.GetNumber(),net=p.GetNetname(),x=mm(p.GetX()),y=mm(p.GetY()),sx=mm(p.GetSizeX()),sy=mm(p.GetSizeY()),rot=p.GetOrientationDegrees(),shape=p.GetShape(),attr=p.GetAttribute(),drill=mm(p.GetDrillSizeX()),drilly=mm(p.GetDrillSizeY()),layers=[b.GetLayerName(l) for l in p.GetLayerSet().Seq() if 'Cu' in b.GetLayerName(l)],pinfn=p.GetPinFunction(),
         bb=[mm(p.GetBoundingBox().GetLeft()),mm(p.GetBoundingBox().GetTop()),mm(p.GetBoundingBox().GetRight()),mm(p.GetBoundingBox().GetBottom())]))
for z in b.Zones():
    zz=dict(name=z.GetZoneName(),net=z.GetNetname(),layers=[b.GetLayerName(l) for l in z.GetLayerSet().Seq()],prio=z.GetAssignedPriority(),keepout=z.GetIsRuleArea(),clear=mm(z.GetLocalClearance() or 0),minw=mm(z.GetMinThickness()),conn=z.GetPadConnection(),island=z.GetIslandRemovalMode(),fills={},outline=[])
    o=z.Outline()
    for i in range(o.OutlineCount()):
        ol=o.Outline(i); zz['outline'].append([[mm(ol.CPoint(k).x),mm(ol.CPoint(k).y)] for k in range(ol.PointCount())])
    if not z.GetIsRuleArea():
        for l in z.GetLayerSet().Seq():
            ps=z.GetFilledPolysList(l); polys=[]
            for i in range(ps.OutlineCount()):
                ol=ps.Outline(i); ext=[[mm(ol.CPoint(k).x),mm(ol.CPoint(k).y)] for k in range(ol.PointCount())]
                holes=[]
                for h in range(ps.HoleCount(i)):
                    hl=ps.Hole(i,h); holes.append([[mm(hl.CPoint(k).x),mm(hl.CPoint(k).y)] for k in range(hl.PointCount())])
                polys.append([ext,holes])
            zz['fills'][b.GetLayerName(l)]=polys
    out['zones'].append(zz)
for d in b.GetDrawings():
    s=dict(cls=d.GetClass(),layer=b.GetLayerName(d.GetLayer()))
    if d.GetClass()=='PCB_SHAPE':
        s.update(shape=d.ShowShape(),x1=mm(d.GetStart().x),y1=mm(d.GetStart().y),x2=mm(d.GetEnd().x),y2=mm(d.GetEnd().y))
        if d.ShowShape()=='Circle': s['r']=mm(d.GetRadius())
    elif hasattr(d,'GetText'): s.update(text=d.GetText(),x=mm(d.GetX()),y=mm(d.GetY()))
    out['drawings'].append(s)
ds=b.GetDesignSettings()
out['setup']=dict(minclr=mm(ds.m_MinClearance),minw=mm(ds.m_TrackMinWidth),edge=mm(ds.m_CopperEdgeClearance),h2h=mm(ds.m_HoleToHoleMin),hclr=mm(ds.m_HoleClearance),thick=mm(ds.GetBoardThickness()))
json.dump(out,open('board.json','w'))
print({k:len(v) if hasattr(v,'__len__') else v for k,v in out.items()})
