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
REMOVE_ESCAPES = []
HANDLED = ()

# R5 shunt current pads (task 04 round 5): native-21 fed R5.4 (HV_RET) through two 0.3 mm vias on
# a small F.Cu island and R5.1 (LEG_RET) through three at x 40.9. Up to 18 A in one via in the
# coherent return case, where native-17 had three 0.8 mm vias per side. Six filled 0.3 mm vias in
# each current pad take the layer transfer at the pad (a shunt's current pads carry their own vias).
IN_PAD = ("R5",)
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


def add(g):
    from patches21_v1 import put
    drill(g, "sw_a", *TIE)
    put(g, "sw_a", "B.Cu", 0.4, list(TIE), [TIE[0], 12.0])
    add_r5(g)


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
