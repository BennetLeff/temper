"""KiCad Python half of copper_delta.sh: analog-net items (exact) and GND fills (polygons) of two boards."""

import json
import os
import sys

import pcbnew

ANALOG = set(os.environ["ANALOG"].split(","))


def dump(path):
    b = pcbnew.LoadBoard(path)
    items, fills, segs = [], {}, []
    for t in b.GetTracks():
        if t.GetNetname() in ANALOG:
            w = t.GetWidth(pcbnew.F_Cu) if t.Type() == pcbnew.PCB_VIA_T else t.GetWidth()
            items.append([t.GetNetname(), t.GetLayer(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, w])
            segs.append([[t.GetStart().x / 1e6, t.GetStart().y / 1e6], [t.GetEnd().x / 1e6, t.GetEnd().y / 1e6]])
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() in ANALOG:
                items.append([fp.GetReference(), p.GetNumber(), p.GetPosition().x, p.GetPosition().y])
                c = [p.GetPosition().x / 1e6, p.GetPosition().y / 1e6]
                segs.append([c, [c[0] + 1e-6, c[1]]])
    for z in b.Zones():
        if z.GetNetname() in ANALOG:
            items.append(["zone", z.GetNetname(), z.GetLayer(), z.IsTeardropArea(), round(z.GetFilledArea())])
        if z.GetNetname() == "GND" and not z.IsTeardropArea():
            for layer in z.GetLayerSet().CuStack():
                ps = z.GetFilledPolysList(layer)
                for i in range(ps.OutlineCount()):
                    o = ps.Outline(i)
                    holes = [ps.Hole(i, k) for k in range(ps.HoleCount(i))]
                    fills.setdefault(b.GetLayerName(layer), []).append(
                        {
                            "o": [[o.CPoint(j).x / 1e6, o.CPoint(j).y / 1e6] for j in range(o.PointCount())],
                            "h": [[[h.CPoint(j).x / 1e6, h.CPoint(j).y / 1e6] for j in range(h.PointCount())] for h in holes],
                        }
                    )
    return {"items": sorted(map(json.dumps, items)), "fills": fills, "analog_segments": segs}


json.dump({"ref": dump(sys.argv[1]), "new": dump(sys.argv[2])}, open(sys.argv[3], "w"))
