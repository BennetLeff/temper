#!/usr/bin/env python3
"""Dump the board's copper and keep-outs for layout/gridroute.py (KiCad Python).

    KICAD_PY layout/export_geom.py <board.kicad_pcb> <out.json>

Pads (effective polygons per outer layer), tracks, vias, drills, F.Cu/B.Cu zone fills (except the
outer ground pours, which are refilled around the new copper), rule areas, and the outline box.
All coordinates in KiCad mm.
"""
import json
import sys

import pcbnew

mm = pcbnew.ToMM
LAYERS = {"F": pcbnew.F_Cu, "In2": pcbnew.In2_Cu, "B": pcbnew.B_Cu}


def polys(ps):
    out = []
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        holes = [[[mm(h.CPoint(k).x), mm(h.CPoint(k).y)] for k in range(h.PointCount())]
                 for h in (ps.Hole(i, j) for j in range(ps.HoleCount(i)))]
        out.append({"outline": [[mm(o.CPoint(k).x), mm(o.CPoint(k).y)] for k in range(o.PointCount())], "holes": holes})
    return out


def main():
    b = pcbnew.LoadBoard(sys.argv[1])
    d = {"pads": [], "tracks": [], "vias": [], "drills": [], "zones": [], "rules": []}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            for ln, l in LAYERS.items():
                if p.IsOnLayer(l) and p.FlashLayer(l):
                    d["pads"].append({"net": p.GetNetname(), "layer": ln, "ref": f"{fp.GetReference()}.{p.GetNumber()}",
                                      "poly": polys(p.GetEffectivePolygon(l, pcbnew.ERROR_OUTSIDE))})
            if p.GetDrillSize().x > 0:
                r = mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2
                d["drills"].append([mm(p.GetPosition().x), mm(p.GetPosition().y), r])
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    # a bare hole: tracks keep the 0.25 mm hole clearance -> a foreign "copper" disc of
                    # radius r + 0.10 (the router adds its 0.15 mm copper clearance)
                    d["vias"].append({"net": "<npth>", "at": [mm(p.GetPosition().x), mm(p.GetPosition().y)],
                                      "r": r + 0.10})
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            d["vias"].append({"net": t.GetNetname(), "at": [mm(t.GetPosition().x), mm(t.GetPosition().y)],
                              "r": mm(t.GetWidth(pcbnew.F_Cu)) / 2, "locked": t.IsLocked()})
            d["drills"].append([mm(t.GetPosition().x), mm(t.GetPosition().y), mm(t.GetDrillValue()) / 2])
        else:
            ln = {pcbnew.F_Cu: "F", pcbnew.In2_Cu: "In2", pcbnew.B_Cu: "B"}.get(t.GetLayer())
            if ln:
                d["tracks"].append({"net": t.GetNetname(), "layer": ln, "w": mm(t.GetWidth()), "locked": t.IsLocked(),
                                    "a": [mm(t.GetStart().x), mm(t.GetStart().y)], "b": [mm(t.GetEnd().x), mm(t.GetEnd().y)]})
    for z in b.Zones():
        if z.GetIsRuleArea():
            d["rules"].append({"name": z.GetZoneName(), "tracks": z.GetDoNotAllowTracks(), "vias": z.GetDoNotAllowVias(),
                               "layers": [ln for ln, l in LAYERS.items() if z.IsOnLayer(l)], "poly": polys(z.Outline())})
            continue
        if z.GetZoneName().startswith("GND_") or z.GetZoneName() == "V3V3_plane":
            continue          # pours that refill around new copper
        for ln, l in LAYERS.items():
            if z.IsOnLayer(l):
                d["zones"].append({"net": z.GetNetname(), "layer": ln, "poly": polys(z.GetFilledPolysList(l))})
    for fp in b.GetFootprints():
        for z in fp.Zones():
            if z.GetIsRuleArea():
                d["rules"].append({"name": f"{fp.GetReference()} rule area", "tracks": z.GetDoNotAllowTracks(),
                                   "vias": z.GetDoNotAllowVias(), "layers": [ln for ln, l in LAYERS.items() if z.IsOnLayer(l)],
                                   "poly": polys(z.Outline())})
    # CONTROLLER-SPEC: no MCU traces through the interlock block. The block's courtyard box is a
    # keep-out for every MCU net except the requests that end in it and the read-back outputs.
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    block = ["U20", "U21", "U22", "U23", "U24", "U25", "R51", "R52", "R53", "R54", "R55", "R56", "R57", "R58",
             "R59", "R60", "R61", "C34", "C35", "C36", "C37", "C38", "C39"]
    xs, ys = [], []
    for r_ in block[:6]:          # the region is the box of the six logic ICs
        for g in fps[r_].GraphicalItems():
            if g.GetLayer() == pcbnew.F_CrtYd:
                bb = g.GetBoundingBox()
                xs += [mm(bb.GetLeft()), mm(bb.GetRight())]
                ys += [mm(bb.GetTop()), mm(bb.GetBottom())]
    mcu = {p.GetNetname() for p in fps["U4"].Pads()} - {"selv_gnd", "v3v3", ""}
    allowed = {p.GetNetname() for r_ in block + ["U9"] for p in fps[r_].Pads()}
    d["forbid"] = [{"rect": [min(xs), min(ys), max(xs), max(ys)], "nets": sorted(mcu - allowed),
                    "why": "interlock block: no MCU traces through it"}]
    eb = b.GetBoardEdgesBoundingBox()
    d["edge"] = [mm(eb.GetLeft()), mm(eb.GetTop()), mm(eb.GetRight()), mm(eb.GetBottom())]
    d["circles"] = [[mm(s.GetCenter().x), mm(s.GetCenter().y), mm(s.GetRadius())] for s in b.GetDrawings()
                    if s.GetLayer() == pcbnew.Edge_Cuts and s.GetShape() == pcbnew.SHAPE_T_CIRCLE]
    json.dump(d, open(sys.argv[2], "w"))
    print(len(d["pads"]), "pad layers,", len(d["tracks"]), "tracks,", len(d["vias"]), "vias,", len(d["zones"]), "zones,",
          len(d["rules"]), "rule areas")


if __name__ == "__main__":
    main()
