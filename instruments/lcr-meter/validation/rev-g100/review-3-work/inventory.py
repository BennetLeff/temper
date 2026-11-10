import pcbnew, json, sys
b = pcbnew.LoadBoard('cad/temper-lcr.kicad_pcb')
out = {}
fps = []
for fp in b.GetFootprints():
    p = fp.GetPosition()
    bb = fp.GetBoundingBox(False, False)
    fps.append(dict(ref=fp.GetReference(), val=fp.GetValue(), fpid=str(fp.GetFPID().GetLibItemName()),
        x=p.x/1e6, y=p.y/1e6, rot=fp.GetOrientationDegrees(), layer=b.GetLayerName(fp.GetLayer()),
        w=bb.GetWidth()/1e6, h=bb.GetHeight()/1e6,
        pads=[dict(n=pd.GetNumber(), net=pd.GetNetname(), x=pd.GetPosition().x/1e6, y=pd.GetPosition().y/1e6,
                   sx=pd.GetSize().x/1e6, sy=pd.GetSize().y/1e6, drill=pd.GetDrillSize().x/1e6,
                   layers=[b.GetLayerName(l) for l in pd.GetLayerSet().Seq()][:3], attr=int(pd.GetAttribute())) for pd in fp.Pads()]))
fps.sort(key=lambda f: f['ref'])
out['footprints'] = fps
tracks = []
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA':
        tracks.append(dict(type='via', net=t.GetNetname(), x=t.GetPosition().x/1e6, y=t.GetPosition().y/1e6, drill=t.GetDrillValue()/1e6, dia=t.GetWidth(pcbnew.F_Cu)/1e6))
    else:
        tracks.append(dict(type='track', net=t.GetNetname(), layer=b.GetLayerName(t.GetLayer()), x1=t.GetStart().x/1e6, y1=t.GetStart().y/1e6, x2=t.GetEnd().x/1e6, y2=t.GetEnd().y/1e6, w=t.GetWidth()/1e6))
out['tracks'] = tracks
zones = []
for z in b.Zones():
    zones.append(dict(net=z.GetNetname(), layers=[b.GetLayerName(l) for l in z.GetLayerSet().Seq()], name=z.GetZoneName(),
        prio=z.GetAssignedPriority(), filled=z.IsFilled(), minw=z.GetMinThickness()/1e6, clearance=z.GetLocalClearance()/1e6 if hasattr(z,'GetLocalClearance') else None,
        bbox=[z.GetBoundingBox().GetLeft()/1e6, z.GetBoundingBox().GetTop()/1e6, z.GetBoundingBox().GetRight()/1e6, z.GetBoundingBox().GetBottom()/1e6],
        keepout=z.GetIsRuleArea(), area=sum(z.GetFilledArea() for _ in [0]) if hasattr(z,'GetFilledArea') else None))
out['zones'] = zones
nets = {}
for n in b.GetNetInfo().NetsByName():
    nets[str(n)] = 1
out['nets'] = sorted(nets)
json.dump(out, open('work/inventory.json','w'), indent=1)
print(len(fps), 'footprints', len(tracks), 'tracks+vias', len(zones), 'zones', len(nets), 'nets')
for z in zones: print(z)
