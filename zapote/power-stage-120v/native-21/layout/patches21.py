"""Stage-6 hand fixes, applied by incr21.py on top of the frozen stage-5 copper (copper_base.json =
the routed stage-5 copper.json, c450f12c). The stage-4/5 record that produced it is patches21_v1.py;
its helpers are reused here.

REMOVE / add(g) / OPEN_IN1 / HANDLED as in patches21_v1.py. IN_PAD: references whose pad vias are
intended (filled and capped, DECISIONS.md 2026-10-08) and must not be moved off by dogbone().
"""
from patches21_v1 import CU, OPEN_IN1, drill  # noqa: F401  (OPEN_IN1 / CU re-exported for incr21)

# SW_B neck (task 04 round 5): SW_B's B.Cu lane narrowed to ~4.5 mm for ~16 mm under leg A
# (x 58-74), squeezed by the SW_A B.Cu link pour above (3.2 mm HOT spacing) and C38/C39's antipads
# below; an IPC-2221 20 K screen gives ~16 A against 21.5 A nominal tank RMS. The SW_A link pour only
# parallels SW_A's F.Cu path: trim it to y <= 12.5 and raise SW_B's lane top to 15.7 (3.2 mm apart).
# The high-side Cgs / R71 return island on F.Cu (C55.2) reaches SW_A's B.Cu pour through one via (the
# F6 gate-loop return): it moves from (73.1, 15.8) to (73.1, 15.2) with a B.Cu stub into the trimmed
# pour, and SW_B's raise keeps HOT spacing round it (TIE_KEEPOUT).
TIE = (73.1, 15.2)
TIE_KEEPOUT = 0.3 + 3.2 + 0.2
SWA_TRIM = (58.0, 12.5, 76.6, 16.1)
SWB_RAISE = (57.0, 15.7, 79.7, 19.4)
REMOVE = [{"net": "sw_a", "box": [72.9, 15.6, 73.3, 16.0], "kind": "via"},
          {"net": "sw_a", "box": [59.8, 11.1, 73.2, 15.9], "kind": "track", "layer": "B.Cu"}]
# Stage 9 (review B1): each UCC21550 output leaves its pin as a 0.3 mm neck under a stack of 0805
# VDD-VSS caps (place.py STACK); the four base output polylines are re-laid in add_stack, identical
# beyond the neck. Also the dead In1 leg_ret stub (55.6-95.4 at y 40, lying on the full 55.6-110 run;
# closure review N3).
REMOVE += [{"net": n, "box": [x - 0.5, 45.5, x + 0.5, 46.5], "kind": "track", "layer": "F.Cu", "touch": True}
           for n, x in (("leg_a-out_h", 76.87), ("leg_a-out_l", 83.22), ("leg_b-out_h", 29.82), ("leg_b-out_l", 36.17))]
REMOVE += [{"net": "leg_ret", "box": [55.5, 39.9, 95.5, 40.1], "kind": "track", "layer": "In1.Cu"}]
REMOVE_ESCAPES = [("J3", "1"), ("J3", "2")]   # the 3.96 mm J3 pin escapes; the 7.92 mm B2P3-VH needs none (M7)
HANDLED = ()

# R5 shunt current pads (task 04 round 5): native-21 fed R5.4 (HV_RET) through two 0.3 mm vias on
# a small F.Cu island and R5.1 (LEG_RET) through three at x 40.9. Up to 18 A in one via in the
# coherent return case, where native-17 had three 0.8 mm vias per side. Six filled 0.3 mm vias in
# each current pad take the layer transfer at the pad (a shunt's current pads carry their own vias).
IN_PAD = ("R5", "U26", "U27", "U28", "U35")
# SW_B's B.Cu outline reaches under R5, but its fill never does (0 mm² in this box on the stage-5
# board): the outline alone kept HV_RET vias out of R5.4. Clip it there.
SWB_CLIP = (34.0, 12.0, 42.0, 18.0)


