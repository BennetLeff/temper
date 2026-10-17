import sys, json, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
out = {}
bb = b.GetBoardEdgesBoundingBox()
out["board_bbox_mm"] = [pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())]
fps = []
for f in b.GetFootprints():
    p = f.GetPosition()
    cb = f.GetCourtyard(pcbnew.F_CrtYd) if hasattr(f,'GetCourtyard') else None
    bbx = f.GetBoundingBox(False, False) if True else None
    pads = []
    for pad in f.Pads():
        pp = pad.GetPosition()
        pads.append([pad.GetNumber(), pad.GetNetname(), round(pcbnew.ToMM(pp.x),3), round(pcbnew.ToMM(pp.y),3)])
    fps.append(dict(ref=f.GetReference(), val=f.GetValue(), fpid=str(f.GetFPID().GetLibItemName()),
        x=round(pcbnew.ToMM(p.x),3), y=round(pcbnew.ToMM(p.y),3), rot=f.GetOrientationDegrees(),
        layer=f.GetLayerName(),
        bbox=[round(pcbnew.ToMM(v),3) for v in (bbx.GetLeft(), bbx.GetTop(), bbx.GetRight(), bbx.GetBottom())],
        pads=pads))
out["footprints"] = fps
nets = sorted(set(n for n in [b.GetNetInfo().GetNetItem(i).GetNetname() for i in range(b.GetNetCount())]))
out["nets"] = nets
json.dump(out, open(sys.argv[2],"w"), indent=0)
print(out["board_bbox_mm"], len(fps), len(nets))
