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

from shapely.geometry import box
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
    shape = unary_union([box(*r) for r in rects])
    PLANES[(net, layer)] = unary_union([PLANES.get((net, layer), shape), shape])
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


def via(net, x, y, power=False):
    spec = POWER_VIA if power else {"size": 0.85, "drill": 0.3}
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
        spot = GEO.via_spot(rp, within=target)
        if spot is None:
            missed.append(rp)
            continue
        track(net, "F.Cu", 0.4, rp, list(spot))
        via(net, *spot)
        done += 1
    FANOUT_LOG.append((net, layer, done, missed))


FANOUT_LOG = []

LINK_LOG = []


def link(net, layer, bx, width, pads):
    """Join `pads` ("REF.PAD") inside box `bx`, nearest pad first (a minimum tree). Bends (and,
    when `layer` is "F+B", F/B vias) come from maze21; each leg is recorded as explicit copper."""
    # never wider than the narrowest pad it lands on (fine-pitch pins)
    width = min([width] + [min(b[2] - b[0], b[3] - b[1]) * 0.9 for b in (GEO.pad(pp)["box"] for pp in pads)])
    width = max(round(width, 2), 0.2)
    layers = ("F.Cu", "B.Cu") if layer == "F+B" else (layer if isinstance(layer, tuple) else None)
    two = layers is not None
    pts = {pp: _xy(pp) for pp in pads}
    lidx = {pp: (None if GEO.pad(pp)["tht"] else 0) for pp in pads}
    tree = [(*pts[pads[0]], lidx[pads[0]] if two else 0)]
    todo = list(pads[1:])
    failed = []
    while todo:
        todo.sort(key=lambda q: min(math.dist(pts[q], t[:2]) for t in tree))
        q = todo.pop(0)
        res = None
        near = min(tree, key=lambda t: math.dist(t[:2], pts[q]))
        for m in (4.0, 10.0, None):
            sub = bx if m is None else (max(bx[0], min(near[0], pts[q][0]) - m), max(bx[1], min(near[1], pts[q][1]) - m),
                                        min(bx[2], max(near[0], pts[q][0]) + m), min(bx[3], max(near[1], pts[q][1]) + m))
            starts = [t for t in tree if sub[0] <= t[0] <= sub[2] and sub[1] <= t[1] <= sub[3]] or [near]
            if two:
                res = maze21.connect2(GEO, net, sub, width, starts, [(*pts[q], lidx[q])], layers=layers)
            else:
                p = maze21.connect(GEO, net, layer, sub, width, [t[:2] for t in starts], [pts[q]])
                res = None if p is None else ([(layer, p)], [])
            if res is not None:
                break
        if res is None:
            failed.append(q)
            continue
        segs, vs = res
        lays = layers or (layer,)
        for lay, path in segs:
            track(net, lay, width, *path)
            tree.extend((x, y, lays.index(lay)) for x, y in path)
        for x, y in vs:
            VIAS.append({"net": net, "at": [x, y], "size": 0.75, "drill": 0.3})
            GEO.add_via(net, x, y, 0.75)
            tree.extend((x, y, k) for k in range(len(lays)))
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
zone("leg_ret", "In1.Cu", (30.0, 0.6, 58.0, 12.5), priority=2, name="leg_ret sources")

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
     (103.6, 19.2, 110.0, 48.0), (103.6, 37.2, 148.6, 48.0), (140.5, 37.2, 148.6, 101.5),
     name="sw_a Q2.3-T1.1", protect=True)
zone("sw_a", "B.Cu", (46.5, 0.6, 76.5, 16.0), name="sw_a leg-A link", protect=True)
# SW_B: leg-B pins, a lane under leg A between the shunt vias (y < 16) and the HF-row pins
# (y > 30.6), a 4.6 mm neck past C39.1, then down right of the LS-A bank (its vias stay free).
zone("sw_b", "B.Cu", (12.5, 0.6, 31.0, 27.0), (12.5, 19.4, 77.0, 27.0), (77.0, 19.4, 100.5, 27.3),
     (79.7, 9.8, 83.7, 23.8), (100.5, 19.7, 110.0, 50.0), (100.5, 37.2, 200.6, 50.0),
     (192.0, 37.2, 200.6, 113.0), name="sw_b leg B-C21..C23", protect=True)
zone("res_a", "B.Cu", (126.0, 64.0, 161.0, 77.0), (150.0, 55.0, 161.0, 114.0), name="res_a J5-C21..C23", protect=True)
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
track("leg_b-out_l", "F.Cu", 0.6, [35.0, 17.9], [35.0, 18.9], [35.6, 21.5], [35.6, 44.5], [36.17, 46.12])
# Leg A low side: down to a via below the HF row, In1 (LOW, inside the HV_RET plane) under
# the leg-A high-side area, up beside U1.
track("leg_a-out_l", "F.Cu", 0.6, [57.1, 17.9], [57.1, 18.9], [56.0, 20.5], [56.0, 31.0])
via("leg_a-out_l", 56.0, 31.0)
track("leg_a-out_l", "In1.Cu", 0.5, [56.0, 31.0], [56.0, 33.6], [82.0, 33.6], [82.0, 41.5])
via("leg_a-out_l", 82.0, 41.5)
track("leg_a-out_l", "F.Cu", 0.5, [82.0, 41.5], [83.22, 43.5], [83.22, 46.12])
# Leg A high side: down the SW_A pour beside Q2.3, left of C39.1.
track("leg_a-out_h", "F.Cu", 0.6, [75.1, 17.9], [75.1, 18.9], [77.0, 20.5], [77.0, 44.0], [76.87, 46.12])

