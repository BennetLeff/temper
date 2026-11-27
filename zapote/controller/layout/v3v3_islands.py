#!/usr/bin/env python3
"""Island links of the In2 v3v3 pour (C53 review M5; KiCad Python).

    KICAD_PY layout/v3v3_islands.py <board.kicad_pcb>      (prints the islands)

In2 carries signals as well as the v3v3 pour, so the pour fills as several islands. An island is linked to the rest
of the net by v3v3 copper on the other layers: an island via, then tracks, pads and other vias, then a via in another
island. links = min(island vias with such a path, outside vias reached). The ESP32 module's 3V3 pin sat on an island
whose only link was one via and a 0.3 mm track. An island is a supply island when that copper reaches a v3v3 pad of an
IC (a U footprint). Used by plane_islands.py (it asks the router for a second link) and check_layout.py (gate
v3v3_islands: every supply island has >= 2 links).
"""
import sys

import pcbnew

NET = "v3v3"
MIN_LINKS = 2


def _polys(b):
    out = []
    for z in b.Zones():
        if z.GetNetname() != NET or z.GetIsRuleArea() or not z.IsOnLayer(pcbnew.In2_Cu):
            continue
        fill = z.GetFilledPolysList(pcbnew.In2_Cu)
        for i in range(fill.OutlineCount()):
            ps = pcbnew.SHAPE_POLY_SET()
            ps.AddOutline(fill.Outline(i))
            for j in range(fill.HoleCount(i)):
                ps.AddHole(fill.Hole(i, j))
            out.append(ps)
    return out


def analyse(b):
    polys = _polys(b)
    if not polys:
        return []
    areas = [p.Area() / 1e12 for p in polys]
    main = max(range(len(polys)), key=lambda i: areas[i])
    vias = [v for v in b.GetTracks() if v.Type() == pcbnew.PCB_VIA_T and v.GetNetname() == NET]
    pads = [(f, p) for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == NET]
    tracks = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() == NET
              and t.GetLayer() != pcbnew.In2_Cu]
    # through-copper anchors (vias, PTH pads) and the In2 island each one lands in
    anchors = [(v.GetPosition(), v.GetWidth(pcbnew.F_Cu) // 2) for v in vias]
    anchors += [(p.GetPosition(), 0) for _, p in pads if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
    isl = [next((i for i, ps in enumerate(polys) if ps.Contains(a)), None) for a, _ in anchors]
    # union-find over the non-In2 copper: anchors, tracks, pads
    n_a, n_t = len(anchors), len(tracks)
    parent = list(range(n_a + n_t + len(pads)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)
    for ti, t in enumerate(tracks):
        lay, ends = t.GetLayer(), (t.GetStart(), t.GetEnd())
        for ai, (a, r) in enumerate(anchors):
            if any((e - a).EuclideanNorm() <= max(r, t.GetWidth() // 2) for e in ends) or t.HitTest(a, 0):
                union(n_a + ti, ai)
        for pi, (_, p) in enumerate(pads):
            if p.IsOnLayer(lay) and any(p.HitTest(e) for e in ends):
                union(n_a + ti, n_a + n_t + pi)
        for tj in range(ti + 1, n_t):
            u = tracks[tj]
            if u.GetLayer() == lay and (any(u.HitTest(e, t.GetWidth() // 2) for e in ends)
                                        or any(t.HitTest(e, u.GetWidth() // 2) for e in (u.GetStart(), u.GetEnd()))):
                union(n_a + ti, n_a + tj)
    for pi, (_, p) in enumerate(pads):
        for ai, (a, r) in enumerate(anchors):
            if p.HitTest(a, r):
                union(n_a + n_t + pi, ai)
    comp_anchors, comp_ic = {}, {}
    for ai in range(n_a):
        comp_anchors.setdefault(find(ai), []).append(ai)
    for pi, (f, _) in enumerate(pads):
        if f.GetReference().startswith("U"):
            comp_ic.setdefault(find(n_a + n_t + pi), set()).add(f.GetReference())
    out = []
    for i in range(len(polys)):
        if i == main:
            continue
        mine = [ai for ai in range(n_a) if isl[ai] == i]
        if not mine:
            continue
        inside, outside, ics = set(), set(), set()
        for ai in mine:
            c = find(ai)
            ics |= comp_ic.get(c, set())
            others = [aj for aj in comp_anchors[c] if isl[aj] != i]
            if others:
                inside.add(ai)
                outside.update(others)
        bb = polys[i].BBox()
        out.append({"island": i, "area_mm2": round(areas[i], 1), "links": min(len(inside), len(outside)),
                    "ics": sorted(ics), "supply": bool(ics), "vias": len(mine),
                    "bbox_mm": [round(pcbnew.ToMM(v), 2) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())],
                    "anchors_mm": [[pcbnew.ToMM(anchors[ai][0].x), pcbnew.ToMM(anchors[ai][0].y)] for ai in mine],
                    "anchor_linked": [ai in inside for ai in mine]})
    main_anchors = [[pcbnew.ToMM(anchors[ai][0].x), pcbnew.ToMM(anchors[ai][0].y)] for ai in range(n_a) if isl[ai] == main]
    for o in out:
        o["main_anchors_mm"] = main_anchors
    return out


def weak(b):
    """Supply islands with fewer than MIN_LINKS links."""
    return [o for o in analyse(b) if o["supply"] and o["links"] < MIN_LINKS]


if __name__ == "__main__":
    for o in analyse(pcbnew.LoadBoard(sys.argv[1])):
        print({k: v for k, v in o.items() if not k.endswith("anchors_mm") and k != "anchor_linked"})