# Stage 12: F1 is a Class CC fuse in 10x38 clips at (252.00, 7.25) (owner-items/f1cc/). The F.Cu mains
# pours are redrawn round its new pads: ac_l_in shrinks to x 257-283 (pads 262.08 / 272.88 and J1.1);
# l_f's top block reaches x 243.5 (pads 231.12 / 241.92) and its strip under the ac_l_in clip starts at
# y 12.3, 3.2 mm from the clip pads (pad edge y 9.10).
MAINS_POURS = {("ac_l_in", "F.Cu"): [[257.0, 0.6], [257.0, 9.1], [283.0, 9.1], [283.0, 0.6]],
               ("l_f", "F.Cu"): [[229.5, 9.0], [229.5, 33.5], [236.8, 33.5], [236.8, 25.6], [240.0, 25.6],
                                 [240.0, 15.1], [273.5, 15.1], [273.5, 26.5], [279.5, 26.5], [279.5, 12.3],
                                 [240.0, 12.3], [240.0, 9.0], [243.5, 9.0], [243.5, 0.6], [223.5, 0.6],
                                 [223.5, 9.0]]}


# Stage 13: resonant bank becomes 5 radial TDK B32654 (pins x 163.0 / 190.5, rows y 53.2-111.5). The B.Cu
# res_a strip widens to x 166 and spans y 52.0-112.9; the sw_b band's lower edge rises from y 50 to 46.8
# between x 150 and 188 (5 mm tank rule to the res_a strip), and the sw_b strip widens to x 188 and
# reaches y 112.9. The last pad edges stay >= 8 mm from the SELV line_zc-raw run (B.Cu, y 121.1).
RES_A_STRIP = (150.0, 52.0, 166.0, 112.9)
SWB_STRIP = (188.0, 46.8, 200.6, 112.9)
SWB_BAND_TRIM = (150.0, 46.8, 188.0, 50.1)


