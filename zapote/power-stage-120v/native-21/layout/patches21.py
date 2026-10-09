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


def edit_zones(zones):
    from shapely.geometry import Polygon, box
    out = []
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
    add_stage8(g)


def add_stage8(g):
    """Stage-8 hand routes (review B1 / M1), laid before the incremental router so it routes round them.

    Leg A high side: the router spent the column right of the C10 / C11 stack on n_ha and left C11's
    p_ha pad boxed in by n_ha on both sides. Leg B routed itself in this topology, so leg A gets it
    by hand, all on F.Cu: no n_ha via can sit here, since leg A's LOW-group In1 runs (out_l y 34.7,
    n_ls / leg_ret / v15_ls y 39.2-40.8) are within the 3.2 mm HOT-group spacing everywhere in the
    stack. p_ha takes the right column (x 75.95, 0.6 mm from OUTA's lane): C10.1, C11.1 and the
    bleed resistor R71.1 (rotated so its p_ha pad faces the column). n_ha takes the left: C11.2 down
    to C50.2, the reservoir cap whose n_ha already reaches the pour; C10.2 joins it on the router.
    U33's VCC1 cap C137 (M1) and U30's spanuv line: the cap's new spot cut the old v5 run, and
    U27's exposed-pad via field cleared spanuv's In2 run under it, and U28's cleared leg B's ov run
    (the router reports it linked, but the join never closes); all three are re-linked here."""
    from patches21_v1 import put, route_group
    put(g, "p_ha", "F.Cu", 0.25, "C10.1", [75.95, 41.875], [75.95, 34.35], "R71.1")
    put(g, "p_ha", "F.Cu", 0.25, "C11.1", [75.95, 38.3])
    put(g, "n_ha", "F.Cu", 0.25, "C11.2", [73.3, 36.4], [73.3, 39.6], "C50.2")
    route_group(g, [("bias_ha.monitor-v5", ("F.Cu", "B.Cu"), (56.0, 96.0, 68.0, 114.0), 0.25, ["C137.1", "U33.3"]),
                    ("bias_ha.monitor-spanuv", CU, (44.0, 78.0, 58.0, 116.0), 0.2, ["U30.9", "C78.1"]),
                    ("bias_hb.monitor-ov", CU, (0.6, 70.0, 20.0, 114.0), 0.2, ["U31.4", "C84.1"])])


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
