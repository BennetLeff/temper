"""Copper / items intersecting candidate rectangles (board mm). KiCad python, read-only."""
import pcbnew, sys, json, collections
b = pcbnew.LoadBoard(sys.argv[1])
rects = json.loads(sys.argv[2])   # {name: [x0,y0,x1,y1]}
MM = 1e6
def rect_poly(r):
    s = pcbnew.SHAPE_POLY_SET(); s.NewOutline()
    for x, y in ((r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])):
        s.Append(int(x * MM), int(y * MM))
    return s
out = {}
for name, r in rects.items():
    rp = rect_poly(r); res = collections.defaultdict(float)
    for z in b.Zones():
        if z.GetIsRuleArea(): continue
        for L in z.GetLayerSet().Seq():
            fp = z.GetFilledPolysList(L)
            if fp is None or fp.OutlineCount() == 0: continue
            c = fp.CloneDropTriangulation(); c.BooleanIntersection(rp)
            a = c.Area() / MM / MM
            if a > 0.5: res[f"{b.GetLayerName(L)}:{z.GetNetname()}:zone"] += a
    trk = collections.Counter()
    for t in b.GetTracks():
        bb = t.GetBoundingBox()
        if bb.GetRight() / MM > r[0] and bb.GetX() / MM < r[2] and bb.GetBottom() / MM > r[1] and bb.GetY() / MM < r[3]:
            trk[f"{t.GetClass()[4:]}:{b.GetLayerName(t.GetLayer()) if t.GetClass()!='PCB_VIA' else 'via'}:{t.GetNetname()}"] += 1
    fps = []
    for f in b.GetFootprints():
        for p in f.Pads():
            q = p.GetPosition()
            if r[0] < q.x / MM < r[2] and r[1] < q.y / MM < r[3]:
                fps.append(f.GetReference()); break
    kos = []
    for z in b.Zones():
        if not z.GetIsRuleArea(): continue
        bb = z.GetBoundingBox()
        if bb.GetRight() / MM > r[0] and bb.GetX() / MM < r[2] and bb.GetBottom() / MM > r[1] and bb.GetY() / MM < r[3]:
            kos.append(z.GetZoneName())
    out[name] = dict(rect=r, zones={k: round(v, 1) for k, v in sorted(res.items())}, tracks=dict(trk), pads_of=sorted(set(fps)), keepouts=kos)
print(json.dumps(out, indent=1))
