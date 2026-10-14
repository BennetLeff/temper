#!/usr/bin/env python3
"""Native-21 copper, authored (layout stage 3) -> native-21/layout/copper.json.

    python3 native-21/layout/route21.py
    KICAD_PY prototype-closure/pcb/apply_copper21.py
    kicad-cli pcb drc --refill-zones --save-board native-21/routed/section.kicad_pcb

Every pour outline, track bend and via below is an explicit coordinate (KiCad
frame, mm); nothing searches for a path. Pours are unions of rectangles; KiCad's
fill applies the D5 insulation rules (section.kicad_dru) to every one of them.

Long-haul plan (ROUTING plan in native-21/FLOORPLAN.md, stage 3):

  layer   lanes leaving the core / BR1 gate (top -> bottom)
  F.Cu    N_FILT (BR1.3)            SW_A (Q2.3 pour)
  B.Cu    L_FILT (BR1.2)            SW_B (core lane under leg A)
  In1     RECT_P (BR1.1 -> J7)      HV_RET trunk (core plane, bottom exit)
  In2     RECT_N (BR1.4 -> J9)      BUS_P trunk (core plane, bottom exit)

The mains pair (F/B, stacked) passes under the link block to L1; the switch
nodes (F/B, stacked) turn down to T1 (SW_A) and the resonant bank (SW_B); the
bus trunk (In1/In2, stacked) runs under both to J8/J10 and C5/C6.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from shapely.geometry import LineString, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
import sys  # noqa: E402
sys.path.insert(0, str(HERE))
from geom21 import Geometry  # noqa: E402
import maze21  # noqa: E402

GEO = Geometry()
ZONES, TRACKS, VIAS, ESCAPES = [], [], [], []
POWER_VIA = {"size": 1.6, "drill": 0.8}


PLANES = {}       # (net, layer) -> union of authored pour outlines, for fan-out targets


def zone(net, layer, *rects, priority=1, name="", protect=False):
    """Pour outline from rectangles, clipped to the D5 barrier in plan view: SELV / PE pours stay
    8.2 mm from every HOT item authored so far (pads, tracks, vias, pour outlines on any layer);
    HOT pours stay 8.2 mm from SELV / PE pads and tracks."""
    import rules21
    shape = unary_union([box(*r) for r in rects])
    dom = rules21.domain(net)
    if dom in ("SELV", "PE", "HOT"):
        tree, items = GEO._tree("PLAN")
        cut = [g for i in tree.query(shape.buffer(8.5)) for g, other in [items[i]]
               if other not in (net, "<npth>") and rules21.barrier(net, other)
               and not (dom == "HOT" and g.area > 400)]
        if cut:
            shape = shape.difference(unary_union(cut).buffer(rules21.BARRIER + 0.2, resolution=8))
    if shape.is_empty:
        return
    PLANES[(net, layer)] = unary_union([PLANES.get((net, layer), shape), shape])
    GEO.add_plan(net, shape)
    if protect:
        GEO.protect(net, layer, shape)
    for poly in getattr(shape, "geoms", [shape]):
        poly = poly.simplify(0.001)
        ZONES.append({"net": net, "layer": layer, "priority": priority, "name": name,
                      "outline": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
                      "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in poly.interiors]})


def _xy(p):
    if isinstance(p, str):
        q = GEO.pad(p)
        return (q["x"], q["y"])
    return tuple(p)


def track(net, layer, width, *points):
    TRACKS.append({"net": net, "layer": layer, "width": width, "points": list(points)})
    GEO.add_track(net, layer, width, [_xy(p) for p in points])


def via(net, x, y, power=False, size=None):
    spec = POWER_VIA if power else {"size": size or 0.6, "drill": 0.3}
    VIAS.append({"net": net, "at": [x, y], **spec})
    GEO.add_via(net, x, y, spec["size"])


def fanout(net, region, layer, skip=()):
    """Via + short F.Cu stub from every SMD pad of `net` inside `region` (x0, y0, x1, y1) down
    to that net's pour on `layer`. Spots are the nearest legal ones (geom21.via_spot)."""
    target = PLANES[(net, layer)].buffer(-0.6)
    done, missed = 0, []
    for p in GEO.pads:
        if p["net"] != net or p["tht"] or f"{p['ref']}.{p['pad']}" in skip:
            continue
        if not (region[0] <= p["x"] <= region[2] and region[1] <= p["y"] <= region[3]):
            continue
        rp = f"{p['ref']}.{p['pad']}"
        spot = GEO.via_spot(rp, within=target) or GEO.via_spot(rp, size=0.6, width=0.25, reach=(0.3, 4.5),
                                                                within=target)
        if spot is None:
            missed.append(rp)
            continue
        small = GEO.via_spot(rp, within=target) is None
        track(net, "F.Cu", 0.25 if small else 0.4, rp, list(spot))
        via(net, *spot, size=0.6 if small else None)
        done += 1
    FANOUT_LOG.append((net, layer, done, missed))


FANOUT_LOG = []

def add_signal_via(net, x, y, la, lb, width):
    """A 0.6/0.3 via at a layer change, or, when a same-net via is already within one drill
    pitch, short joins on both layers to that via instead (no stacked drills)."""
    for v in VIAS:
        if v["net"] == net and math.dist(v["at"], (x, y)) < 0.8:
            for lay in {la, lb}:
                if math.dist(v["at"], (x, y)) > 1e-3:
                    track(net, lay, width, [x, y], list(v["at"]))
            return
    VIAS.append({"net": net, "at": [x, y], "size": 0.6, "drill": 0.3})
    GEO.add_via(net, x, y, 0.6)


