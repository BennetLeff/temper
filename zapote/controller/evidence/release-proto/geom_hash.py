#!/usr/bin/env python3
"""Hash the copper and placement of a KiCad board, ignoring Value/MPN text fields.

    KiCad python:  geom_hash.py <board.kicad_pcb>   -> JSON with per-class sha256 and a total
Classes: footprints (ref, layer, position, rotation, pad positions/sizes/nets), tracks, vias,
zones (layer, net, outline, filled polygons), board edge and graphics. Value/MPN excluded on purpose.
"""
import hashlib, json, sys
import pcbnew

def h(rows):
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()

def poly(ps):
    return [(p.x, p.y) for i in range(ps.OutlineCount()) for j in range(ps.COutline(i).PointCount()) for p in [ps.COutline(i).CPoint(j)]]

b = pcbnew.LoadBoard(sys.argv[1])
fps, pads, trk, vias, zones, gfx = [], [], [], [], [], []
for f in b.GetFootprints():
    p = f.GetPosition()
    fps.append(f"{f.GetReference()}|{f.GetLayerName()}|{p.x}|{p.y}|{f.GetOrientationDegrees():.4f}|{f.GetFPID().GetUniStringLibItemName()}")
    for pd in f.Pads():
        q = pd.GetPosition(); s = pd.GetSize(pcbnew.F_Cu)
        pads.append(f"{f.GetReference()}.{pd.GetNumber()}|{q.x}|{q.y}|{s.x}|{s.y}|{pd.GetNetname()}|{pd.GetLayerSet().FmtHex()}")
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        q = t.GetPosition()
        vias.append(f"{q.x}|{q.y}|{t.GetWidth(pcbnew.F_Cu)}|{t.GetDrill()}|{t.GetNetname()}|{t.TopLayer()}|{t.BottomLayer()}")
    else:
        a, e = t.GetStart(), t.GetEnd()
        trk.append(f"{t.GetLayerName()}|{a.x}|{a.y}|{e.x}|{e.y}|{t.GetWidth()}|{t.GetNetname()}|{t.GetClass()}")
for z in b.Zones():
    fills = []
    for l in z.GetLayerSet().Seq():
        if z.HasFilledPolysForLayer(l):
            fills.append(f"{l}:" + str(poly(z.GetFilledPolysList(l))))
    zones.append(f"{z.GetNetname()}|{z.GetLayerSet().FmtHex()}|{poly(z.Outline())}|{fills}")
for d in b.GetDrawings():
    bb = d.GetBoundingBox()
    gfx.append(f"{d.GetClass()}|{d.GetLayerName()}|{bb.GetX()}|{bb.GetY()}|{bb.GetWidth()}|{bb.GetHeight()}")
out = {k: {"n": len(v), "sha256": h(v)} for k, v in dict(footprints=fps, pads=pads, tracks=trk, vias=vias, zones=zones, drawings=gfx).items()}
out["copper_and_placement_sha256"] = hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()
print(json.dumps(out, indent=1))
