"""M11: measure the sink-row geometry of native-21 stage 11 against the sink face.

Run with KiCad 10's Python (read-only on the board):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      board_sink_geometry.py <section.kicad_pcb> <out.json>

Sink face model (enclosure R25, src/electronics_r17.py + electronics_r21.py):
  world = (141 - x, 236 - y, 26 + z); sink envelope X32..149, Y236..284, Z15.5..83 with its
  vertical base at Y236..240. In board coordinates the sink face is the plane y = 0 for
  board x in [141-149, 141-32] = [-8, 109], spanning z = 15.5-26 .. 83-26 = -10.5 .. 57 mm,
  i.e. it covers the whole board edge thickness. y < 0 is sink metal (PE).

Outputs: per sink-row part, pad/net/position/drill and F.Fab extent in y (tab face), and per
layer per net the minimum distance of copper to y = 0 within the sink span.
"""
import json
import sys

import pcbnew

SINK_X = (-8.0, 109.0)
NM = 1e-6


def mm(v):
    return v * NM


def main(path, out):
    b = pcbnew.LoadBoard(path)
    res = {"board": path, "sink_face": "board y = 0, x in [-8, 109], z -10.5..57 (R25 pose)", "parts": {}, "edge_copper": {}}
    # Board outline extent
    eb = b.GetBoardEdgesBoundingBox()
    res["edge_bbox_mm"] = [mm(eb.GetLeft()), mm(eb.GetTop()), mm(eb.GetRight()), mm(eb.GetBottom())]
    hot_like = set()
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref not in ("Q2", "Q3", "Q5", "Q6", "BR1"):
            continue
        pos = fp.GetPosition()
        info = {"value": fp.GetValue(), "fpid": str(fp.GetFPID().GetUniStringLibItemName()),
                "pos_mm": [mm(pos.x), mm(pos.y)], "rot_deg": fp.GetOrientationDegrees(),
                "layer": fp.GetLayerName(), "pads": []}
        for p in fp.Pads():
            c = p.GetPosition()
            sz = p.GetSize()
            info["pads"].append({"num": p.GetNumber(), "net": p.GetNetname(), "xy_mm": [mm(c.x), mm(c.y)],
                                 "size_mm": [mm(sz.x), mm(sz.y)], "drill_mm": mm(p.GetDrillSize().x),
                                 "pad_edge_to_y0_mm": mm(c.y) - max(mm(sz.x), mm(sz.y)) / 2})
            hot_like.add(p.GetNetname())
        ys, xs = [], []
        for g in fp.GraphicalItems():
            if g.GetLayerName() in ("F.Fab",):
                bb = g.GetBoundingBox()
                ys += [mm(bb.GetTop()), mm(bb.GetBottom())]
                xs += [mm(bb.GetLeft()), mm(bb.GetRight())]
        if ys:
            info["fab_bbox_mm"] = [min(xs), min(ys), max(xs), max(ys)]
        res["parts"][ref] = info
    # Copper near the sink face, inside the sink span
    layers = {}
    def note(layer, net, d, where):
        key = (layer, net)
        if key not in layers or d < layers[key][0]:
            layers[key] = (d, where)
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition(); r = mm(t.GetWidth(pcbnew.F_Cu)) / 2
            x, y = mm(p.x), mm(p.y)
            if SINK_X[0] <= x <= SINK_X[1]:
                note("via", t.GetNetname(), y - r, [x, y])
            continue
        for p in (t.GetStart(), t.GetEnd()):
            x, y = mm(p.x), mm(p.y)
            if SINK_X[0] <= x <= SINK_X[1]:
                note(t.GetLayerName(), t.GetNetname(), y - mm(t.GetWidth()) / 2, [x, y])
    for z in b.Zones():
        if z.GetIsRuleArea():
            continue
        for lid in z.GetLayerSet().Seq():
            poly = z.GetFilledPolysList(lid)
            if poly is None:
                continue
            for i in range(poly.OutlineCount()):
                ol = poly.Outline(i)
                for k in range(ol.PointCount()):
                    pt = ol.CPoint(k)
                    x, y = mm(pt.x), mm(pt.y)
                    if SINK_X[0] <= x <= SINK_X[1]:
                        note(b.GetLayerName(lid), z.GetNetname(), y, [x, y])
    for fp in b.GetFootprints():
        for p in fp.Pads():
            c = p.GetPosition(); x, y = mm(c.x), mm(c.y)
            if SINK_X[0] <= x <= SINK_X[1]:
                sz = p.GetSize()
                note("pad", p.GetNetname(), y - max(mm(sz.x), mm(sz.y)) / 2, [x, y, fp.GetReference()])
    for (layer, net), (d, where) in sorted(layers.items(), key=lambda kv: kv[1][0]):
        if d > 12:
            continue
        res["edge_copper"].setdefault(layer, {})[net] = {"min_dist_to_y0_mm": round(d, 3), "at": where}
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res["parts"], indent=1)[:4000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
