"""Edge-to-edge plan distance from proposed THT pads (circle r) to other-net copper per layer, and to board edge / holes.
   KPY dist.py BOARD points.json  (points: [[name, net, x, y, r_pad], ...])"""
import pcbnew, sys, json, math
b = pcbnew.LoadBoard(sys.argv[1]); pts = json.load(open(sys.argv[2]))
MM = 1e6
cu = [l for l in b.GetEnabledLayers().CuStack()]
objs = []  # (layer, net, kind, shape_poly)
for z in b.Zones():
    if z.GetIsRuleArea(): continue
    for L in z.GetLayerSet().Seq():
        fp = z.GetFilledPolysList(L)
        if fp and fp.OutlineCount(): objs.append((b.GetLayerName(L), z.GetNetname(), "zone:" + z.GetZoneName(), fp))
for t in b.GetTracks():
    for L in (t.GetLayerSet().Seq() if t.GetClass() == "PCB_VIA" else [t.GetLayer()]):
        if L not in cu: continue
        s = pcbnew.SHAPE_POLY_SET(); t.TransformShapeToPolygon(s, L, 0, 5000, pcbnew.ERROR_INSIDE)
        objs.append((b.GetLayerName(L), t.GetNetname(), t.GetClass()[4:], s))
for f in b.GetFootprints():
    for p in f.Pads():
        for L in p.GetLayerSet().Seq():
            if L not in cu: continue
            s = pcbnew.SHAPE_POLY_SET(); p.TransformShapeToPolygon(s, L, 0, 5000, pcbnew.ERROR_INSIDE)
            objs.append((b.GetLayerName(L), p.GetNetname(), "pad:" + f.GetReference() + "." + p.GetNumber(), s))
        if p.GetDrillSize().x > 0 and p.GetNetname() == "":
            objs.append(("HOLE", "", "npth:" + f.GetReference(), None, p.GetPosition(), p.GetDrillSize().x / 2))
edge = b.GetBoardEdgesBoundingBox()
res = []
for name, net, x, y, r in pts:
    P = pcbnew.VECTOR2I(int(x * MM), int(y * MM)); best = {}
    for o in objs:
        if o[0] == "HOLE":
            dd = math.hypot(o[4].x - P.x, o[4].y - P.y) / MM - o[5] / MM - r; key = ("HOLE", o[2])
        else:
            L, n, k, s = o
            if n == net: continue
            dd = math.sqrt(s.SquaredDistance(P, False)) / MM - r
            if dd > 40: continue
            key = (L, n)
        if key not in best or dd < best[key][0]: best[key] = (round(dd, 3), o[2] if o[0] != "HOLE" else "")
    # L-shaped outline: main 0-290 x 0-140, tab 0-91 x 140-190
    de = min(x, 290 - x, y, (140 - y) if x > 91 else (190 - y)) - r
    res.append(dict(pt=name, net=net, x=x, y=y, edge=round(de, 3),
                    near=sorted([[d[0], k[0], k[1], d[1]] for k, d in best.items()])[:14]))
print(json.dumps(res, indent=1))