def edit_zones(zones):
    from shapely.geometry import Polygon, box
    out = []
    zones = [{**z, "outline": MAINS_POURS[(z["net"], z["layer"])], "holes": []}
             if (z["net"], z["layer"]) in MAINS_POURS else z for z in zones]
    for z in zones:
        poly = Polygon(z["outline"], z["holes"])
        if z["net"] == "sw_a" and z["layer"] == "B.Cu" and poly.intersects(box(*SWA_TRIM)):
            poly = poly.difference(box(*SWA_TRIM))
            poly = max(getattr(poly, "geoms", [poly]), key=lambda q: q.area)
            z = {**z, "outline": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
                 "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in poly.interiors]}
        if z["net"] == "sw_b" and z["layer"] == "B.Cu" and poly.intersects(box(*SWB_RAISE)):
            from shapely.geometry import Point as _Pt
            poly = poly.union(box(*SWB_RAISE).difference(_Pt(*TIE).buffer(TIE_KEEPOUT))).simplify(0)
            z = {**z, "outline": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
                 "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in poly.interiors]}
        if z["net"] == "sw_b" and z["layer"] == "B.Cu":
            poly = Polygon(z["outline"], z["holes"])
            if poly.intersects(box(*SWB_CLIP)):
                poly = poly.difference(box(*SWB_CLIP))
                poly = max(getattr(poly, "geoms", [poly]), key=lambda q: q.area)
                z = {**z, "outline": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
                     "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in poly.interiors]}
        if z["layer"] == "B.Cu" and z["net"] in ("res_a", "sw_b"):
            poly = Polygon(z["outline"], z["holes"])
            if z["net"] == "res_a" and poly.intersects(box(*RES_A_STRIP)):
                poly = poly.union(box(*RES_A_STRIP)).simplify(0)
            if z["net"] == "sw_b" and poly.intersects(box(*SWB_STRIP)):
                poly = poly.difference(box(*SWB_BAND_TRIM)).union(box(*SWB_STRIP)).simplify(0)
                poly = max(getattr(poly, "geoms", [poly]), key=lambda q: q.area)
            z = {**z, "outline": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
                 "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in poly.interiors]}
        out.append(z)
    return out
R5_PADS = {"leg_ret": "R5.1", "hv_ret": "R5.4"}
R5_MAX, R5_REACH = 10, 2.6


# Exposed-pad thermal vias (independent review 2026-10-08, B2): the TPS7A4700 LDOs (U26 LS ~0.95 W,
# U27 / U28 HS) and the SN6507 (U35) had none. Filled, capped 0.6 / 0.3 vias on a grid in each pad,
# into the part's own plane (n_ls / n_ha / n_hb); pitch 1.0 / 0.9 mm keeps merge_close_vias off them.
EP_VIAS = {"U26.21": (3, 1.0), "U27.21": (3, 1.0), "U28.21": (3, 1.0), "U35.11": (2, 0.9)}


def add_ep(g):
    """Thermal via field per exposed pad. Other nets' In1 / In2 / B.Cu tracks under the pad are
    cleared first (the next routing pass re-routes them) and the field is protected on those layers,
    so the router keeps out of it from then on."""
    from shapely.geometry import LineString, Point, box as _box
    G = g["GEO"]
    for ref_pad, (n, pitch) in EP_VIAS.items():
        pd = G.pad(ref_pad)
        cx, cy = (pd["box"][0] + pd["box"][2]) / 2, (pd["box"][1] + pd["box"][3]) / 2
        field = _box(*pd["box"]).buffer(0.45, join_style=2)
        cleared = set()
        for t in list(g["TRACKS"]):
            if t["net"] == pd["net"] or t["layer"] == "F.Cu":
                continue
            geom = LineString([g["_xy"](q) for q in t["points"]]).buffer(t["width"] / 2, cap_style=1)
            if not geom.intersects(field):
                continue
            g["TRACKS"].remove(t)
            items = G.items[t["layer"]]
            for k in range(len(items) - 1, -1, -1):
                gg, nn = items[k]
                if nn == t["net"] and abs(gg.area - geom.area) < 1e-6 and gg.centroid.distance(geom.centroid) < 1e-6:
                    del items[k]
                    break
            for k in range(len(G.items["PLAN"]) - 1, -1, -1):
                gg, nn = G.items["PLAN"][k]
                if nn == t["net"] and abs(gg.area - geom.area) < 1e-6 and gg.centroid.distance(geom.centroid) < 1e-6:
                    del G.items["PLAN"][k]
                    break
            G._trees.clear()
            cleared.add(t["net"])
        for lay in ("In1.Cu", "In2.Cu", "B.Cu"):
            G.protect(pd["net"], lay, field, via_ok=True)
        placed = 0
        for i in range(n):
            for j in range(n):
                x = round(cx + (i - (n - 1) / 2) * pitch, 3)
                y = round(cy + (j - (n - 1) / 2) * pitch, 3)
                if G.conflicts(pd["net"], CU, Point(x, y).buffer(0.3), limit=1, via=True):
                    continue
                drill(g, pd["net"], x, y, size=0.6)
                placed += 1
        print(f"EP {ref_pad}: {placed} thermal vias; cleared from under it: {sorted(cleared)}")


def add(g):
    from patches21_v1 import put
    drill(g, "sw_a", *TIE)
    put(g, "sw_a", "B.Cu", 0.4, list(TIE), [TIE[0], 12.0])
    add_r5(g)
    add_ep(g)
    add_stack(g)
    add_stage8(g)
    add_stage13(g)


# Output polylines (base copper), with the y where each leaves 0.6 / 0.5 mm for the 0.3 mm neck
OUT_POLY = {"leg_a-out_h": ("U1.15", 0.6, [[75.1, 17.9], [75.1, 18.9], [77.0, 20.5], [77.0, 38.3]], [76.83, 38.6]),
            "leg_a-out_l": ("U1.10", 0.5, [[82.0, 37.0], [83.17, 39.9]], None),
            "leg_b-out_h": ("U2.15", 0.6, [[17.0, 17.9], [17.0, 18.9], [12.6, 21.0], [12.6, 32.9], [29.82, 32.9],
                                           [29.82, 38.3]], [29.83, 38.6]),
            "leg_b-out_l": ("U2.10", 0.6, [[35.0, 17.9], [35.0, 18.9], [35.95, 21.5], [35.95, 39.6]], [36.17, 39.9])}
POURS = ("bus_p", "hv_ret", "leg_ret", "sw_a", "sw_b")    # pours the unchanged base routes cross; KiCad refills round them
ESC = {n: POURS for n in ("leg_a-out_h", "leg_a-out_l", "leg_b-out_h", "leg_b-out_l")}
# Pin -> stack columns: (pin, column x, top-of-stack y) per supply net; pads sit at 1.9 mm pitch
STACK_TIES = [("U1.16", "p_ha", 75.88, 39.75), ("U1.14", "n_ha", 77.78, 39.75),
              ("U1.11", "v15_ls", 82.22, 41.85), ("U1.9", "n_ls", 84.12, 41.85),
              ("U2.16", "p_hb", 28.88, 39.75), ("U2.14", "n_hb", 30.78, 39.75),
              ("U2.11", "v15_ls", 35.22, 41.85), ("U2.9", "n_ls", 37.12, 41.85)]


def add_stack(g):
    """Stage 9 (review B1): the UCC21550 VDD-VSS stacks. Each output leaves its pin as a 0.3 mm neck
    through its stack's 0.9 mm pad gap (0.3 mm clear both sides); the supply pins tie straight up
    to the pad columns (0.4 mm), so each cap's loop is pin - pad - pad - pin, ~3 mm, no vias."""
    from patches21_v1 import put
    for net, (pin, w, wide, jog) in OUT_POLY.items():
        # the wide part is the base polyline unchanged (DRC-clean through stage 8); the pours it
        # crosses refill round it, so put()'s pour-outline check is waived there (final DRC decides)
        put(g, net, "F.Cu", w, *wide, escape=ESC.get(net))
        put(g, net, "F.Cu", 0.3, wide[-1], *([jog] if jog else []), pin)
    for pin, net, x, top in STACK_TIES:
        put(g, net, "F.Cu", 0.4, pin, [x, 43.95], [x, top])


def add_stage8(g):
    """Stage-8 re-links (review M1 / B2 side effects): U33's VCC1 cap C137's new spot cut the old v5
    run; U27's exposed-pad via field cleared spanuv's In2 run under it, and U28's cleared leg B's ov
    run (the router reports it linked, but the join never closes). All three are re-linked here."""
    from patches21_v1 import route_group
    route_group(g, [("bias_ha.monitor-v5", ("F.Cu", "B.Cu"), (56.0, 96.0, 68.0, 114.0), 0.25, ["C137.1", "U33.3"]),
                    ("bias_ha.monitor-spanuv", CU, (44.0, 78.0, 58.0, 116.0), 0.2, ["U30.9", "C78.1"]),
                    ("bias_hb.monitor-ov", CU, (0.6, 70.0, 20.0, 114.0), 0.2, ["U31.4", "C84.1"])])


def add_stage13(g):
    """Stage 13: the resonant-bank bleed tap R22.1 -> RES_A. The base polyline served C21's old axial pad
    and is dropped with it. Re-laid on F.Cu down the base's own x 156.54 lane to the new C21 pin 1. The
    pad escape next to R22.2 (crbleed_1) is the base geometry, bounded by the DRU pad-escape rule, so
    put()'s check waives that partner and the final DRC decides. The B.Cu sw_b band is another layer."""
    from patches21_v1 import put
    put(g, "res_a", "F.Cu", 0.4, "R22.1", [156.54, 50.0], "C21.1", escape="crbleed_1")


def add_r5(g):
    """Up to R5_MAX legal 0.6 / 0.3 vias per R5 current pad, 0.85 mm apart (so merge_close_vias
    keeps them), on a 0.15 mm grid in the pad and in the same-net F.Cu copper within R5_REACH of it,
    nearest the pad centre first. Every spot is checked against all copper on every layer (the
    Kelvin pair runs under R5.1 on In1). Vias inside the pad are filled and capped."""
    from shapely.geometry import Point, Polygon, box as _box
    G = g["GEO"]
    for net, ref_pad in R5_PADS.items():
        pd = G.pad(ref_pad)
        x0, y0, x1, y1 = pd["box"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        pad = _box(x0, y0, x1, y1)
        pours = [Polygon(z["outline"], z["holes"]) for z in g["ZONES"] if z["net"] == net and z["layer"] == "F.Cu"]
        own = [Point(*v["at"]) for v in g["VIAS"] if v["net"] == net]
        cand = []
        for i in range(int((x1 - x0 + 2 * R5_REACH) / 0.15) + 1):
            for j in range(int((y1 - y0 + 2 * R5_REACH) / 0.15) + 1):
                c = Point(round(x0 - R5_REACH + i * 0.15, 3), round(y0 - R5_REACH + j * 0.15, 3))
                if pad.buffer(-0.3).contains(c) or any(q.buffer(-0.35).contains(c) for q in pours):
                    if pad.distance(c) <= R5_REACH:
                        cand.append(c)
        placed = []
        for c in sorted(cand, key=lambda c: (round(c.distance(Point(cx, cy)), 3), c.x, c.y)):
            if len(placed) >= R5_MAX:
                break
            if any(c.distance(q) < 0.85 for q in placed + own):
                continue
            if G.conflicts(net, CU, c.buffer(0.3), limit=1, via=True):
                continue
            drill(g, net, c.x, c.y, size=0.6)
            placed.append(c)
        print(f"R5 {ref_pad}: {len(placed)} vias ({sum(pad.contains(q) for q in placed)} in the pad)")
