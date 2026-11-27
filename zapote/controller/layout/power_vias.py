#!/usr/bin/env python3
"""Companion vias for the high-current nets' layer changes (C53 review M4).

    python3  layout/power_vias.py plan  <geom.json> <plan.json>     (shapely; layout/gridroute.py's exact check)
    KICAD_PY layout/power_vias.py apply <board.kicad_pcb> <plan.json>

The router makes every layer change with one 0.6/0.3 via. A 0.3 mm barrel is about 1 A of plating, and V_BLOWER
(1.42 A typ, 2.70 A max) went through four of them in series. For each via of a net in NETS, this adds companion
vias until it has COMPANIONS of them within REACH mm. A companion sits on one of the via's own tracks, a step along
it, and a stub on each of the via's other layers ties it back to the via. Each candidate passes gridroute.Exact's
clearance, keep-out and drill-spacing checks against the copper exported by layout/export_geom.py, and the vias
already accepted. A via whose candidates all fail keeps fewer companions; check_layout.py's power_vias gate reports
it. Run after routing, before the outer pours go in (route.py).
"""
import json
import math
import sys
from pathlib import Path

NETS = {"V_BLOWER": 0.8, "V15_BLW": 0.8, "v15_selv": 0.8, "V12_FAN2": 0.6}   # net: stub width (its routed width)
COMPANIONS = 2        # so each layer change has three barrels (1.42 A typ / 2.70 A max over three on V_BLOWER)
REACH = 1.8           # mm: a via within this of another same-net via counts as its companion
STEPS = (0.9, 1.1, 1.3, 1.5)
RTD_KEEP = 2.0        # mm from any RTD analog via (their In1 antipad spacing, gridroute RTD_HOLE_GAP)


def plan(geom_path, out_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gridroute as g
    from shapely.geometry import LineString, Point
    geom = json.load(open(geom_path))
    g.configure(geom)
    ex = g.Exact(geom)
    drills = [tuple(d) for d in geom["drills"]]
    rtd_vias = [v["at"] for v in geom["vias"] if v["net"] in set(geom.get("rtd_analog", []))]
    tracks = [t for t in geom["tracks"] if t["net"] in NETS]
    vias = [v for v in geom["vias"] if v["net"] in NETS]
    added_v, added_t, short = [], [], []
    same = {n: [tuple(v["at"]) for v in vias if v["net"] == n] for n in NETS}
    fills = {}          # net -> layer -> filled zone geometry (F/B pours such as BLW_FEED and the buck VIN pours)
    for z in geom["zones"]:
        if z["net"] in NETS:
            gz = g.shp(z["poly"])
            if gz is not None:
                fills.setdefault(z["net"], {}).setdefault(z["layer"], []).append(gz)

    def in_fill(p, net, l):
        return any(gz.buffer(-g.VIA_R).contains(Point(p)) for gz in fills.get(net, {}).get(l, []))

    def near(c, net):
        return sum(1 for o in same[net] if 1e-6 < math.dist(o, c) <= REACH)

    for v in vias:
        c, net = tuple(v["at"]), v["net"]
        w = NETS[net]
        inc = []
        for t in tracks:
            if t["net"] != net:
                continue
            for a, b in ((t["a"], t["b"]), (t["b"], t["a"])):
                if math.dist(a, c) < 0.05:
                    inc.append((t["layer"], tuple(b), t["w"]))
        layers = sorted({l for l, _, _ in inc})
        # a layer the via meets only through a pour: a companion inside that pour needs no stub there
        pour_layers = [l for l in ("F", "B") if l not in layers and in_fill(c, net, l)]
        cands = []
        if not inc:         # pour to pour: around the via, inside the pours on both sides
            for k in range(8):
                a_ = math.pi * k / 4
                for s in STEPS:
                    cands.append(((c[0] + s * math.cos(a_), c[1] + s * math.sin(a_)), "pour"))
        for l, e, tw in inc:
            d = math.dist(c, e)
            u = ((e[0] - c[0]) / d, (e[1] - c[1]) / d)
            for s in STEPS:
                if s <= d:
                    cands.append(((c[0] + s * u[0], c[1] + s * u[1]), l))
            for s in STEPS:          # beside the via, square to the track, stubbed on every layer
                for sg in (1, -1):
                    cands.append(((c[0] - sg * s * u[1], c[1] + sg * s * u[0]), None))
        for p, on in cands:
            if near(c, net) >= COMPANIONS:
                break
            if any(math.dist(p, r) < RTD_KEEP for r in rtd_vias) or any(math.dist(p, o) < 0.9 for o in same[net]):
                continue
            if not ex.via_ok(p, net, drills):
                continue
            if any(not in_fill(p, net, l) for l in pour_layers):
                continue
            stubs = [l for l in layers if l != on]
            if not all(ex.seg_ok(l, p, c, w, net) for l in stubs):
                continue
            for l in g.LAYERS:
                ex.add(l, Point(p).buffer(g.VIA_R), net)
            for l in stubs:
                ex.add(l, LineString([p, c]).buffer(w / 2), net)
                added_t.append({"net": net, "layer": l, "w": w, "a": list(p), "b": list(c)})
            drills.append((p[0], p[1], g.VIA_DRILL_R))
            same[net].append(p)
            added_v.append({"net": net, "at": list(p)})
        if near(c, net) < COMPANIONS:
            short.append({"net": net, "at": list(c), "companions": near(c, net)})
    json.dump({"vias": added_v, "tracks": added_t, "short": short}, open(out_path, "w"), indent=1)
    print(f"power vias: {len(added_v)} added, {len(added_t)} stubs, {len(short)} vias short of {COMPANIONS} companions")


def apply(board_path, plan_path):
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    r = json.load(open(plan_path))
    L = {"F": pcbnew.F_Cu, "In2": pcbnew.In2_Cu, "In3": pcbnew.In3_Cu, "B": pcbnew.B_Cu}
    for t in r["tracks"]:
        tr = pcbnew.PCB_TRACK(b)
        tr.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(t["a"][0]), pcbnew.FromMM(t["a"][1])))
        tr.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(t["b"][0]), pcbnew.FromMM(t["b"][1])))
        tr.SetWidth(pcbnew.FromMM(t["w"]))
        tr.SetLayer(L[t["layer"]])
        tr.SetNet(b.FindNet(t["net"]))
        b.Add(tr)
    for v in r["vias"]:
        via = pcbnew.PCB_VIA(b)
        via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(v["at"][0]), pcbnew.FromMM(v["at"][1])))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetNet(b.FindNet(v["net"]))
        b.Add(via)
    pcbnew.SaveBoard(board_path, b)
    print(f"power vias applied: {len(r['vias'])} vias, {len(r['tracks'])} stubs")


if __name__ == "__main__":
    {"plan": plan, "apply": apply}[sys.argv[1]](sys.argv[2], sys.argv[3])
