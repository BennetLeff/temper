#!/usr/bin/env python3
"""Make KiCad's "zone to zone" unconnected items routable (KiCad Python).

    KICAD_PY layout/plane_islands.py <board.kicad_pcb> <drc.json>     (rewrites drc.json in place)

When In2 signal tracks cut the In2 v3v3 pour into islands, KiCad reports the plane net as
"Zone ... -> Zone ..." with both positions at the zone's first corner, which gives the router
nothing to aim at. This replaces every such item with a real pair: for each island that is
not the largest, the closest two v3v3 vias (or through-hole pads) of that island and of the
rest of the net, written as through-hole items so gridroute.py may join them on any layer.
The board must have filled zones (the DRC run with --refill-zones --save-board does that).

C53 review M5: an island that IS connected, but by a single link, and carries an IC's supply (v3v3_islands.py) also
gets a pair: from one of its vias that is not on the existing link to the nearest via of the main island, so the
router adds a second link.
"""
import json
import math
import sys

import pcbnew

mm = pcbnew.ToMM


def main():
    b = pcbnew.LoadBoard(sys.argv[1])
    path = sys.argv[2]
    d = json.load(open(path))
    zone_items = [u for u in d["unconnected_items"]
                  if all(e["description"].startswith("Zone") for e in u["items"])]
    keep = [u for u in d["unconnected_items"] if u not in zone_items]
    # a pad or via -> zone item (a PTH pad left on a pour island, C53 J7.2): the zone end also carries the zone's first
    # corner (the board corner), which the router took as a 77 mm target every round. Aim it at the zone's through
    # copper instead: the anchor in the zone's largest fill outline nearest the other end.
    n_mixed = 0
    for u in keep:
        zs = [e for e in u["items"] if e["description"].startswith("Zone")]
        others = [e for e in u["items"] if not e["description"].startswith("Zone")]
        if len(zs) != 1 or not others:
            continue
        m_ = __import__("re").match(r"Zone '([^']*)' \[([^\]]+)\] on ([^,\s]+)", zs[0]["description"])
        if not m_:
            continue
        zname, net, lname = m_.groups()
        lay = b.GetLayerID(lname)
        o = (others[0]["pos"]["x"], others[0]["pos"]["y"])
        cands = []
        for z in b.Zones():
            if z.GetZoneName() != zname or z.GetNetname() != net or not z.IsOnLayer(lay):
                continue
            fill = z.GetFilledPolysList(lay)
            if not fill.OutlineCount():
                continue
            k = max(range(fill.OutlineCount()), key=lambda i: abs(fill.Outline(i).Area()))
            poly = pcbnew.SHAPE_POLY_SET()
            poly.AddOutline(fill.Outline(k))
            pts = [t.GetPosition() for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == net]
            pts += [p.GetPosition() for f in b.GetFootprints() for p in f.Pads()
                    if p.GetNetname() == net and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
            cands += [(mm(q.x), mm(q.y)) for q in pts if poly.Contains(q)]
        cands = [c for c in cands if math.dist(c, o) > 0.05]
        if not cands:
            continue
        c = min(cands, key=lambda c: math.dist(c, o))
        zs[0]["description"] = f"Via [{net}] on F.Cu - B.Cu"
        zs[0]["pos"] = {"x": c[0], "y": c[1]}
        n_mixed += 1
    for net in sorted({__import__("re").search(r"\[([^\]]+)\]", u["items"][0]["description"]).group(1)
                       for u in zone_items}):
        # through-copper anchors of this net: vias and PTH pads
        anchors = [(mm(t.GetPosition().x), mm(t.GetPosition().y), "via")
                   for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == net]
        anchors += [(mm(p.GetPosition().x), mm(p.GetPosition().y), "pad")
                    for f in b.GetFootprints() for p in f.Pads()
                    if p.GetNetname() == net and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
        islands = []
        for z in b.Zones():
            if z.GetNetname() != net or z.GetIsRuleArea():
                continue
            for lay in z.GetLayerSet().Seq():
                fill = z.GetFilledPolysList(lay)
                for i in range(fill.OutlineCount()):
                    poly = pcbnew.SHAPE_POLY_SET()
                    poly.AddOutline(fill.Outline(i))
                    members = [a for a in anchors
                               if poly.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))]
                    if members:
                        islands.append((poly.Area(), members))
        if len(islands) < 2:
            continue
        islands.sort(key=lambda t: -t[0])
        main_set = islands[0][1]
        for _, members in islands[1:]:
            best = min(((math.dist(a[:2], m[:2]), a, m) for a in members for m in main_set if a[:2] != m[:2]),
                       default=None)
            if best is None:
                continue
            _, a, m = best
            keep.append({"description": "plane island (plane_islands.py)", "items": [
                {"description": f"Via [{net}] on F.Cu - B.Cu", "pos": {"x": a[0], "y": a[1]}},
                {"description": f"Via [{net}] on F.Cu - B.Cu", "pos": {"x": m[0], "y": m[1]}}]})
            main_set = main_set + members
    sys.path.insert(0, __import__("os").path.dirname(__file__))
    import v3v3_islands
    n_weak = 0
    for o in v3v3_islands.weak(b):
        if o["links"] == 0 or not o["main_anchors_mm"]:
            continue          # an unlinked island is a zone item above
        # prefer an island via that is not on the existing link, so the new pair is a second, separate path
        free = [a for a, used in zip(o["anchors_mm"], o["anchor_linked"]) if not used]
        cands = free or o["anchors_mm"]
        best = min(((math.dist(a, m), a, m) for a in cands for m in o["main_anchors_mm"]), default=None)
        if best is None:
            continue
        _, a, m = best
        keep.append({"description": "weak plane island (plane_islands.py, v3v3_islands.py)", "items": [
            {"description": f"Via [{v3v3_islands.NET}] on F.Cu - B.Cu", "pos": {"x": a[0], "y": a[1]}},
            {"description": f"Via [{v3v3_islands.NET}] on F.Cu - B.Cu", "pos": {"x": m[0], "y": m[1]}}]})
        n_weak += 1
    d["unconnected_items"] = keep
    json.dump(d, open(path, "w"), indent=1)
    print(f"plane islands: {len(zone_items)} zone items replaced, {n_mixed} pad-to-zone items re-aimed, "
          f"{n_weak} weak-island pairs added")


if __name__ == "__main__":
    main()
