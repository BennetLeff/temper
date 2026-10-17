#!/usr/bin/env python3
"""Refill a built board's zones and report the connections KiCad's connectivity leaves open, in kicad-cli DRC shape.

    KICAD_PY native-21/layout/gates/fast_conn.py BOARD.kicad_pcb OUT.json [--save]

~12 s against ~50-150 s for kicad-cli DRC (2026-10-15): no rule checks, only the zone refill and KiCad's own
connectivity. OUT.json is {"violations": [], "unconnected_items": [...]}, each item a pair of
{"description", "pos": {x, y}} written by KiCad (GetItemDescription), so incr21.py reads it as it reads a DRC.
Per net, the items are grouped into KiCad's connected clusters (zone fills included) and the clusters are joined by
a minimum spanning tree over their nearest anchors (pad centres, track ends, vias, zone outline corners): one pair
per missing link, clusters - 1 per net, as the DRC counts them. The pairs need not name the same items as the DRC's
ratsnest; incr21 joins clusters, not items. --save writes the refilled board back (plot_copper.py --dump then sees
the fills the new copper gets).
"""
import json
import math
import sys

import pcbnew  # type: ignore[import-not-found]

path, out = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(path)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.BuildConnectivity()
conn = b.GetConnectivity()
if "--save" in sys.argv:
    pcbnew.SaveBoard(path, b)
units = pcbnew.UNITS_PROVIDER(pcbnew.pcbIUScale, pcbnew.EDA_UNITS_MM)
mm = pcbnew.ToMM


def anchors(it):
    if isinstance(it, pcbnew.PAD) or isinstance(it, pcbnew.PCB_VIA):
        p = it.GetPosition()
        return [(mm(p.x), mm(p.y))]
    if isinstance(it, pcbnew.PCB_TRACK):
        return [(mm(it.GetStart().x), mm(it.GetStart().y)), (mm(it.GetEnd().x), mm(it.GetEnd().y))]
    if isinstance(it, pcbnew.ZONE):
        o = it.Outline().Outline(0)
        return [(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]
    return []


by_net = {}
for it in list(b.GetPads()) + list(b.GetTracks()) + list(b.Zones()):
    if it.GetNetCode() > 0:
        by_net.setdefault(it.GetNetCode(), []).append(it)

pairs = []
for code, items in sorted(by_net.items()):
    cluster = {}
    for it in items:
        k = it.m_Uuid.AsString()
        if k in cluster:
            continue
        cid = len({*cluster.values()})
        cluster[k] = cid
        for o in conn.GetConnectedItems(it):
            if o.GetNetCode() == code:
                cluster.setdefault(o.m_Uuid.AsString(), cid)
    groups = {}
    for it in items:
        groups.setdefault(cluster[it.m_Uuid.AsString()], []).append(it)
    if len(groups) < 2:
        continue
    # Prim over clusters; edge weight = nearest anchor pair
    pts = {g: [(a, it) for it in its for a in anchors(it)] for g, its in groups.items()}
    pts = {g: v for g, v in pts.items() if v}
    todo = sorted(pts)
    if len(todo) < 2:
        continue
    done = [todo.pop(0)]
    while todo:
        best = None
        for g in done:
            for h in todo:
                for (pa, ia) in pts[g]:
                    for (pb, ib) in pts[h]:
                        d = math.dist(pa, pb)
                        if best is None or d < best[0]:
                            best = (d, h, (pa, ia), (pb, ib))
        _, h, (pa, ia), (pb, ib) = best
        pairs.append({"type": "unconnected_items", "severity": "error", "description": "Missing connection between items",
                      "items": [{"description": ia.GetItemDescription(units, True), "pos": {"x": pa[0], "y": pa[1]}},
                                {"description": ib.GetItemDescription(units, True), "pos": {"x": pb[0], "y": pb[1]}}]})
        done.append(h)
        todo.remove(h)

json.dump({"source": "fast_conn.py", "violations": [], "unconnected_items": pairs}, open(out, "w"), indent=1)
print(f"fast_conn: {len(pairs)} unconnected (KiCad count {conn.GetUnconnectedCount(True)})")
