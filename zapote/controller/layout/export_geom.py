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


def _ohms(v):
    """Resistance from a Yageo RC/RT/AF MPN (RC0603FR-0733RL -> 33, -0710KL -> 10 k, -074K7L -> 4.7 k); inf if not one.
    The footprints carry the MPN as their value, with no resistance field."""
    m = __import__("re").match(r"(?:RC|RT|AF)\d{4}[A-Z]{2}-\d{2}(\d*)([RKM])(\d*)L", v)
    if not m:
        return float("inf")
    return float(f"{m.group(1) or 0}.{m.group(3) or 0}") * {"R": 1, "K": 1e3, "M": 1e6}[m.group(2)]

LAYERS = {"F": pcbnew.F_Cu, "In2": pcbnew.In2_Cu, "In3": pcbnew.In3_Cu, "B": pcbnew.B_Cu}   # C53: In3 (6 layers)


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
    d = {"pads": [], "tracks": [], "vias": [], "drills": [], "drill_nets": [], "zones": [], "rules": []}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            for ln, l in LAYERS.items():
                if p.IsOnLayer(l) and p.FlashLayer(l):
                    d["pads"].append({"net": p.GetNetname(), "layer": ln, "ref": f"{fp.GetReference()}.{p.GetNumber()}",
                                      "poly": polys(p.GetEffectivePolygon(l, pcbnew.ERROR_OUTSIDE))})
            if p.GetDrillSize().x > 0:
                r = mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2
                d["drills"].append([mm(p.GetPosition().x), mm(p.GetPosition().y), r])
                d["drill_nets"].append(p.GetNetname())
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
            d["drill_nets"].append(t.GetNetname())
        else:
            ln = {l: n for n, l in LAYERS.items()}.get(t.GetLayer())
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
    # Parts are selected by atopile path (SourceInstance), which survives designator renumbering.
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    path = {r_: f.GetFieldText("SourceInstance") for r_, f in fps.items()}
    block = sorted(r_ for r_ in fps if path[r_].startswith("interlock."))
    rb = [r_ for r_ in fps if path[r_] == "u_rb"]
    xs, ys = [], []
    for r_ in [r_ for r_ in block if r_.startswith("U")]:     # the region is the box of the six logic ICs
        for g in fps[r_].GraphicalItems():
            if g.GetLayer() == pcbnew.F_CrtYd:
                bb = g.GetBoundingBox()
                xs += [mm(bb.GetLeft()), mm(bb.GetRight())]
                ys += [mm(bb.GetTop()), mm(bb.GetBottom())]
    mcu = {p.GetNetname() for p in fps["U4"].Pads()} - {"selv_gnd", "v3v3", ""}
    for r_, f_ in fps.items():      # C53 review m3: nets the MCU drives through a series resistor
        ns_ = [p.GetNetname() for p in f_.Pads()]
        # series terminations only (<= 100 R: the 33 R PWM parts); kilohm ADC input resistors face the other way, and
        # the op-amp buffer outputs (*_buf_out) behind their 33-100 R isolation resistors are signals into the ADC
        if r_.startswith("R") and len(ns_) == 2 and _ohms(f_.GetValue()) <= 100:
            for a_, b_ in (ns_, ns_[::-1]):
                if a_ in mcu and b_ not in ("selv_gnd", "v3v3", "") and not b_.endswith("_buf_out"):
                    mcu = mcu | {b_}
    allowed = {p.GetNetname() for r_ in block + rb for p in fps[r_].Pads()}
    d["forbid"] = [{"rect": [min(xs), min(ys), max(xs), max(ys)], "nets": sorted(mcu - allowed),
                    "why": "interlock block: no MCU traces through it"}]
    # C34: per-net copper clearance above the board's 0.15 mm (net classes in the board's .kicad_pro,
    # exact-name patterns as build_board.py writes them), and the RTD analog family (floorplan.py)
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import floorplan
    pro = json.loads(pathlib.Path(sys.argv[1]).with_suffix(".kicad_pro").read_text())["net_settings"]
    cls = {c["name"]: c["clearance"] for c in pro["classes"]}
    d["clearance"] = {pt["pattern"]: cls[pt["netclass"]] for pt in pro["netclass_patterns"]
                      if cls[pt["netclass"]] > 0.15 + 1e-9}
    d["pair_clearance"] = [list(x) for x in floorplan.PAIR_CLEARANCE]
    d["rtd_analog"] = list(floorplan.RTD_ANALOG_NETS)
    d["rtd_return_via_mm"] = floorplan.RTD_RETURN_VIA_MM
    eb = b.GetBoardEdgesBoundingBox()
    d["edge"] = [mm(eb.GetLeft()), mm(eb.GetTop()), mm(eb.GetRight()), mm(eb.GetBottom())]
    d["circles"] = [[mm(s.GetCenter().x), mm(s.GetCenter().y), mm(s.GetRadius())] for s in b.GetDrawings()
                    if s.GetLayer() == pcbnew.Edge_Cuts and s.GetShape() == pcbnew.SHAPE_T_CIRCLE]
    json.dump(d, open(sys.argv[2], "w"))
    print(len(d["pads"]), "pad layers,", len(d["tracks"]), "tracks,", len(d["vias"]), "vias,", len(d["zones"]), "zones,",
          len(d["rules"]), "rule areas")


if __name__ == "__main__":
    main()
