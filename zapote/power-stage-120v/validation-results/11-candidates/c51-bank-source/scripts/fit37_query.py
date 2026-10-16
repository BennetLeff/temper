"""Read-only query of the s51 board for the P37.5 column-left fit (KiCad python, -I).
   KPY -I scripts/fit37_query.py BOARD OUT.json
Dumps: bank footprints (C21-C23, C151, C152) pads; every footprint whose courtyard/bbox intersects x 140-200, y 40-130;
nets of zones / tracks crossing x 145-163, y 40-125 (the strip extension band)."""
import pcbnew, sys, json
b = pcbnew.LoadBoard(sys.argv[1]); MM = 1e6
mm = lambda v: round(v / MM, 3)
out = {"bank": {}, "fps_near": [], "copper_band": {}}
for f in b.GetFootprints():
    ref = f.GetReference()
    cy = None
    for side in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        try:
            poly = f.GetCourtyard(side)
            if poly.OutlineCount():
                r = poly.BBox(); cy = [mm(r.GetX()), mm(r.GetY()), mm(r.GetRight()), mm(r.GetBottom())]
        except Exception:
            pass
    bb = f.GetBoundingBox(False); box = cy or [mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())]
    pads = [dict(n=p.GetNumber(), net=p.GetNetname(), x=mm(p.GetPosition().x), y=mm(p.GetPosition().y)) for p in f.Pads()]
    if ref in ("C21", "C22", "C23", "C151", "C152"):
        out["bank"][ref] = dict(box=box, pads=pads, lib=str(f.GetFPID().GetUniStringLibId()))
    elif box[2] > 140 and box[0] < 200 and box[3] > 40 and box[1] < 130:
        out["fps_near"].append(dict(ref=ref, val=f.GetValue(), box=box, layer=b.GetLayerName(f.GetLayer()),
                                    nets=sorted({p["net"] for p in pads})))
band = pcbnew.BOX2I(pcbnew.VECTOR2I(int(145 * MM), int(40 * MM)), pcbnew.VECTOR2I(int(18 * MM), int(85 * MM)))
for z in b.Zones():
    if z.GetIsRuleArea():
        continue
    for L in z.GetLayerSet().Seq():
        fp = z.GetFilledPolysList(L)
        if fp and fp.OutlineCount() and fp.BBox().Intersects(band):
            out["copper_band"].setdefault(b.GetLayerName(L), set()).add("zone:" + z.GetNetname() + ":" + z.GetZoneName())
for t in b.GetTracks():
    if t.GetBoundingBox().Intersects(band):
        out["copper_band"].setdefault(b.GetLayerName(t.GetLayer()), set()).add(t.GetClass()[4:] + ":" + t.GetNetname())
out["copper_band"] = {k: sorted(v) for k, v in out["copper_band"].items()}
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(json.dumps(out["bank"], indent=0)[:1500]); print(len(out["fps_near"]))