def _legal(net, segs, width, vias=()):
    """Final check of a found path against everything authored so far (incl. plan-view barrier)."""
    from shapely.geometry import Point
    for lay, path in segs:
        if len(path) > 1 and GEO.conflicts(net, (lay,), LineString(path).buffer(width / 2), limit=1):
            return False
    for v in vias:
        if GEO.conflicts(net, ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"), Point(v[0], v[1]).buffer(0.3), limit=1, via=True):
            return False
    return True


LINK_LOG = []


def link(net, layer, bx, width, pads):
    """Join `pads` ("REF.PAD") inside box `bx`, nearest pad first (a minimum tree). Bends (and,
    when `layer` is "F+B", F/B vias) come from maze21; each leg is recorded as explicit copper."""
    # never wider than the narrowest pad it lands on (fine-pitch pins)
    width = min([width] + [min(b[2] - b[0], b[3] - b[1]) * 0.9 for b in (GEO.pad(pp)["box"] for pp in pads
                                                                          if not pp.startswith("@"))])
    width = max(round(width, 2), 0.2)
    layers = ("F.Cu", "B.Cu") if layer == "F+B" else (layer if isinstance(layer, tuple) else None)
    two = layers is not None
    def _pt(pp):
        if pp.startswith("@"):
            x, y, _ = pp[1:].split(",")
            return (float(x), float(y))
        return _xy(pp)

    def _li(pp):
        if pp.startswith("@"):
            lay = pp.rsplit(",", 1)[1]
            lays_ = layers or (layer,)
            return lays_.index(lay) if lay in lays_ else (None if lay == "*" else -1)
        return None if GEO.pad(pp)["tht"] else 0
    pts = {pp: _pt(pp) for pp in pads}
    lidx = {pp: _li(pp) for pp in pads}
    if any(v == -1 for v in lidx.values()):
        LINK_LOG.append((net, layer, len(pads), [pp for pp in pads if lidx[pp] == -1]))
        return False
    tree = [(*pts[pads[0]], lidx[pads[0]] if two else 0)]
    todo = list(pads[1:])
    failed = []
    while todo:
        todo.sort(key=lambda q: min(math.dist(pts[q], t[:2]) for t in tree))
        q = todo.pop(0)
        res = None
        near = min(tree, key=lambda t: math.dist(t[:2], pts[q]))
        # direct and L-shaped joins first (fine-pitch neighbours, short hops)
        lays0 = layers or (layer,)
        a, b = near[:2], pts[q]
        for cand, wj in [(c, w_) for w_ in (width, 0.2) for c in ([a, b], [a, (b[0], a[1]), b], [a, (a[0], b[1]), b])]:
            for li, lay in enumerate(lays0):
                if (near[2] not in (None, li)) or (lidx.get(q) not in (None, li)) if two else False:
                    continue
                if lay != "F.Cu" and not q.startswith("@") and not (GEO.pad(q)["tht"]):
                    continue
                geom = LineString(cand).buffer(wj / 2)
                if not GEO.conflicts(net, (lay,), geom, limit=1):
                    res = ([(lay, [[round(x, 3), round(y, 3)] for x, y in cand])], [])
                    join_w = wj
                    break
            if res:
                break
        if res is not None:
            segs, vs = res
            for lay, path in segs:
                track(net, lay, join_w, *path)
                tree.extend((x, y, lays0.index(lay)) for x, y in path)
            continue
        for m in (4.0, 10.0, 30.0, None):   # None: the whole corridor box (long detours)
            sub = bx if m is None else (max(bx[0], min(near[0], pts[q][0]) - m), max(bx[1], min(near[1], pts[q][1]) - m),
                                        min(bx[2], max(near[0], pts[q][0]) + m), min(bx[3], max(near[1], pts[q][1]) + m))
            starts = [t for t in tree if sub[0] <= t[0] <= sub[2] and sub[1] <= t[1] <= sub[3]] or [near]
            if two:
                res = maze21.connect2(GEO, net, sub, width, starts, [(*pts[q], lidx[q])], layers=layers, via=0.6)
                if res is not None and not _legal(net, res[0], width, res[1]):
                    res = None
            else:
                p = maze21.connect(GEO, net, layer, sub, width, [t[:2] for t in starts], [pts[q]])
                res = None if p is None else ([(layer, p)], [])
            if res is not None:
                break
        if res is None and two:
            # fine pass for dense pin fields: 0.1 mm grid, 0.2 mm trace, local box only
            maze21.STEP = 0.1
            try:
                for m in (3.0, 8.0):
                    sub = (max(bx[0], min(near[0], pts[q][0]) - m), max(bx[1], min(near[1], pts[q][1]) - m),
                           min(bx[2], max(near[0], pts[q][0]) + m), min(bx[3], max(near[1], pts[q][1]) + m))
                    starts = [t for t in tree if sub[0] <= t[0] <= sub[2] and sub[1] <= t[1] <= sub[3]] or [near]
                    res = maze21.connect2(GEO, net, sub, 0.2, starts, [(*pts[q], lidx[q])], layers=layers, via=0.6)
                    if res is not None and not _legal(net, res[0], 0.2, res[1]):
                        res = None
                    if res is not None:
                        width_used = 0.2
                        break
            finally:
                maze21.STEP = 0.2
            if res is not None:
                segs, vs = res
                lays = layers or (layer,)
                for lay, path in segs:
                    track(net, lay, 0.2, *path)
                    tree.extend((x, y, lays.index(lay)) for x, y in path)
                for x, y, la, lb in vs:
                    add_signal_via(net, x, y, la, lb, 0.2)
                    tree.extend((x, y, kk) for kk in range(len(lays)))
                continue
        if res is None:
            failed.append(q)
            continue
        segs, vs = res
        lays = layers or (layer,)
        for lay, path in segs:
            track(net, lay, width, *path)
            tree.extend((x, y, lays.index(lay)) for x, y in path)
        for x, y, la, lb in vs:
            add_signal_via(net, x, y, la, lb, width)
            tree.extend((x, y, kk) for kk in range(len(lays)))
    LINK_LOG.append((net, layer, len(pads), failed))
    return not failed


def island_signals(bx, layer="F+B", width=0.25, exclude=()):
    """Every net whose pads all sit inside `bx` (and is not a plane net there) joined on `layer`."""
    by = {}
    for p in GEO.pads:
        if p["net"]:
            by.setdefault(p["net"], []).append(p)
    nets = []
    for n, ps in by.items():
        if n in exclude or len(ps) < 2 or any((n, lay) in PLANES for lay in ("In1.Cu", "In2.Cu", "B.Cu")):
            continue
        if all(bx[0] <= q["x"] <= bx[2] and bx[1] <= q["y"] <= bx[3] for q in ps):
            nets.append((sum(math.dist((q["x"], q["y"]), (ps[0]["x"], ps[0]["y"])) for q in ps), n, ps))
    for _, n, ps in sorted(nets):
        link(n, layer, bx, width, [f"{q['ref']}.{q['pad']}" for q in ps])



# shunt-side power vias: 1.0 / 0.5 mm
VIA_1 = {"size": 1.0, "drill": 0.5}


# ---------------------------------------------------------------- bus trunk
# Core planes (In2 BUS_P / In1 HV_RET) under the FET row and HF row, bottom exit under the
# LS-A bank, then a 23 mm stacked band right to the resonant bank and down to C5/C6/D3.
TRUNK = [(0.6, 0.6, 76.5, 25.5), (0.6, 25.5, 100.5, 48.0), (77.0, 27.2, 214.0, 50.5),
         (198.0, 50.5, 214.0, 57.0), (198.0, 57.0, 289.4, 113.0)]
zone("bus_p", "In2.Cu", *TRUNK, (137.0, 21.0, 148.5, 27.2), name="bus_p trunk")      # J8 from below
zone("hv_ret", "In1.Cu", *TRUNK, (144.5, 0.6, 160.0, 13.2), (150.8, 13.2, 160.0, 27.2),
     name="hv_ret trunk")                                                               # J10 round J8
zone("leg_ret", "In1.Cu", (18.0, 0.6, 58.0, 12.5), priority=2, name="leg_ret sources")

# ---------------------------------------------------------------- rectifier to the links
zone("rect_p", "In1.Cu", (79.7, 0.6, 86.4, 9.8), (79.7, 9.8, 128.6, 24.0), name="rect_p BR1.1-J7", protect=True)
zone("rect_n", "In2.Cu", (104.4, 0.6, 128.6, 13.2), name="rect_n BR1.4-J9", protect=True)

# ---------------------------------------------------------------- mains pair (F N_FILT / B L_FILT)
zone("n_filt", "F.Cu", (96.9, 0.6, 101.5, 16.0), (96.9, 9.8, 122.2, 16.0), (113.2, 9.8, 122.2, 34.0),
     (113.2, 27.2, 226.0, 34.0), (162.0, 22.0, 168.0, 34.0), (216.0, 27.2, 226.0, 50.0),
     (216.0, 40.0, 246.0, 50.0), (237.5, 40.0, 246.0, 60.0), (237.5, 54.0, 288.6, 60.0),
     (283.0, 46.0, 288.6, 60.0), name="n_filt BR1.3-L1-C2", protect=True)
zone("l_filt", "B.Cu", (86.9, 0.6, 94.0, 16.5), (86.9, 9.8, 122.2, 16.5), (113.2, 9.8, 122.2, 34.0),
     (113.2, 29.1, 236.0, 34.0), (226.0, 29.1, 236.0, 58.0), name="l_filt BR1.2-L1", protect=True)

# ---------------------------------------------------------------- switch nodes and tank
zone("sw_a", "F.Cu", (72.5, 0.6, 76.5, 24.0), (72.5, 9.8, 93.7, 23.8), (87.2, 19.2, 103.6, 30.4),
     (103.6, 19.2, 110.0, 48.0), (103.6, 37.2, 148.6, 48.0), (139.0, 37.2, 148.6, 101.5),
     name="sw_a Q2.3-T1.1", protect=True)
zone("sw_a", "B.Cu", (46.5, 0.6, 76.5, 12.5), (58.0, 12.5, 76.5, 16.0), name="sw_a leg-A link", protect=True)
# SW_B: leg-B pins, a lane under leg A between the shunt vias (y < 16) and the HF-row pins
# (y > 30.6), a 4.6 mm neck past C39.1, then down right of the LS-A bank (its vias stay free).
# (widened upward under leg A's low side, x 40-57, so the Cgs source via at x 46.4 cannot sever it)
zone("sw_b", "B.Cu", (0.6, 9.7, 12.5, 27.0), (12.5, 0.6, 31.0, 27.0), (12.5, 19.4, 77.0, 27.0), (40.0, 15.7, 57.0, 27.0), (77.0, 19.4, 100.5, 27.3),
     (79.7, 9.8, 83.7, 23.8), (100.5, 19.7, 110.0, 50.0), (100.5, 37.2, 200.6, 50.0),
     (192.0, 37.2, 200.6, 113.0), name="sw_b leg B-C21..C23", protect=True)
zone("res_a", "B.Cu", (127.0, 64.0, 161.0, 77.0), (150.0, 55.0, 161.0, 114.0), name="res_a J5-C21..C23", protect=True)
zone("coil_feed", "F.Cu", (126.0, 80.0, 135.5, 101.0), name="coil_feed J2-T1.2", protect=True)
zone("coil_feed", "B.Cu", (126.0, 80.0, 135.5, 101.0), name="coil_feed J2-T1.2", protect=True)

# ---------------------------------------------------------------- core: snubbers, gate networks
# Snubbers onto their FET pins (F, 0.8 mm). Each 1206 leaves its pad diagonally outward to
# the pin column (pads are 1.26 mm inboard of the pins), inside a bounded pad-escape area.
def snubber(c, left, right, q_left, q_right, xl, xr):
    track(left, "F.Cu", 0.8, f"{c}.1", [xl, 8.6], f"{q_left}")
    track(right, "F.Cu", 0.8, f"{c}.2", [xr, 8.6], f"{q_right}")
    ESCAPES.append({"ref": c, "pad": "1", "rect": [xl - 0.7, 7.9, xl + 2.0, 10.8]})
    ESCAPES.append({"ref": c, "pad": "2", "rect": [xr - 2.0, 7.9, xr + 0.7, 10.8]})


snubber("C19", "bus_p", "sw_b", "Q5.2", "Q5.3", 9.95, 15.40)
snubber("C20", "sw_b", "leg_ret", "Q6.2", "Q6.3", 27.95, 33.40)
snubber("C13", "sw_a", "leg_ret", "Q3.2", "Q3.3", 50.05, 55.50)
snubber("C12", "bus_p", "sw_a", "Q2.2", "Q2.3", 68.05, 73.50)

# Gate network, identical about each gate pin x = g (place.py): R_g (g, 11.14 gate / 14.06 out),
# R_pd (g-2.7, 12.93 gate / 11.28 source), D_off (g+2.4 off / g+6.8 gate, y 17.9),
# R_off (g+9.5 off / g+12.5 out, y 17.9), Cgs (g+0.2 gate / g+1.8 source, y 21.8).
# Planar: OUT runs above the D_off/R_off row to R_g; OFF links R_off-D_off over the top of
# D_off.gate; GATE comes down a spine left of R_g and returns under the row to D_off and Cgs.
def gate_network(g, gate, out, off):
    track(gate, "F.Cu", 0.8, [g, 4.21], [g, 11.14])
    track(gate, "F.Cu", 0.4, [g, 11.14], [g - 1.35, 12.0], [g - 1.35, 20.3], [g + 6.8, 20.3], [g + 6.8, 17.9])
    track(gate, "F.Cu", 0.4, [g - 2.7, 12.93], [g - 1.35, 12.93])
    track(gate, "F.Cu", 0.4, [g - 1.35, 20.3], [g - 1.35, 21.8], [g + 0.2, 21.8])
    track(off, "F.Cu", 0.4, [g + 9.5, 17.9], [g + 9.5, 15.6], [g + 2.4, 15.6], [g + 2.4, 17.9])
    track(out, "F.Cu", 0.6, [g + 12.5, 17.9], [g + 12.5, 16.9], [g + 11.0, 14.3], [g, 14.3])


for g, leg, side in ((4.5, "leg_b", "h"), (22.5, "leg_b", "l"), (44.6, "leg_a", "l"), (62.6, "leg_a", "h")):
    gate_network(g, f"{leg}-gate_{side}", f"{leg}-out_{side}", f"{leg}-off_{side}")

# Driver outputs to R_off.out (U2 / U1 HOT row at y 46.12, pins 15 OUTA = high side, 10 OUTB = low side).
# Leg B high side: left of C41.2, under the HF row, through its own (SW_B) bank to U2.15.
track("leg_b-out_h", "F.Cu", 0.6, [17.0, 17.9], [17.0, 18.9], [12.6, 21.0], [12.6, 32.9], [29.82, 32.9],
      [29.82, 46.12])
# Leg B low side: straight down beside the shunt (LOW group throughout).
track("leg_b-out_l", "F.Cu", 0.6, [35.0, 17.9], [35.0, 18.9], [35.95, 21.5], [35.95, 44.5], [36.17, 46.12])
# Leg A low side: down to a via below the HF row, In1 (LOW, inside the HV_RET plane) under
# the leg-A high-side area, up beside U1.
track("leg_a-out_l", "F.Cu", 0.6, [57.1, 17.9], [57.1, 18.9], [56.0, 20.5], [56.0, 31.0])
via("leg_a-out_l", 56.0, 31.0)
track("leg_a-out_l", "In1.Cu", 0.5, [56.0, 31.0], [56.0, 33.6], [82.0, 33.6], [82.0, 37.0])
via("leg_a-out_l", 82.0, 37.0)
track("leg_a-out_l", "F.Cu", 0.5, [82.0, 37.0], [82.6, 43.5], [83.22, 46.12])
# Leg A high side: down the SW_A pour beside Q2.3, left of C39.1.
track("leg_a-out_h", "F.Cu", 0.6, [75.1, 17.9], [75.1, 18.9], [77.0, 20.5], [77.0, 44.0], [76.87, 46.12])


# Gate-network source pads (R_pd and Cgs source sides) are enclosed by each network's own gate,
# OFF and OUT tracks, so they leave through vias: high-side ones into their switch node's B
# copper, low-side ones into the In1 LEG_RET region (R_pd directly; Cgs through a short In1 slot
# running from below the HF row's return currents up into the region). R13.2 sits in the F
# LEG_RET pour; C55.2 reaches the SW_A F pour beside Q2.3 directly.
for net, pad_, at in (("sw_b", "R19.2", (1.8, 9.9)), ("sw_b", "C62.2", (6.28, 23.3)),
                      ("sw_a", "R11.2", (59.9, 9.7)), ("leg_ret", "R21.2", (19.8, 9.7))):
    track(net, "F.Cu", 0.3, pad_, list(at))
    via(net, *at, size=0.6)
for pad_, x in (("C63.2", 24.27), ("C56.2", 46.38)):
    track("leg_ret", "F.Cu", 0.3, pad_, [x, 23.3])
    via("leg_ret", x, 23.3, size=0.6)
    track("leg_ret", "In1.Cu", 0.3, [x, 23.3], [x, 12.2])
track("sw_a", "F.Cu", 0.4, "C55.2", [72.8, 22.6])

# ---------------------------------------------------------------- core: shunt R5
# LEG_RET current pad 1 joins Q6.3 on F (Q3.3 arrives through the In1 LEG_RET region and
# Q6.3's barrel, plus three vias beside pad 1). HV_RET pad 4 drops to the In1 plane through
# vias left of the pad (kept above the SW_B lane). Kelvin pads 2/3 are left for their own pair.
zone("leg_ret", "F.Cu", (31.0, 0.6, 41.2, 12.2), (41.2, 9.8, 42.6, 11.9), priority=3, name="leg_ret Q6.3-R5.1-R13.2")
for y in (4.0, 5.5, 7.0):
    via("leg_ret", 40.9, y, power=False)
zone("hv_ret", "F.Cu", (35.4, 13.3, 39.2, 16.9), priority=3, name="hv_ret R5.4")
for y in (13.9, 15.3):
    via("hv_ret", 35.8, y)

# ---------------------------------------------------------------- HV chains and the Kelvin pair
def chain_link(net, a, b, width=0.4):
    """Straight pad-to-pad link between neighbouring resistors of a high-voltage chain, with a
    bounded pad escape at each end (the part's own pins sit closer than the group spacing)."""
    pa, pb = GEO.pad(a), GEO.pad(b)
    track(net, "F.Cu", width, a, b)
    # each end's escape area covers the whole link (KiCad's enclosedByArea needs the full track)
    rect = [round(min(pa["x"], pb["x"]) - 0.9, 3), round(min(pa["y"], pb["y"]) - 0.9, 3),
            round(max(pa["x"], pb["x"]) + 0.9, 3), round(max(pa["y"], pb["y"]) + 0.9, 3)]
    for pp in (pa, pb):
        ESCAPES.append({"ref": pp["ref"], "pad": pp["pad"], "rect": rect})


# Bus divider for the AMC1311 (vertical at x 96.5): BUS_P at the top joins the In2 trunk.
for net, a, b in (("vdiv_1", "R26.2", "R27.1"), ("vdiv_2", "R27.2", "R28.1"), ("vdiv_3", "R28.2", "R29.1")):
    chain_link(net, a, b)
track("bus_p", "F.Cu", 0.4, "R26.1", [95.2, 60.5])
via("bus_p", 95.2, 60.5)
track("bus_p", "In2.Cu", 0.4, [95.2, 60.5], [95.2, 46.5])
ESCAPES.append({"ref": "R26", "pad": "1", "rect": [94.1, 59.6, 96.3, 63.2]})
# Tank bleed across the top of C21: RES_A (C21.1) - R22 - R23 - R24 - R25 - SW_B (B lane).
for net, a, b in (("crbleed_1", "R22.2", "R23.1"), ("crbleed_2", "R23.2", "R24.1"), ("crbleed_3", "R24.2", "R25.1")):
    chain_link(net, a, b)
track("res_a", "F.Cu", 0.4, "R22.1", [156.54, 50.0], "C21.1")
ESCAPES.append({"ref": "R22", "pad": "1", "rect": [154.0, 40.0, 157.8, 59.7]})
track("sw_b", "F.Cu", 0.4, "R25.2", [193.0, 44.0])
via("sw_b", 193.0, 44.0)
ESCAPES.append({"ref": "R25", "pad": "2", "rect": [188.3, 40.0, 193.6, 44.6]})
# Line zero-cross string taps.
for net, a, b in (("r1mid", "R67.2", "R68.1"), ("r2mid", "R69.2", "R70.1")):
    chain_link(net, a, b, 0.3)

# Shunt Kelvin pair R5 -> protection (In1, LOW group): vias beside pads 2 / 3, down the radial
# wedge between C40.2 and C38.2 (parallel to the HF-cap return currents into R5.4), along the
# bottom band of the core plane, into the protection block. KELVIN_P ends on the protection's
# own ground plane; KELVIN_N continues to R33.
track("ocp_kelvin_p", "F.Cu", 0.3, "R5.2", [36.0, 8.0])
via("ocp_kelvin_p", 36.0, 8.0)
track("ocp_kelvin_p", "In1.Cu", 0.3, [36.0, 8.0], [39.4, 11.4], [42.2, 11.4], [42.2, 42.6], [107.6, 42.6],
      [107.6, 53.5])
track("ocp_kelvin_n", "F.Cu", 0.3, "R5.3", [41.3, 15.2])
via("ocp_kelvin_n", 41.3, 15.2)


# PS2 (rear band) to the LS block. Its LOW outputs are walled off by the power lanes on F/B and
# by the BUS_P trunk on In2, so they cross on In1 inside the HV_RET trunk (same LOW group) at
# its right-hand corner, where a slot leaves the band's turn down to C5/C6 intact (x 198-209),
# then run between C21 and C22's pins and over J5 into the LS block.
track("n_ls", "In1.Cu", 0.4, "PS2.3", [211.0, 26.0], [211.0, 75.0], [151.0, 75.0], [145.2, 59.75],
      [121.0, 59.75], [121.0, 76.0])
track("v24_raw", "In1.Cu", 0.4, "PS2.4", [212.2, 17.6], [212.2, 76.0], [150.0, 76.0], [144.3, 60.55],
      [121.8, 60.55], [121.8, 77.0], [117.6, 77.0])
V24 = GEO.via_spot("U26.15", width=0.3)
track("v24_raw", "In1.Cu", 0.4, [117.6, 77.0], list(V24))
via("v24_raw", *V24)
track("v24_raw", "F.Cu", 0.3, list(V24), "U26.15")
# TCO loop: J3.2 (TCO_L) along the rear edge to PS2.1; J3.1 (L_FILT) from the B lane.
track("tco_l", "F.Cu", 0.4, "PS2.1", [165.0, 1.0], [221.6, 1.0], [221.6, 5.95], "J3.2")
track("l_filt", "B.Cu", 0.5, [214.0, 30.0], [214.0, 7.6], "J3.1")
ESCAPES.append({"ref": "J3", "pad": "1", "rect": [212.9, 4.0, 218.0, 30.5], "layer": "B.Cu"})
ESCAPES.append({"ref": "J3", "pad": "2", "rect": [217.5, 0.4, 222.4, 7.5]})


# Core distribution of the LS rails and gate-network sources.
# U2's VSSA (N_HB) and VDDB (V15_LS) pins rise between the OUTA and OUTB tracks to vias.
track("n_hb", "F.Cu", 0.3, "U2.14", [31.09, 40.0])
via("n_hb", 31.09, 40.0, size=0.6)
track("v15_ls", "F.Cu", 0.3, "U2.11", [34.91, 41.0])
via("v15_ls", 34.91, 41.0, size=0.6)
# N_LS / LEG_RET / V15_LS along In1 above the Kelvin pair, from vias just east of the LS-B bank,
# turning down east of the Kelvin pair and ending above its last leg (y < 72): N_LS joins PS2's
# N_LS feed at x 120.2, LEG_RET and V15_LS stop at the top of the protection block (the
# remaining-connection pass takes them on to their pads).
LS_LINES = {"n_ls": (39.2, 121.0, (54.8, 39.2), 59.75), "leg_ret": (40.0, 110.0, (55.6, 40.0), 52.0),
            "v15_ls": (40.8, 109.0, (56.4, 40.8), 60.0)}
for net, (yl, xv, sp, yend) in LS_LINES.items():
    via(net, *sp, size=0.6)
    track(net, "In1.Cu", 0.4, list(sp), [xv, yl], [xv, yend])

# KELVIN_N's last leg, after the PS2 feeds are in place (its via must clear them).
KN = (119.95, 72.4)        # just below R33.2, clear of PS2's V24_RAW feed (x 121)
track("ocp_kelvin_n", "In1.Cu", 0.3, [41.3, 15.2], [41.3, 43.4], [106.6, 43.4], [106.6, KN[1]], list(KN))
via("ocp_kelvin_n", *KN)
track("ocp_kelvin_n", "F.Cu", 0.3, list(KN), "R33.2")

# Bring-up / coil stud lands: each REDCUBE's four same-number pads joined on F and B.
for ref, (cx, cy) in {"J9": (130.0, 6.5), "J10": (143.0, 6.5), "J7": (130.0, 19.5), "J8": (143.0, 19.5),
                      "J5": (132.0, 70.5), "J2": (132.0, 85.5)}.items():
    n = [p["net"] for p in GEO.pads if p["ref"] == ref and p["net"]][0]
    for lay in ("F.Cu", "B.Cu"):
        zone(n, lay, (cx - 4.6, cy - 4.6, cx + 4.6, cy + 4.6), priority=4, name=f"{ref} stud land")

# Mains input (line current): J1.1 -> fuse line clips on F; fuse load clips (L_F) on F down to
# C1.1 / L1.1 and along a band over C1 to the varistor; AC_N_IN on B from J1.2 down the right
# edge and back along y 26.5-36 to RV1.2, C1.2 and L1.2 (stacked under L_F where they run together).
zone("ac_l_in", "F.Cu", (251.5, 0.6, 283.0, 8.9), name="ac_l_in J1-F1")
zone("l_f", "F.Cu", (223.5, 0.6, 237.5, 9.0), (229.5, 9.0, 240.0, 25.6), (229.5, 25.6, 236.8, 33.5),
     (235.0, 12.1, 278.5, 15.1), (273.5, 12.1, 279.5, 26.5), name="l_f F1-C1-L1-RV1")
zone("ac_n_in", "B.Cu", (283.6, 3.5, 289.4, 40.0), (239.5, 26.5, 289.4, 36.0), (257.5, 15.5, 264.5, 30.0),
     name="ac_n_in J1-RV1-C1-L1")
# Filtered mains down under C5's body: L_FILT on F to the zero-cross string and PS1's line pin,
# N_FILT on B to the string, C4 and PS1's neutral pin.
# L_FILT drops to B past U36's LED pins and the string, back to F under PS1's body.
track("l_filt", "F.Cu", 1.0, "L1.4", [230.0, 60.0], [230.0, 92.5])
track("l_filt", "F.Cu", 0.6, [230.0, 92.5], "R67.1")
ESCAPES.append({"ref": "R67", "pad": "1", "rect": [229.3, 91.8, 232.4, 96.4]})
via("l_filt", 230.0, 92.5)
track("l_filt", "B.Cu", 1.0, [230.0, 92.5], [230.5, 93.5], [230.5, 107.0])
track("l_filt", "B.Cu", 0.6, [230.5, 102.8], "C3.1")
via("l_filt", 230.5, 107.0)
track("l_filt", "F.Cu", 1.0, [230.5, 107.0], [250.0, 130.0], "PS1.1")
track("n_filt", "B.Cu", 1.0, "L1.3", [241.0, 59.0], [238.0, 62.0], [237.5, 64.0], [237.5, 113.0], [250.0, 113.0],
      "PS1.2")
track("n_filt", "B.Cu", 0.6, [237.5, 111.5], [226.0, 111.5], "C4.1")
track("n_filt", "B.Cu", 0.6, [237.5, 107.0], [243.5, 107.0])
via("n_filt", 243.5, 107.0)
track("n_filt", "F.Cu", 0.6, [243.5, 107.0], "R70.2")
ESCAPES.append({"ref": "R70", "pad": "2", "rect": [242.1, 100.6, 244.4, 107.8]})
# Bus bleed: R3 (BUS_P end to the In2 trunk, bleed end over D3) - R4 (HV_RET end to the In1 trunk).
track("busbleed_mid", "F.Cu", 0.4, "R3.2", [248.04, 100.8], [281.54, 100.8], "R4.1")
ESCAPES.append({"ref": "R3", "pad": "2", "rect": [247.2, 100.0, 249.0, 107.3]})
ESCAPES.append({"ref": "R4", "pad": "1", "rect": [280.6, 100.0, 282.4, 107.3]})
track("bus_p", "F.Cu", 0.6, "R3.1", "D3.1")
ESCAPES.append({"ref": "R3", "pad": "1", "rect": [250.0, 105.0, 255.2, 107.0]})
track("hv_ret", "F.Cu", 0.4, "R4.2", [286.6, 106.0])
ESCAPES.append({"ref": "R4", "pad": "2", "rect": [283.5, 105.0, 287.3, 107.0]})
via("hv_ret", 286.6, 106.0)
# X-cap bleeder R1 (L_F) - R2 (AC_N_IN).
chain_link("xbleed_mid", "R1.2", "R2.1", 0.3)
track("l_f", "F.Cu", 0.4, [224.54, 8.6], "R1.1")
ESCAPES.append({"ref": "R1", "pad": "1", "rect": [223.4, 8.0, 225.7, 15.9]})
track("ac_n_in", "F.Cu", 0.4, "R2.2", [229.0, 25.0])
via("ac_n_in", 229.0, 25.0)
track("ac_n_in", "B.Cu", 0.6, [229.0, 25.0], [238.5, 25.0], [240.5, 26.8])
ESCAPES.append({"ref": "R2", "pad": "2", "rect": [226.3, 22.0, 229.9, 25.9]})

# SN6507 (U35, LS block) to both high-side transformer primaries: three LOW tracks along the
# bottom band of the core plane on In1 (below the Kelvin pair), each tapping T2 and T3 through a
# via and a short F.Cu drop; pin order (SW1, V24, V24, SW2) kept so nothing crosses.
# (band line y, vertical x, horizontal y, T2 via x, T3 via x, U35 via, horizontal end x)
# Verticals run down through the protection / LS-block In1 planes (LOW) right of the bus
# divider and left of the Kelvin pair's turn.
T_LINES = {"bias_sw2": (44.4, 103.0, 82.0, 56.6, 9.5, (107.3, 85.0), 107.3),
           "v24_raw": (45.5, 101.9, 87.6, 54.6, 7.6, (100.4, 87.6), 100.4),
           "bias_sw1": (46.6, 100.8, 85.4, 52.6, 5.7, (100.0, 85.4), 100.0)}
U35_PIN = {"bias_sw1": "U35.1", "v24_raw": "U35.3", "bias_sw2": "U35.10"}
for net, (yb, xv, yh, xt2, xt3, spot, xe) in T_LINES.items():
    if net == "bias_sw2":      # leave pin 10 sideways, clear of pin 9 (N_LS) below it
        track(net, "F.Cu", 0.2, U35_PIN[net], [107.3, 86.045], list(spot))
    elif net == "bias_sw1":    # leave pin 1 sideways, clear of pin 2 (N_LS) below it
        track(net, "F.Cu", 0.2, U35_PIN[net], [100.6, 86.045], list(spot))
    else:
        track(net, "F.Cu", 0.25, U35_PIN[net], list(spot))
    via(net, *spot)
    track(net, "In1.Cu", 0.4, list(spot), [xv, yh], [xv, yb], [xt2, yb], [xt3, yb])
    via(net, xt2, yb)
    via(net, xt3, yb)
track("bias_sw1", "F.Cu", 0.4, [52.6, 46.6], [52.6, 58.0], "T2.1")
track("v24_raw", "F.Cu", 0.4, [54.6, 45.5], [54.6, 57.5], "T2.2", "T2.3")
track("bias_sw2", "F.Cu", 0.4, [56.6, 44.4], [56.6, 50.0], [60.25, 53.65], "T2.4")
track("bias_sw1", "F.Cu", 0.4, [5.7, 46.6], [5.7, 53.0], "T3.1")
track("v24_raw", "F.Cu", 0.4, [7.6, 45.5], [7.6, 53.0], "T3.2", "T3.3")
track("bias_sw2", "F.Cu", 0.4, [9.5, 44.4], [9.5, 49.0], [13.95, 53.45], "T3.4")

# ---------------------------------------------------------------- rail planes (islands)
# Each isolation island gets its own planes; KiCad's fill keeps them 8 mm (SELV) / 3.2 mm
# (other HOT groups) from everything else. Every SMD pad of a plane net gets a via beside it.
SELV_REGION = [(0.6, 114.0, 160.0, 139.4), (0.6, 139.4, 90.4, 189.4), (22.0, 52.0, 44.5, 114.0),
               (70.0, 52.0, 93.0, 114.0), (142.0, 131.0, 207.0, 139.4), (205.0, 92.8, 216.8, 139.4)]
# High-side islands: -2 V rail (N_Hx) on In1 (B under the HS reservoir bank); +15 V routed.
for leg, isl, bank in (("b", (0.6, 60.0, 22.0, 119.0), (12.0, 30.6, 28.5, 48.0)),
                       ("a", (44.5, 64.0, 70.0, 119.0), (58.5, 30.6, 75.5, 48.0))):
    zone(f"n_h{leg}", "In1.Cu", isl, name=f"n_h{leg} island")
    # strip from the bank down into the island, kept 3.2 mm clear of the transformer primaries
    strip_x0 = 17.5 if leg == "b" else 64.5
    ext = [(28.5, 38.5, 31.4, 48.0)] if leg == "b" else []          # under U2.14 (VSSA) via
    zone(f"n_h{leg}", "B.Cu", bank, (strip_x0, bank[3], bank[2], isl[1] + 2.5), *ext, name=f"n_h{leg} bank")
# LOW blocks: protection (OCP_KELVIN_P ground) and LS bias (N_LS) on In1; HOT5 / V15_LS routed. B N_LS also
# under both LS reservoir banks, joined to the block past U1's SELV moat (x >= 92.5).
PROT, LSB = (100.5, 51.0, 123.0, 75.3), (100.5, 75.3, 123.0, 113.0)
zone("ocp_kelvin_p", "In1.Cu", PROT, name="ocp_kelvin_p protection")
zone("n_ls", "In1.Cu", LSB, name="n_ls LS block")
zone("n_ls", "B.Cu", (84.0, 30.6, 97.3, 48.0), name="n_ls LS-A bank")
zone("n_ls", "B.Cu", (37.5, 30.6, 54.0, 48.0), name="n_ls LS-B bank")
# SELV planes last, so they are clipped against every HOT pour above (plan view, 8.2 mm).
zone("v3v3", "In1.Cu", *SELV_REGION, name="v3v3 SELV island")
zone("selv_gnd", "In2.Cu", *SELV_REGION, name="selv_gnd SELV island")

# Long SELV runs first, before the pad fan-outs crowd the driver tongues (F/B only; the SELV
# planes on In1/In2 stay whole). U2's PWM pair lands on J4 from B, U1's from F, so they cross.
SELV_LONG = [("pwm_hb", ["U2.1", "J4.7"], (20, 50, 62, 189)), ("pwm_lb", ["U2.2", "J4.8"], (20, 50, 62, 189)),
             ("pwm_ha", ["U1.1", "J4.5"], (40, 50, 95, 189)), ("pwm_la", ["U1.2", "J4.6"], (40, 50, 95, 189)),
             ("permit", ["R14.1", "R6.1", "J4.9"], (20, 60, 95, 189)),
             ("bias_bad", ["U23.2", "U22.2", "U40.4"], (5, 55, 95, 140)),
             ("bias_hb_bad", ["U34.13", "U25.6"], (0.6, 100, 40, 140)),
             ("bias_ha_bad", ["U33.13", "U25.3"], (0.6, 100, 90, 140)),
             ("line_zc", ["U24.4", "J4.16"], (0.6, 120, 90.4, 189)),
             ("line_zc_raw", ["U36.4", "R125.2", "U24.2"], (0.6, 90, 217, 139.4)),
             ("pe", ["C3.2", "C4.2", "J6.1", "J6.2", "R38.1"], (0.6, 95, 217, 139.4))]
for net, pads_, bx in SELV_LONG:
    link(net, "F+B", bx, 0.3 if net != "pe" else 0.6, pads_)

# bank (B) to island (In1) for each high-side -2 V rail
for net, x, y in (("n_hb", 18.6, 61.6), ("n_hb", 19.4, 62.4), ("n_ha", 65.6, 65.6), ("n_ha", 66.4, 66.0)):
    via(net, x, y)
fanout("v3v3", (0, 52, 160, 190), "In1.Cu")
fanout("selv_gnd", (0, 52, 160, 190), "In2.Cu")
for leg, isl, bank in (("b", (0, 30, 29, 120), None), ("a", (44, 30, 76, 120), None)):  # noqa
    fanout(f"n_h{leg}", (isl[0], isl[1], isl[2], 48.5), "B.Cu")
    fanout(f"n_h{leg}", (isl[0], 58.0, isl[2], isl[3]), "In1.Cu")
fanout("ocp_kelvin_p", PROT, "In1.Cu")
fanout("n_ls", (84, 30, 100, 49), "B.Cu")
fanout("n_ls", (100, 75.3, 124, 114), "In1.Cu")
fanout("n_ls", (37, 30, 55, 49), "B.Cu")

# ---------------------------------------------------------------- remaining connections
# Everything still open after the explicit copper above is listed in todo.json as pad pairs
# (KiCad's ratsnest of the previous build, `make_todo.py`). Each pair is joined inside the
# rules: every pour is an obstacle except the corridors opened here for LOW-group wiring on
# In1 (the radial wedge between C40.2 and C38.2 under R5, the band along the bottom of the
# core plane, the trunk band), so the return planes keep their shape.
OPEN_IN1 = [(30.0, 0.6, 58.0, 12.5), (40.4, 12.0, 44.6, 38.6), (0.6, 38.5, 101.0, 47.0),
            (77.0, 27.2, 214.0, 50.5)]


def protect_pours():
    from shapely.geometry import Polygon
    opened = unary_union([box(*r) for r in OPEN_IN1])
    for z in ZONES:
        if z["net"] not in ("hv_ret", "bus_p") or z["layer"] not in ("In1.Cu", "In2.Cu"):
            continue          # island / SELV / LOW-block planes yield to vias; lanes protected at creation
        poly = Polygon(z["outline"], z["holes"])
        if z["layer"] == "In1.Cu":
            poly = poly.difference(opened)
        if not poly.is_empty:
            GEO.protect(z["net"], z["layer"], poly, via_ok=True)


# In2 inside the islands and the LOW blocks is a signal layer (their +15 V / HOT5 rails are
# routed, only the reference planes are poured); elsewhere In2 is the protected BUS_P trunk.
LAYERS_FOR = {"LOW": ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"), "SW_A": ("F.Cu", "In2.Cu", "B.Cu"),
              "SW_B": ("F.Cu", "In2.Cu", "B.Cu")}

# ---------------------------------------------------------------- island-local signals (F.Cu)
protect_pours()
L3 = ("F.Cu", "In2.Cu", "B.Cu")
island_signals((0.6, 34.0, 28.0, 120.0), layer=L3)            # SW_B island
island_signals((44.0, 50.0, 70.5, 120.0), layer=L3)           # SW_A island
island_signals((100.0, 50.0, 123.5, 114.0), layer=L3)         # protection + LS block
island_signals((0.6, 113.0, 160.0, 189.4))          # SELV band + tongue

TODO = HERE / "todo.json"
if TODO.exists():
    import rules21
    for net, a, b in json.loads(TODO.read_text()):
        group = rules21.GROUP.get(net)
        layers = LAYERS_FOR.get(group, ("F.Cu", "B.Cu"))
        if rules21.domain(net) == "SELV":
            # SELV signals may use In1/In2 inside the SELV region (only the SELV planes live there,
            # and they yield); the plan-view barrier keeps them out of everything else.
            layers = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
        w = 0.4 if net in ("leg_ret", "v15_ls", "n_ls", "v24_raw", "bias_sw1", "bias_sw2", "hot5",
                           "v15_selv", "pe", "l_filt", "n_filt", "l_f", "ac_n_in", "ac_l_in", "tco_l") else 0.25
        try:
            link(net, layers, (0.6, 0.6, 289.4, 189.4), w, [a, b])
        except KeyError:
            LINK_LOG.append((net, "?", 2, [a, b]))

if __name__ == "__main__":
    (HERE / "copper.json").write_text(json.dumps({"zones": ZONES, "tracks": TRACKS, "vias": VIAS,
                                                  "escapes": ESCAPES}, indent=1) + "\n")
    print(len(ZONES), "zones", len(TRACKS), "tracks", len(VIAS), "vias")
    for net, layer, done, missed in FANOUT_LOG:
        print(f"fanout {net:14s} {layer:7s} {done:3d} vias", ("missed " + " ".join(missed)) if missed else "")
    bad = [(n, f) for n, _, _, f in LINK_LOG if f]
    print("links", len(LINK_LOG), "failed", len(bad), bad[:20])