# ---------------------------------------------------------------- core: shunt R5
# LEG_RET current pad 1 joins Q6.3 on F (Q3.3 arrives through the In1 LEG_RET region and
# Q6.3's barrel, plus three vias beside pad 1). HV_RET pad 4 drops to the In1 plane through
# vias left of the pad (kept above the SW_B lane). Kelvin pads 2/3 are left for their own pair.
zone("leg_ret", "F.Cu", (31.0, 0.6, 41.2, 12.2), priority=3, name="leg_ret Q6.3-R5.1")
for y in (4.0, 5.5, 7.0):
    via("leg_ret", 40.9, y, power=False)
zone("hv_ret", "F.Cu", (35.4, 13.3, 39.2, 16.9), priority=3, name="hv_ret R5.4")
for y in (13.9, 15.3):
    via("hv_ret", 35.8, y)

# ---------------------------------------------------------------- rail planes (islands)
# Each isolation island gets its own planes; KiCad's fill keeps them 8 mm (SELV) / 3.2 mm
# (other HOT groups) from everything else. Every SMD pad of a plane net gets a via beside it.
SELV_REGION = [(0.6, 114.0, 160.0, 139.4), (0.6, 139.4, 90.4, 189.4), (22.0, 52.0, 44.5, 114.0),
               (70.0, 52.0, 93.0, 114.0), (142.0, 131.0, 207.0, 139.4), (205.0, 92.8, 216.8, 139.4)]
zone("v3v3", "In1.Cu", *SELV_REGION, name="v3v3 SELV island")
zone("selv_gnd", "In2.Cu", *SELV_REGION, name="selv_gnd SELV island")
# High-side islands: -2 V rail (N_Hx) on In1 and B (B continues up under the HS reservoir bank),
# +15 V (P_Hx) on In2.
for leg, isl, bank in (("b", (0.6, 60.0, 22.0, 119.0), (12.0, 30.6, 28.5, 48.0)),
                       ("a", (44.5, 64.0, 70.0, 119.0), (58.5, 30.6, 75.5, 48.0))):
    zone(f"n_h{leg}", "In1.Cu", isl, name=f"n_h{leg} island")
    zone(f"n_h{leg}", "B.Cu", bank, (bank[0], bank[3], bank[2], isl[1] + 2.5), name=f"n_h{leg} bank")
    zone(f"p_h{leg}", "In2.Cu", isl, name=f"p_h{leg} island")
# LOW blocks: protection (OCP_KELVIN_P ground, HOT5) and LS bias (N_LS, V15_LS); B N_LS also
# under both LS reservoir banks, joined to the block past U1's SELV moat (x >= 92.5).
PROT, LSB = (100.5, 51.0, 123.0, 75.3), (100.5, 75.3, 123.0, 113.0)
zone("ocp_kelvin_p", "In1.Cu", PROT, name="ocp_kelvin_p protection")
zone("hot5", "In2.Cu", PROT, name="hot5 protection")
zone("n_ls", "In1.Cu", LSB, name="n_ls LS block")
zone("v15_ls", "In2.Cu", LSB, name="v15_ls LS block")
zone("n_ls", "B.Cu", (84.0, 30.6, 97.3, 48.0), (92.5, 48.0, 97.3, 56.0), (92.5, 53.5, 103.0, 56.0),
     name="n_ls LS-A bank to LS block")
zone("n_ls", "B.Cu", (37.5, 30.6, 54.0, 48.0), name="n_ls LS-B bank")

fanout("v3v3", (0, 52, 160, 190), "In1.Cu")
fanout("selv_gnd", (0, 52, 160, 190), "In2.Cu")
for leg, isl, bank in (("b", (0, 30, 29, 120), None), ("a", (44, 30, 76, 120), None)):  # noqa
    fanout(f"n_h{leg}", (isl[0], isl[1], isl[2], 48.5), "B.Cu")
    fanout(f"n_h{leg}", (isl[0], 58.0, isl[2], isl[3]), "In1.Cu")
    fanout(f"p_h{leg}", (isl[0], 58.0, isl[2], 120), "In2.Cu")
fanout("ocp_kelvin_p", PROT, "In1.Cu")
fanout("hot5", PROT, "In2.Cu")
fanout("n_ls", (84, 30, 100, 49), "B.Cu")
fanout("n_ls", (100, 75.3, 124, 114), "In1.Cu")
fanout("n_ls", (37, 30, 55, 49), "B.Cu")
fanout("v15_ls", LSB, "In2.Cu")

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
        poly = Polygon(z["outline"], z["holes"])
        if z["layer"] == "In1.Cu":
            poly = poly.difference(opened)
        if not poly.is_empty:
            GEO.protect(z["net"], z["layer"], poly)


LAYERS_FOR = {"LOW": ("F.Cu", "In1.Cu", "B.Cu")}

# ---------------------------------------------------------------- island-local signals (F.Cu)
island_signals((0.6, 34.0, 28.0, 120.0))            # SW_B island
island_signals((44.0, 50.0, 70.5, 120.0))           # SW_A island
island_signals((100.0, 50.0, 123.5, 114.0))         # protection + LS block
island_signals((0.6, 113.0, 160.0, 189.4))          # SELV band + tongue

protect_pours()
TODO = HERE / "todo.json"
if TODO.exists():
    import rules21
    for net, a, b in json.loads(TODO.read_text()):
        group = rules21.GROUP.get(net)
        layers = LAYERS_FOR.get(group, ("F.Cu", "B.Cu"))
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
