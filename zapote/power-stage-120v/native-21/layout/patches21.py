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
# Stage 18 (DECISIONS 18): the SELV line_zc_raw / v15_selv B.Cu runs under the bank (y 121.3-123.6) are re-laid
# by add_stage18; these boxes hold exactly those two base polylines (their other B.Cu pieces lie at x < 80).
REMOVE += [{"net": "line_zc_raw", "box": [89.0, 100.0, 210.0, 130.0], "kind": "track", "layer": "B.Cu"},
           {"net": "v15_selv", "box": [76.0, 120.0, 211.0, 140.0], "kind": "track", "layer": "B.Cu"}]
# Stage 19 (DECISIONS 19): the SELV bypass row at y 127.1 (place.py STAGE19_MOVES) sits 7.84-7.88 mm from two
# base n_hb via-and-stub pairs at y 118.35 (C82.2 and R111.2 to the In1 n_hb pour, laid before the row moved up).
# Drop them: the router re-attaches both pads with the barrier check against the new pads.
REMOVE += [{"net": "n_hb", "box": [4.0, 118.0, 4.6, 118.7], "kind": "via"},
           {"net": "n_hb", "box": [4.0, 118.0, 4.6, 118.7], "kind": "track", "layer": "F.Cu", "touch": True},
           {"net": "n_hb", "box": [12.1, 118.0, 12.7, 118.7], "kind": "via"},
           {"net": "n_hb", "box": [12.1, 118.0, 12.7, 118.7], "kind": "track", "layer": "F.Cu", "touch": True}]
# Stage 19 (PI2): U26 moved east; the PS2 v24_raw In1 feed's last leg to the old IN 16 via is a dangling stub.
REMOVE += [{"net": "v24_raw", "box": [115.9, 76.7, 117.7, 77.1], "kind": "track", "layer": "In1.Cu"}]
# ... and its new thermal-pad field (add_ep) would cut the leg_ret B.Cu run (U16 side up to the protection block) and
# the hot5 In1 rail; both are taken out whole here and re-laid round the field by add_stage19_pi.
# Stage 19 (SI1): bus_fault_hot's last run to U9 follows the Kelvin chain on In2; the U29 monitor isolator input's
# In2 run crossed that lane (y 112.7-114.9) and is re-laid by the routing passes.
REMOVE += [{"net": "monitor_ls-isoin", "box": [104.0, 112.6, 104.5, 112.9], "kind": "track", "layer": "In2.Cu", "touch": True}]
REMOVE += [{"net": "n_ls", "box": [113.0, 82.2, 114.4, 82.9], "kind": "via"},
           {"net": "n_ls", "box": [113.0, 82.2, 114.4, 82.9], "kind": "track", "layer": "F.Cu", "touch": True}]
REMOVE += [{"net": "leg_ret", "box": [114.6, 82.0, 114.8, 82.2], "kind": "track", "layer": "B.Cu", "touch": True},
           {"net": "hot5", "box": [120.0, 86.0, 120.2, 86.2], "kind": "track", "layer": "In1.Cu", "touch": True}]
REMOVE_ESCAPES = [("J3", "1"), ("J3", "2")]   # the 3.96 mm J3 pin escapes; the 7.92 mm B2P3-VH needs none (M7)
HANDLED = ()

# R5 shunt current pads (task 04 round 5): native-21 fed R5.4 (HV_RET) through two 0.3 mm vias on
# a small F.Cu island and R5.1 (LEG_RET) through three at x 40.9. Up to 18 A in one via in the
# coherent return case, where native-17 had three 0.8 mm vias per side. Six filled 0.3 mm vias in
# each current pad take the layer transfer at the pad (a shunt's current pads carry their own vias).
IN_PAD = ("R5", "U26")   # stage 14: U27 / U28 / U35 removed
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
# reaches y 112.9. The last pad edges stay >= 8 mm from the SELV line_zc_raw run (B.Cu, y 121.1).
RES_A_STRIP = (150.0, 52.0, 166.0, 112.9)
SWB_STRIP = (188.0, 46.8, 200.6, 112.9)
SWB_BAND_TRIM = (150.0, 46.8, 188.0, 50.1)


STAGE21_DROP = {"J8 stud land", "J10 stud land"}   # with every rect_p / rect_n pour: the link studs are gone
STAGE21_FEED = ((74.0, 0.6), (136.0, 0.6), (136.0, 29.0), (74.0, 29.0))   # BR1 window, overlaps both trunks


def edit_zones(zones):
    from shapely.geometry import Polygon, box
    out = []
    # Stage 21 (DECISIONS 25): BR1 feeds the bus directly. The rect_p (In1) / rect_n (In2) pours and the four stud
    # lands go; the bus_p (In2) and hv_ret (In1) trunk pours, whose outlines already cover the BR1 zone, fill it.
    zones = [z for z in zones if z["net"] not in ("rect_p", "rect_n") and z.get("name") not in STAGE21_DROP]
    # The trunk outlines are notched where the rect pours were (x 76-135, y 0-27): the BR1 window is merged into
    # each trunk's own outline (one zone; KiCad refuses intersecting zones of equal priority), joining BR1.1
    # (In2 bus_p) and BR1.4 (In1 hv_ret) to the trunks.
    for i, z in enumerate(zones):
        if (z["net"], z["layer"], z.get("name")) in (("hv_ret", "In1.Cu", "hv_ret trunk"), ("bus_p", "In2.Cu", "bus_p trunk")):
            u = Polygon(z["outline"], z["holes"]).union(Polygon(STAGE21_FEED)).buffer(0)
            u = max(getattr(u, "geoms", [u]), key=lambda q: q.area)
            zones[i] = {**z, "outline": [[round(x, 3), round(y, 3)] for x, y in list(u.exterior.coords)[:-1]],
                        "holes": [[[round(x, 3), round(y, 3)] for x, y in list(h.coords)[:-1]] for h in u.interiors]}
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
        key = (z["net"], z["layer"])
        if any(k == key for k, _ in S15_ADD + S15_TRIM):
            poly = Polygon(z["outline"], z["holes"])
            for k, b in S15_TRIM:
                if k == key:
                    poly = poly.difference(box(*b))
            poly = max(getattr(poly, "geoms", [poly]), key=lambda q: q.area)
            for k, b in S15_ADD:
                if k == key and poly.intersects(box(*b)):
                    poly = poly.union(box(*b)).simplify(0)
            poly = max(getattr(poly, "geoms", [poly]), key=lambda q: q.area)
            z = {**z, "outline": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
                 "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in poly.interiors]}
        out.append(z)
    return out


# Stage 15 (28 A tank hardware, DECISIONS 2026-10-10): tank copper to >= 9.77 mm (IPC-2221, 70 um, 20 K,
# 28 A) where it can be had without moving parts. Outline edits only, clearance-checked against the
# stage-14 copper (scratchpad stage15/proposals.py -> committed with task 04's stage-15 evidence); KiCad's
# refill keeps the rules. P-A1: SW_A's leg to T1 widens right past J5's bite (6.99 -> 10.79 mm). P-B1:
# SW_B's band at the bank regains y 46.8-50 where the res_a 5 mm rule allows. P-B1b / P-B3: SW_B
# gains 0.4-3.8 mm off the l_filt mains pour's edge (l_filt trimmed to match). Proposal P-B2 (SW_B's drop at
# x 100.5-110, 9.49 mm) is not taken: its l_filt trim at x 112-114 cuts the pour in two. SW_B beside the FETs
# (x 31-76) can't widen without moving C38/C40 / R5: left to B3's 28 A case.
S15_ADD = [(("sw_a", "F.Cu"), (148.6, 55.0, 152.4, 101.5)),       # P-A1 (from y 55: the R22 -> C21 res_a tap runs at x 156.5 to y 50)
           (("sw_b", "B.Cu"), (150.0, 46.8, 188.0, 50.0)),        # P-B1
           (("sw_b", "B.Cu"), (150.0, 36.8, 188.0, 37.2)),        # P-B1b
           (("sw_b", "B.Cu"), (83.7, 15.6, 100.5, 19.4))]         # P-B3
S15_TRIM = [(("l_filt", "B.Cu"), (150.0, 33.4, 188.0, 34.2)),     # for P-B1b
            (("l_filt", "B.Cu"), (83.0, 12.4, 101.0, 17.0))]      # for P-B3
# Stage 15b (28 A thermal, DECISIONS item 14; validation-results/04-board-current-thermal/round5-native21/stage15b/):
# B3 put the 28 A FET-row peak in SW_A's A-low-side path: the B.Cu leg-A link (2.83 mm over the Q3.3 / Q2.2
# keep-outs) and the F.Cu neck right of Q2.3. Candidate c2h: raise the link's top 12.5 -> 13.5 over x 50.5-70
# and drop SW_B's lane bottom 15.7 -> 16.7 to keep the 3.2 mm gap (stops short of the C55 tie via at 73.1);
# fill the Q2.3 / BR1.1 corner on F.Cu (refill keeps 3.2 mm from BR1.1). No part moves, inner layers untouched.
S15_ADD += [(("sw_a", "F.Cu"), (76.5, 0.6, 81.7, 9.8)),
            (("sw_a", "B.Cu"), (50.5, 12.4, 70.0, 13.5))]
S15_TRIM += [(("sw_b", "B.Cu"), (50.5, 12.5, 70.0, 16.7))]
R5_PADS = {"leg_ret": "R5.1", "hv_ret": "R5.4"}
R5_MAX, R5_REACH = 10, 2.6
# Stage 17: R5.2 / R5.3 are custom pads (lobe + finger, footprint temper:R_Shunt_Bourns_CSS2H-2512_Kelvin);
# GEO only knows their bounding boxes, which overlap the current pads' first via rows. add_r5 checks those
# two nets against the true outlines (footprint-local polygons, R5 at (38.5, 12.6), -90 deg; asserted
# against the dumped pad boxes).
R5_AT = (38.5, 12.6)
R5_SENSE_LOCAL = {"ocp_kelvin_p": ("R5.2", [(-1.8, -0.2), (-0.3, -0.2), (-0.3, 3.2), (-0.7, 3.2), (-0.7, 0.2), (-1.8, 0.2)]),
                  "ocp_kelvin_n": ("R5.3", [(1.8, -0.2), (0.3, -0.2), (0.3, 3.2), (0.7, 3.2), (0.7, 0.2), (1.8, 0.2)])}


def r5_sense(G):
    """True board outlines of R5's sense pads {net: Polygon}; board = (x0 - ly, y0 + lx) for -90 deg."""
    from shapely.geometry import Polygon
    out = {}
    for net, (ref_pad, pts) in R5_SENSE_LOCAL.items():
        poly = Polygon([(R5_AT[0] - ly, R5_AT[1] + lx) for lx, ly in pts])
        box_ = G.pad(ref_pad)["box"]
        assert all(abs(a - b) < 1e-3 for a, b in zip(poly.bounds, box_)), (ref_pad, poly.bounds, box_)
        out[net] = poly
    return out


# Exposed-pad thermal vias (independent review 2026-10-08, B2): the TPS7A4700 LDOs (U26 LS ~0.95 W,
# U27 / U28 HS) and the SN6507 (U35) had none. Filled, capped 0.6 / 0.3 vias on a grid in each pad,
# into the part's own plane (n_ls / n_ha / n_hb); pitch 1.0 / 0.9 mm keeps merge_close_vias off them.
EP_VIAS = {"U26.21": (3, 1.0)}   # stage 14: the HS TPS7A47s (U27/U28) and the SN6507 (U35) are gone


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
    add_stage17(g)          # before add_r5: the Kelvin pair's In1 run under R5 is laid first
    add_r5(g)
    add_ep(g)
    add_stage19_pi(g)    # stage 19: before the stage-14 module re-links, which route round these pins
    add_stack(g)
    add_stage8(g)
    add_stage13(g)
    add_stage14(g)
    add_stage16(g)
    add_stage18(g)
    add_stage19(g)
    add_stage19_si(g)
    add_stage21b_kn(g)   # last: routes round every fixed patch
    resolve_zone_priorities(g["ZONES"])


# Stage 18 (DECISIONS items 7 and 18): RES_A is 297 V rms / 656 V pk to earth at 28 A, so it needs 12.6 mm
# reinforced creepage to SELV / PE on the outer layers (rules21.RES_A_CREEPAGE). On stage 17b two SELV runs on
# B.Cu passed under the bank's res_a strip (edge y 114.0 at x 150-161, y 112.9 at x 161-166): line_zc_raw at
# y 121.27-122.87 (8.145 mm) and v15_selv at y 123.6 (9.40 mm). Both keep their base geometry outside the bank
# and drop into lanes south of it: line_zc_raw at y 127.5 (edge 13.375 mm from the strip), v15_selv at y 128.6
# (14.4 mm), on 45-degree doglegs (3.5 mm apart) east at x 177-187 and west at x 136-141. B.Cu is otherwise empty
# there; no part, pour or other net moves. put() checks the 12.6 mm rule (geom21 -> rules21.clearance_on).
S18_LINE_ZC = [[209.07, 102.47], [209.07, 102.67], [208.87, 102.87], [208.87, 116.47], [205.27, 120.07],
               [204.87, 120.07], [204.27, 120.67], [203.87, 120.67], [203.27, 121.27], [184.0, 121.27],
               [177.77, 127.5], [141.23, 127.5], [136.6, 122.87], [124.27, 122.87], [118.07, 129.07], [89.87, 129.07]]
S18_V15 = [[210.8, 123.6], [186.6, 123.6], [181.6, 128.6], [137.1, 128.6], [128.5, 137.2], [127.1, 137.2],
           [125.7, 138.6], [124.3, 138.6], [123.7, 139.2], [76.7, 139.2]]


def add_stage18(g):
    from patches21_v1 import put
    put(g, "line_zc_raw", "B.Cu", 0.25, *S18_LINE_ZC)
    put(g, "v15_selv", "B.Cu", 0.4, *S18_V15)


# Stage 17b: deterministic pour fill. Two different-net pours on one layer, closer than their clearance and at the
# SAME priority, let KiCad's fill order decide who gets the contested copper; rebuilds of identical copper.json
# flipped it (In1 n_ls / ocp_kelvin_p at y 75.3: U26 133.0 vs 126.1 C at nominal h 25; B.Cu sw_b / res_a 48 mm2 at
# the bank, sw_a / sw_b, l_filt / sw_b, res_a / coil_feed between stages 14-17). Every such pair now has a declared
# winner; strict orders already in copper.json are kept, and gates/zone_priority_gate.py fails any unresolved pair.
# Winners: In1 n_ls (stage-17b review call); the rest keep stage 15b's fill (the board DECISIONS 14 accepted for 28 A).
ZONE_WINNERS = [("In1.Cu", "n_ls LS block", "ocp_kelvin_p protection"),
                ("B.Cu", "l_filt BR1.2-L1", "sw_b leg B-C21..C23"),
                ("B.Cu", "sw_a leg-A link", "sw_b leg B-C21..C23"),
                ("B.Cu", "sw_b leg B-C21..C23", "res_a J5-C21..C23"),
                ("B.Cu", "coil_feed J2-T1.2", "res_a J5-C21..C23"),
                ("B.Cu", "n_ls U42 heat-spread", "n_hb bank"),
                # outlines exactly 3.2 mm apart: only a ~5 um boundary sliver moves, but it moved between rebuilds
                ("F.Cu", "sw_a Q2.3-T1.1", "n_filt BR1.3-L1-C2"),
                ("B.Cu", "sw_b leg B-C21..C23", "n_ls LS-A bank"),
                ("F.Cu", "l_f F1-C1-L1-RV1", "ac_l_in J1-F1")]


def contested_pairs(zones):
    """(i, j, need) for different-net pours on one layer whose outlines are closer than their clearance."""
    from shapely.geometry import Polygon
    import rules21
    polys = [Polygon(z["outline"], z["holes"]) for z in zones]
    out = []
    for i, a in enumerate(zones):
        for j in range(i + 1, len(zones)):
            b = zones[j]
            if a["layer"] != b["layer"] or a["net"] == b["net"]:
                continue
            need = rules21.clearance(a["net"], b["net"])
            if polys[i].distance(polys[j]) < need + 1e-3:   # outlines exactly at the clearance still trade a ~5 um sliver
                out.append((i, j, need))
    return out


def resolve_zone_priorities(zones):
    win = {(lay, w, l_) for lay, w, l_ in ZONE_WINNERS}
    cons, bad = [], []
    for i, j, _ in contested_pairs(zones):
        a, b = zones[i], zones[j]
        pa, pb = a.get("priority", 1), b.get("priority", 1)
        if pa != pb:
            cons.append((i, j) if pa > pb else (j, i))
        elif (a["layer"], a.get("name"), b.get("name")) in win:
            cons.append((i, j))
        elif (a["layer"], b.get("name"), a.get("name")) in win:
            cons.append((j, i))
        else:
            bad.append((a["layer"], a.get("name"), b.get("name")))
    if bad:
        raise SystemExit(f"equal-priority pours closer than clearance, no declared winner: {bad}")
    for _ in range(len(zones) + 1):
        changed = False
        for hi, lo in cons:
            if zones[hi].get("priority", 1) <= zones[lo].get("priority", 1):
                zones[hi]["priority"] = zones[lo].get("priority", 1) + 1
                changed = True
        if not changed:
            return
    raise SystemExit("pour priority constraints are cyclic")


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


def add_stage16(g):
    """Stage 16 (DECISIONS 16): the blower-supply mains tap. L_FILT from PS1.1 into F2, F2 out (BLW_L) to
    J11.1, N_FILT from PS1.2 to J11.2; 1.0 mm, since F2 (3.15 A T) rather than F1 protects this branch.
    The three groups (L_F, BLW_L, MAINS_N) keep 3.2 mm from each other; the router chooses layers."""
    from patches21_v1 import route_group
    box = (248.0, 108.0, 282.0, 140.0)
    route_group(g, [("l_filt", CU, box, 1.0, ["PS1.1", "F2.1"]),
                    ("blw_l", CU, box, 1.0, ["F2.2", "J11.1"]),
                    ("n_filt", CU, box, 1.0, ["PS1.2", "J11.2"])])



def add_stage19(g):
    """Stage 19 (DECISIONS 19): copper the router could not lay for the moved bypass caps.
    C87 (U31's cmonitor, vertical beside the board edge): p_hb pad down a via to the In2 p_hb run at x 2.4.
    C49 (U15's bypass, left of it): pads linked to U15.5 / U15.3 by the router (it could not
    do so in the open-pair passes). bias_hb_bad (U25.6 to U34.13) lost its y 127.56 lane to the cap row."""
    from patches21_v1 import put, route_group
    drill(g, "p_hb", 2.4, 68.8, size=0.6)
    put(g, "p_hb", "F.Cu", 0.25, "C87.1", [2.4, 68.8])
    put(g, "p_hb", "In2.Cu", 0.25, [2.4, 68.8], [2.4, 71.925])
    # C44 (U10's bypass): its selv_gnd pad to the U10.2 return via at x 25.22 (the open-pair passes left it open)
    put(g, "selv_gnd", "F.Cu", 0.25, "C44.2", [23.843, 128.1], [25.243, 128.1], [25.643, 128.5], [25.643, 129.745])
    box49 = (97.0, 49.0, 108.0, 58.0)
    route_group(g, [("hot5", CU, box49, 0.3, ["C49.1", "U15.5"]),
                    ("ocp_kelvin_p", CU, box49, 0.25, ["C49.2", "U15.3"]),
                    ("bias_hb_bad", CU, (1.0, 104.0, 36.0, 133.0), 0.3, ["U25.6", "U34.13"])])

def add_stage19_pi(g):
    """Stage 19 PI1 / PI2 (DECISIONS 19; place.py STAGE19_PI): the converter-local capacitor links, laid by hand so
    each is a short F.Cu run from the pin to the cap pad (no via in the VOUT+ / OUT / IN / NR paths).
    U41 / U42 (RECOM R24C2T25/R p.13): VOUT+ pins 28 / 29 straight down into the 1210's p pad and on to the 0603's;
    the 0603's VOUT- pad back up to pin 31 (U41) / pin 35 (U42); the 1210's VOUT- pad to the In1 n_h* plane by a
    via beside it (the F.Cu n_h* pour around the secondary pins joins it too). FBVOUT+ / FBVOUT- (33 / 34) are tied
    between their pads; U41's leaves by a stub east of the 0603, U42's by a via (U31 holds its 1210 further east).
    U26 (TI SBVS204 9.1): OUT 1 / 20 / SENSE 3 meet at C99's v15_ls pad; IN 15 / 16 straight into C98 (north-east
    corner); NR 14 straight to C64 (east); EN 13 by a via; an F.Cu n_ls pour joins GND 4-10, the pad and the cap
    returns."""
    from patches21_v1 import put, route_group
    F1 = ("F.Cu",)
    L4 = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    # --- U41 (leg A high side)
    put(g, "p_ha", "F.Cu", 0.3, "U41.29", [57.475, 73.82], "C75.1")
    put(g, "p_ha", "F.Cu", 0.3, "U41.28", [56.825, 72.6], [57.475, 72.6])
    put(g, "p_ha", "F.Cu", 0.3, [57.475, 73.915], "C104.1")
    put(g, "p_ha", "F.Cu", 0.3, "C75.1", "R92.1")
    put(g, "n_ha", "F.Cu", 0.3, "C75.2", [59.925, 72.75], [58.775, 72.75], "U41.31")
    put(g, "bias_ha-fbm", "F.Cu", 0.25, "U41.33", "U41.34")
    put(g, "bias_ha-fbm", "F.Cu", 0.2, "U41.34", [60.725, 73.795], "C71.1")
    put(g, "bias_ha-fbm", "F.Cu", 0.2, [60.725, 73.795], [60.725, 75.42], "R92.2")
    drill(g, "n_ha", 55.93, 78.3, size=0.6)
    put(g, "n_ha", "F.Cu", 0.5, "C104.2", [55.93, 78.3])
    # --- U42 (leg B high side)
    put(g, "p_hb", "F.Cu", 0.3, "U42.29", [11.175, 68.82], "C82.1")
    put(g, "p_hb", "F.Cu", 0.3, "U42.28", [10.525, 68.915], "C108.1")
    put(g, "n_hb", "F.Cu", 0.3, "C82.2", [15.075, 68.82], "U42.35")
    put(g, "bias_hb-fbm", "F.Cu", 0.25, "U42.33", "U42.34")
    drill(g, "bias_hb-fbm", 14.1, 67.72, size=0.6)
    put(g, "bias_hb-fbm", "F.Cu", 0.25, "U42.33", [13.775, 67.72], [14.1, 67.72])
    drill(g, "n_hb", 11.0, 73.5, size=0.6)
    put(g, "n_hb", "F.Cu", 0.5, "C108.2", [11.0, 73.5])
    # --- U26 (low-side bias LDO; pins: OUT 1 / 20, SENSE 3, GND 4-10, EN 13, NR 14, IN 15 / 16)
    put(g, "v15_ls", "F.Cu", 0.4, "U26.1", [112.1, 79.7], "C99.1")
    put(g, "v15_ls", "F.Cu", 0.3, "U26.20", [114.1125, 77.85], [112.1, 77.85], [112.1, 79.7])
    put(g, "v15_ls", "F.Cu", 0.3, "U26.3", [112.1, 81.05], [112.1, 79.7])
    put(g, "n_ls", "F.Cu", 0.5, "C99.2", "U26.5")
    put(g, "ldo_nr", "F.Cu", 0.25, "U26.14", "C64.1")
    # IN 16 straight up into C98's v24_raw pad, IN 15 up its east side; the PS2 v24_raw In1 feed ends at
    # (117.6, 77.0) under that pad: an In1 stub to a via between C98's pads joins it.
    put(g, "v24_raw", "F.Cu", 0.3, "U26.16", "C98.1")
    put(g, "v24_raw", "In1.Cu", 0.4, [117.6, 77.0], [118.6, 77.0], escape="n_ls")   # the In1 n_ls pour refills round it
    drill(g, "v24_raw", 118.6, 77.0, size=0.6)
    put(g, "v24_raw", "F.Cu", 0.3, "U26.15", [118.45, 79.75], [118.45, 77.6], [118.6, 77.0], "C98.1")
    # EN 13 (tied to IN; no current) leaves under C64 and reaches the same via on B.Cu
    drill(g, "v24_raw", 118.9, 81.85, size=0.6)
    put(g, "v24_raw", "F.Cu", 0.2, "U26.13", [118.6, 81.05], [118.9, 81.85])
    put(g, "v24_raw", "B.Cu", 0.25, [118.9, 81.85], [118.6, 77.0])
    # C98 / C64 returns: C98's down C64's east side, both into the local F.Cu pour and by a via to In1 n_ls
    put(g, "n_ls", "F.Cu", 0.4, "C98.2", [121.3, 77.1], [121.3, 79.9], "C64.2")
    drill(g, "n_ls", 121.6, 81.5, size=0.6)
    put(g, "n_ls", "F.Cu", 0.4, "C64.2", [121.6, 81.5], [121.6, 82.5])
    g["zone"]("n_ls", "F.Cu", (108.7, 82.0, 122.0, 85.2), name="n_ls U26 local return (stage 19)")
    # leg_ret (B.Cu) and hot5 (In1) re-laid west / south of U26's thermal-pad field
    put(g, "leg_ret", "B.Cu", 0.2, [113.6, 55.4], [113.6, 65.2], [114.1, 65.7], [114.1, 70.4], [114.7, 71.0], [114.7, 76.4],
        [112.85, 78.25], [112.85, 85.15], [113.0, 85.3])
    if not g["link"]("hot5", ("In1.Cu", "In2.Cu", "B.Cu"), (100.0, 72.0, 124.0, 117.0), 0.4,
                     ["@110.0,73.695,In1.Cu", "@107.105,115.675,In1.Cu"]):
        raise SystemExit("stage 19: hot5 rail round U26")
    # The rails that served U26's old pins lose their base copper with them (incr21 prunes what hangs off it): the PS2
    # v24_raw In1 feed is re-laid on its base polyline (else the router takes it diagonally across the In1 hv_ret
    # trunk and splits it); the LS rail (v15_ls) and leg_ret runs round U26 are re-joined at the end of add_stage19_si.
    put(g, "v24_raw", "In1.Cu", 0.4, "PS2.4", [212.2, 17.6], [212.2, 76.0], [150.0, 76.0], [144.3, 60.55], [121.8, 60.55],
        [121.8, 77.0], [117.6, 77.0], escape=("hv_ret", "bus_p", "n_ls", "ocp_kelvin_p"))
    # (the stage-14 re-links that follow join R93.1 to this fbm, and U30.3 / U1.16 / R94.1 to these p_h* pads)
    route_group(g, [("bias_hb-fbm", L4, (8.0, 64.0, 19.0, 75.0), 0.25, ["@14.1,67.72,*", "C72.1", "R94.2", "R61.1"])])


def rip(g, net, pick=lambda item: True):
    """Take a net's tracks / vias (those `pick` selects) back out of the route state and the clearance index."""
    from shapely.geometry import LineString as _LS, Point as _Pt
    G = g["GEO"]

    def drop(layers, geom):
        for lay in tuple(layers) + ("PLAN",):
            items = G.items[lay]
            for k in range(len(items) - 1, -1, -1):
                gg, nn = items[k]
                if nn == net and abs(gg.area - geom.area) < 1e-6 and gg.centroid.distance(geom.centroid) < 1e-6:
                    del items[k]
                    break
    n = 0
    for t in [t for t in g["TRACKS"] if t["net"] == net and pick(t)]:
        g["TRACKS"].remove(t)
        drop((t["layer"],), _LS([g["_xy"](q) for q in t["points"]]).buffer(t["width"] / 2, cap_style=1))
        n += 1
    for v in [v for v in g["VIAS"] if v["net"] == net and pick(v)]:
        g["VIAS"].remove(v)
        drop(CU, _Pt(*v["at"]).buffer(v["size"] / 2))
        n += 1
    G._trees.clear()
    return n


def plane_via(g, ref_pad, reach=(0.85, 1.6)):
    """A 0.6 mm via on the pad's net next to an SMD pad, the nearest legal spot within `reach` of its centre,
    with a 0.3 mm stub to it (the pad's net is poured on an inner layer there)."""
    import math
    from shapely.geometry import Point
    from patches21_v1 import put
    G = g["GEO"]
    pd = G.pad(ref_pad)
    net, x0, y0 = pd["net"], pd["x"], pd["y"]
    steps = int(round((reach[1] - reach[0]) / 0.05))
    for k in range(steps + 1):
        r = reach[0] + 0.05 * k
        for i in range(24):
            a = 2 * math.pi * i / 24
            x, y = round(x0 + r * math.cos(a), 3), round(y0 + r * math.sin(a), 3)
            if G.conflicts(net, CU, Point(x, y).buffer(0.3), limit=1, via=True):
                continue
            try:
                put(g, net, "F.Cu", 0.3, ref_pad, [x, y])
            except SystemExit:
                continue
            drill(g, net, x, y, size=0.6)
            return x, y
    raise SystemExit(f"stage 19b: no plane via spot beside {ref_pad}")


def add_stage19_si(g):
    """Stage 19 SI1 / SI2 (DECISIONS 19; stage-18 return-path review). `layout/gates/return_path19.py` checks them.
    SI1 bus_fault_hot (U8.4 -> U9.4; both grounds are ocp_kelvin_p): over the In1 Kelvin pour to its west end, then
    beside / under the Kelvin return that already joins U9's ground to that pour (the B.Cu run at x 100-103), so the
    signal never crosses the In1 ocp_kelvin_p / n_ls boundary without its own return beside it. The Kelvin run's
    lower 26 mm moves from B.Cu to In2 directly above the signal (same polyline, one via at the corner); no new
    Kelvin path is added, so no Kelvin loop forms (the R5 sense fingers and pours are untouched).
    SI2 ct_zc: B.Cu from U12.1's via-in-pad (C46 1.8 mm) straight to the J4.13 pin (THT), dropping the F.Cu hop.
    SI2 pwm_hb / pwm_lb: C14 (U2's VCCI cap) moved under U2 broke pwm_lb's F.Cu lane; pwm_lb is re-laid on F.Cu
    (no via). pwm_hb: F.Cu -> B.Cu beside C14 (2.4 mm), B.Cu down the spur, F.Cu hop over the permit / bias_bad
    B.Cu crossing between vias beside C142 (2.0 mm) and C47 (2.4 mm); from there to J4.7 the stage-18 route (four
    more changes, no transfer capacitor within 3 mm: open, DECISIONS 19)."""
    from patches21_v1 import put
    link = g["link"]
    # --- SI2 ct_zc
    rip(g, "ct_zc", lambda it: "layer" in it or abs(it["at"][1] - 164.595) < 0.5)
    if not link("ct_zc", ("B.Cu",), (20.0, 125.0, 62.0, 189.0), 0.25, ["@26.907,128.795,B.Cu", "J4.13"]):
        raise SystemExit("stage 19: ct_zc B.Cu run to J4.13")
    # --- SI2 pwm_lb / pwm_hb
    rip(g, "pwm_hb")
    rip(g, "pwm_lb")
    if not link("pwm_lb", ("F.Cu",), (20.0, 54.0, 70.0, 189.0), 0.3, ["U2.2", "J4.8"]):
        raise SystemExit("stage 19: pwm_lb F.Cu lane")
    put(g, "pwm_hb", "F.Cu", 0.3, "U2.1", [28.955, 55.875])
    drill(g, "pwm_hb", 28.955, 55.875, size=0.6)
    drill(g, "pwm_hb", 34.4, 110.6, size=0.6)
    drill(g, "pwm_hb", 35.2, 125.0, size=0.6)
    for ok, what in ((link("pwm_hb", ("B.Cu",), (20.0, 54.0, 62.0, 189.0), 0.3, ["@28.955,55.875,B.Cu", "@34.4,110.6,B.Cu"]), "B.Cu spur"),
                     (link("pwm_hb", ("F.Cu",), (20.0, 100.0, 62.0, 130.0), 0.3, ["@34.4,110.6,F.Cu", "@35.2,125.0,F.Cu"]), "F.Cu hop"),
                     ):
        if not ok:
            raise SystemExit(f"stage 19: pwm_hb {what}")
    # J4 side: stage 18's geometry (no v3v3-selv_gnd capacitor lies within 3 mm of these four changes; DECISIONS 19 open)
    put(g, "pwm_hb", "B.Cu", 0.3, [35.2, 125.0], [36.9, 125.0], [38.955, 127.055], [38.955, 127.075])
    drill(g, "pwm_hb", 38.955, 127.075, size=0.6)
    put(g, "pwm_hb", "F.Cu", 0.3, [38.955, 127.075], [42.955, 127.075], [43.155, 127.275], [54.155, 127.275],
        [55.155, 128.275], [55.155, 128.675])
    drill(g, "pwm_hb", 55.155, 128.675, size=0.6)
    put(g, "pwm_hb", "B.Cu", 0.3, [55.155, 128.675], [56.155, 129.675], [56.155, 157.275])
    drill(g, "pwm_hb", 56.155, 157.275, size=0.6)
    put(g, "pwm_hb", "F.Cu", 0.3, [56.155, 157.275], [55.955, 157.475], [55.955, 175.0])
    drill(g, "pwm_hb", 55.955, 175.0, size=0.6)
    if not link("pwm_hb", ("B.Cu",), (48.0, 170.0, 60.0, 182.0), 0.3, ["@55.955,175.0,B.Cu", "J4.7"]):
        raise SystemExit("stage 19: pwm_hb B.Cu into J4.7")
    # --- SI1 bus_fault_hot and the Kelvin return under it
    rip(g, "bus_fault_hot")
    n = rip(g, "ocp_kelvin_p", lambda it: it.get("layer") == "B.Cu" and any(
        not isinstance(q, str) and abs(q[0] - 100.35) < 0.01 and abs(q[1] - 88.695) < 0.01 for q in it["points"]))
    if n != 1:
        raise SystemExit(f"stage 19: Kelvin B.Cu return not found ({n})")
    put(g, "ocp_kelvin_p", "B.Cu", 0.25, [103.75, 74.095], [102.95, 74.895], [102.95, 83.695], [99.55, 87.095],
        [99.55, 87.895], [100.35, 88.695])
    drill(g, "ocp_kelvin_p", 100.35, 88.695, size=0.6)
    put(g, "ocp_kelvin_p", "In2.Cu", 0.25, [100.35, 88.695], [100.35, 109.095], [101.55, 110.295], [101.55, 112.895],
        [101.75, 113.095], [101.75, 114.095])
    # The In1 Kelvin pour's outline reaches x 100.5 here, but the v24_raw In1 feed at x 101.9 cuts its west strip off
    # and KiCad drops it as an island. A Kelvin via in the strip, tied by B.Cu to the Kelvin via (103.75, 74.095),
    # keeps the strip, so the signal changes layer over Kelvin copper. A dead end: it carries no Kelvin current.
    drill(g, "ocp_kelvin_p", 100.6, 73.6, size=0.6)
    put(g, "ocp_kelvin_p", "B.Cu", 0.25, [100.6, 73.6], [103.25, 73.6], [103.75, 74.095])
    drill(g, "bus_fault_hot", 101.1, 74.9, size=0.6)
    put(g, "bus_fault_hot", "B.Cu", 0.25, [101.1, 74.9], [102.45, 74.9], [102.45, 83.488], [99.05, 86.888],
        [99.05, 89.2], [100.35, 90.5], [100.35, 109.095], [101.55, 110.295], [101.55, 112.6], [100.6, 113.55], [100.6, 114.0])
    drill(g, "bus_fault_hot", 100.6, 114.0, size=0.6)
    drill(g, "bus_fault_hot", 113.635, 114.5, size=0.6)
    put(g, "bus_fault_hot", "F.Cu", 0.25, "U9.4", [113.635, 114.5])
    for ok, what in ((link("bus_fault_hot", ("F.Cu", "In2.Cu", "B.Cu"), (100.6, 51.0, 120.6, 74.95), 0.25, ["U8.4", "@101.1,74.9,In2.Cu"]), "over the Kelvin pour"),
                     ):
        if not ok:
            raise SystemExit(f"stage 19: bus_fault_hot {what}")
    # last 13 mm to U9 on In2, within 0.5 mm in plan of the Kelvin chain to U9's grounds (In1 / F.Cu tracks)
    put(g, "bus_fault_hot", "In2.Cu", 0.25, [100.6, 114.0], [100.6, 114.9], [101.2, 115.5], [101.7, 115.0], [105.6, 115.0],
        [106.3, 114.2], [109.6, 114.2], [110.05, 114.65], [113.485, 114.65], [113.635, 114.5])
    # Stage 19b: each pwm_hb transfer cap (C153-C156) reaches its two planes (In1 v3v3, In2 selv_gnd) through its
    # own via beside each pad, so the cap closes the return loop locally instead of through long pad tracks.
    for ref in ("C153", "C154", "C155", "C156"):
        for pad in ("1", "2"):
            plane_via(g, f"{ref}.{pad}", reach=(0.85, 2.2))
    # PI2 follow-up (after the SI1 lanes are laid): the LS rail and leg_ret round the moved U26
    L4 = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    from patches21_v1 import route_group
    route_group(g, [("v15_ls", L4, (98.0, 50.0, 124.0, 114.0), 0.4,
                     ["C99.1", "U29.3", "C70.1", "U37.1", "C65.1", "R59.1", "C100.1", "C131.1", "R85.1", "R87.1", "C25.1", "U3.1"]),
                    ("leg_ret", L4, (98.0, 70.0, 124.0, 114.0), 0.25, ["@113.0,85.3,B.Cu", "U16.2", "R77.1", "R83.1", "R81.1"])])
    # v24_raw: the module trunk (In1, x 101.9, ending at the via (101.9, 87.5)) met the PS2 feed at U26's old IN pins;
    # B.Cu now joins it to U26's EN / IN via, below the In1 n_ls pour (an In1 run here would cut that pour).
    if not g["link"]("v24_raw", ("F.Cu", "B.Cu"), (99.0, 74.0, 123.0, 92.0), 0.4, ["@101.9,87.5,B.Cu", "@118.9,81.85,B.Cu"]):
        raise SystemExit("stage 19: v24_raw trunk to U26")



def add_stage13(g):
    """Stage 13: the resonant-bank bleed tap R22.1 -> RES_A. The base polyline served C21's old axial pad
    and is dropped with it. Re-laid on F.Cu down the base's own x 156.54 lane to the new C21 pin 1. The
    pad escape next to R22.2 (crbleed_1) is the base geometry, bounded by the DRU pad-escape rule, so
    put()'s check waives that partner and the final DRC decides. The B.Cu sw_b band is another layer."""
    from patches21_v1 import put
    put(g, "res_a", "F.Cu", 0.4, "R22.1", [156.54, 50.0], "C21.1", escape="crbleed_1")


# Stage 14: the module primary feeds and the bus-clamp midpoint. Every run ends on a pad (through a
# via and a short F.Cu stub) so nothing dangles: the incremental pass treated the renamed base trunks
# as stale and prunes dangling copper.
# - V24_RAW: from the LS-block via at (101.9, 87.5) on In1 (route21's T_LINES band, y 45.5) to a drop
#   beside C102 (U41's input cap) and, past the west end of the In1 n_ls run (x 10.6), to C106 (U42).
# - Enable: each module has its own divider beside its CTRL pin (no shared run).
# - BUSBLEED_MID: R3 - the D3 / D17 midpoint - R4 along y 100.8 (ALT-D3 4.2), with the 1.0 mm
#   midpoint link between the two TVS.
FEEDS = [("v24_raw", [(101.9, 87.5), (101.9, 45.5), (54.6, 45.5), (52.6, 47.5), (52.6, 58.1)], "C102.1"),
         ("v24_raw", [(54.6, 45.5), (8.0, 45.5), (7.0, 46.5), (7.0, 53.1)], "C106.1"),
]


def add_stage14(g):
    from patches21_v1 import put
    for net, pts, pad in FEEDS:
        # In1 crosses the ocp_kelvin_p protection pour and the hv_ret trunk pour (pours only, checked: no
        # tracks), as route21's T_LINES did; KiCad refills both round it
        put(g, net, "In1.Cu", 0.4, *[list(q) for q in pts], escape=("ocp_kelvin_p", "hv_ret"))
        drill(g, net, *pts[-1])
        put(g, net, "F.Cu", 0.25, list(pts[-1]), pad)
    put(g, "busbleed_mid", "F.Cu", 1.0, "D3.2", "D17.1")
    # the base bleed route's own geometry: R3 / R4 each span bus_p or hv_ret and the midpoint, so their
    # pads are bounded pad escapes (DRU); the final DRC judges the clearance
    # into R4 pad 1 from above and out of pad 2 from below, ending at the pads' outer edges (not their
    # centres) so the two runs stay >= 3.2 mm apart across R4
    put(g, "busbleed_mid", "F.Cu", 0.4, "R3.2", [248.04, 100.8], [288.0, 100.8], [288.0, 101.4], escape=("bus_p", "hv_ret"))
    put(g, "busbleed_mid", "F.Cu", 0.4, [268.57, 106.0], [268.57, 100.8])
    put(g, "hv_ret", "F.Cu", 0.6, [288.0, 105.6], [287.4, 106.2], "D17.2", escape="busbleed_mid")
    # Module heat (about 1.1 W each, ALT-BIAS 3.2) leaves through its pins: RECOM R24C2T25/R p.12 asks
    # for copper pours with vias on PGND and VOUT-. Each module gets an N_LS pour under its primary half
    # and an N_Hx pour under its secondary half, on F.Cu and B.Cu, stitched with vias; the two halves
    # stay >= 3.2 mm apart (HOT groups), the pours refill round everything else.
    from shapely.geometry import Point as _Pt
    for (mx, my), nsec, tag in (((56.5, 66.2), "n_ha", "U41"), ((10.2, 61.2), "n_hb", "U42")):
        # primary pour over the PGND pins 8-18 only (x <= mx + 0.9), clear of PVIN / AVIN / CTRL (pins 4-7).
        # Both modules get both pours on F.Cu and B.Cu: with U42's primary on F.Cu only, B3 put U42
        # 40 K above U41 (175.6 vs 135.5 C, nominal h10); P_HB now runs on In2, and SW_B re-routes round it.
        pri = (mx - 7.8, my - 10.2, mx + 0.9, my - 1.9)
        sec = (mx - 7.8, my + 1.9, mx + 7.0, my + 9.8)
        for net, rect in (("n_ls", pri), (nsec, sec)):
            for lay in ("F.Cu", "B.Cu"):
                g["zone"](net, lay, rect, name=f"{net} {tag} heat-spread")
            x0, y0, x1, y1 = rect
            y = y0 + 1.0
            while y < y1 - 0.8:
                x = x0 + 1.0
                while x < x1 - 0.8:
                    if not g["GEO"].conflicts(net, CU, _Pt(x, y).buffer(0.3), limit=1, via=True):
                        g["via"](net, round(x, 3), round(y, 3), size=0.6)
                    x += 1.6
                y += 1.6
        if tag == "U42":
            # U42's N_LS island sits at the board edge, and SW_B's B.Cu link cuts its B.Cu pour: B3 still
            # had it at 175 C (nominal h10) against U41's 136. In1 / In2 are empty there, so its primary
            # also spreads on both inner layers (priority 2 over the hv_ret / bus_p trunks' edge; the
            # primary stitching vias above join all four layers).
            for lay in ("In1.Cu", "In2.Cu"):
                g["zone"]("n_ls", lay, (1.0, 48.0, 13.6, 56.6), priority=2, name=f"n_ls {tag} heat-spread inner")
    put(g, "p_hb", "F.Cu", 0.25, "U42.28", "U42.29")      # the module's two VOUT+ pins
    put(g, "p_ha", "F.Cu", 0.25, "U41.28", "U41.29")
    # Driver-side links the router can't find (spots probed against the stage-14 copper): the U2 / U1
    # driver banks meet the modules only through narrow corridors, 8 mm from the SELV driver inputs and
    # 3.2 mm from the LS / v24 copper. P_HB leaves U2's supply caps north of the In1 LOW runs and takes
    # In2 down x = 19 to R94; the N_HB bank tail joins U42's B.Cu pour; the N_HA bank tail drops on In1
    # into the U41 In1 pour.
    drill(g, "p_hb", 27.6, 37.6)
    put(g, "p_hb", "F.Cu", 0.3, [27.6, 37.6], [28.88, 38.88], "C18.1")
    # In2 crosses the bus_p trunk pour's edge (a pour: KiCad refills round it)
    put(g, "p_hb", "In2.Cu", 0.3, [27.6, 37.6], [25.9, 37.6], [19.3, 44.2], [19.3, 72.6], [12.2, 72.6], escape="bus_p")
    drill(g, "p_hb", 12.2, 72.6)
    put(g, "p_hb", "F.Cu", 0.3, [12.2, 72.6], "R94.1")   # stage 19: R94 moved beside C108 (place.py STAGE19_PI)
    put(g, "n_hb", "B.Cu", 0.5, [18.6, 61.6], [16.6, 64.0])
    put(g, "n_ha", "B.Cu", 0.6, [64.8, 47.5], [64.8, 50.0])
    drill(g, "n_ha", 64.8, 50.0)
    put(g, "n_ha", "In1.Cu", 0.25, [64.8, 50.0], [63.6, 52.0], [61.8, 53.8], [61.8, 61.0], [60.4, 62.4], [60.4, 67.0],
        escape="hv_ret")   # the hv_ret trunk pour's edge (a pour: KiCad refills round it)
    # Local re-links round the modules (the base copper that served U27 / U28 / T2 / T3 is gone):
    # each module's enable divider, the U41 input caps on the far side of its PGND pins, P_HA from the
    # module and the island to the driver bank (U1.16), P_HB to U31's supply, and SW_B to U20 (the
    # leg-B split shunt's cathode).
    from patches21_v1 import route_group
    route_group(g, [("bias_ha-en", CU, (57.0, 57.0, 68.0, 67.0), 0.25, ["U41.4", "R62.2", "R127.1"]),
                    ("bias_hb-en", CU, (11.0, 53.0, 22.0, 62.0), 0.25, ["U42.4", "R128.2", "R129.1"]),
                    ("v24_raw", CU, (52.0, 56.0, 67.0, 60.4), 0.3, ["C74.1", "C105.1", "C103.1"]),
                    ("p_ha", CU, (44.0, 34.0, 79.0, 92.0), 0.3, ["U41.28", "R92.1", "U30.3", "C104.1", "U1.16"]),
                    ("p_hb", CU, (0.6, 60.0, 20.0, 84.0), 0.3, ["U42.29", "R94.1", "U31.3"]),
                    ("n_ls", CU, (55.0, 56.0, 67.0, 66.0), 0.3, ["U41.1", "U41.5", "U41.8", "R127.2"]),
                    ("n_ls", CU, (8.0, 44.0, 22.0, 58.0), 0.3, ["C107.2", "U42.1"]),
                    ("n_ls", CU, (8.0, 40.0, 42.0, 54.0), 0.3, ["C107.2", "U2.9"]),
                    ("v24_raw", CU, (8.0, 50.0, 20.0, 58.5), 0.3, ["U42.7", "C81.1", "C106.1", "C109.1", "C107.1", "R128.1"]),
                    ("v24_raw", CU, (60.0, 56.0, 68.0, 63.0), 0.3, ["R62.1", "C103.1"]),
                    ("v24_raw", CU, (52.0, 56.5, 60.0, 60.0), 0.3, ["C102.1", "C74.1"]),
                    ("v24_raw", CU, (55.0, 56.5, 61.0, 62.2), 0.25, ["U41.7", "U41.6", "C74.1"]),
                    ("n_ha", CU, (44.0, 64.0, 66.0, 86.0), 0.3, ["U41.19", "U30.12"]),
                    ("bias_ha-fbm", CU, (55.0, 68.0, 64.0, 78.0), 0.2, ["U41.34", "U41.33", "R92.2", "R93.1", "C71.1"]),
                    ("sw_b", CU, (0.6, 40.0, 30.0, 95.0), 0.3, ["U20.2", "C95.1"])])


# Stage 17 (DECISIONS 17): R5 is a Bourns CSS2H-2512R-1L00F on Bourns' Kelvin land (footprint
# temper:R_Shunt_Bourns_CSS2H-2512_Kelvin). Both sense fingers leave the part on the WEST side, 1.0 mm
# apart (R5.2 / OCP_KELVIN_P at y 12.1, R5.3 / OCP_KELVIN_N at y 13.1, finger tips at x 35.3), so the
# pair now leaves R5 as a tight pair instead of from opposite ends. The pads changed, so incr21 treats
# R5 as moved: the stage-16 F.Cu stubs R5.2 -> (36.0, 8.0) / R5.3 -> (41.3, 15.2) are stale, and
# prune_dangling then drops the whole base Kelvin run down to the sense cluster (vias (36.0, 8.0),
# (41.3, 15.2), KP/KN_MID, KP/KN_VIA, (119.95, 72.4), the In1 / In2 legs and the U14-side In1 tail);
# the base HV_RET via at (35.8, 13.9) meets the new R5.3 lobe and goes too. Everything from the new
# finger vias onward is re-laid here: the two In1 legs under R5 to the stage-16 KP_MID / KN_MID, then
# the stage-16 geometry unchanged (patches21_v1 KP_* / KN_* and the base tails, byte for byte).
K17_P, K17_N = (35.0, 12.1), (35.0, 13.1)      # finger-tip vias (0.6 / 0.3), 0.4 mm apart edge to edge
K17_P_IN1 = [list(K17_P), [42.2, 12.1], [42.2, 30.8]]          # to KP_MID
K17_N_IN1 = [list(K17_N), [41.3, 13.1], [41.3, 31.8]]          # to KN_MID


def add_stage17(g):
    from patches21_v1 import KN_MID, KN_VIA, KP_MID, KP_VIA, put
    put(g, "ocp_kelvin_p", "F.Cu", 0.3, "R5.2", list(K17_P))
    drill(g, "ocp_kelvin_p", *K17_P)
    put(g, "ocp_kelvin_n", "F.Cu", 0.3, "R5.3", list(K17_N))
    drill(g, "ocp_kelvin_n", *K17_N)
    # In1 under R5: P crosses the LEG_RET sources pour, N the HV_RET trunk (pours: KiCad refills round them)
    put(g, "ocp_kelvin_p", "In1.Cu", 0.3, *K17_P_IN1, escape=("hv_ret", "leg_ret"))
    put(g, "ocp_kelvin_n", "In1.Cu", 0.3, *K17_N_IN1, escape=("hv_ret", "leg_ret"))
    # stage-16 geometry from here on
    drill(g, "ocp_kelvin_p", *KP_MID)
    put(g, "ocp_kelvin_p", "In2.Cu", 0.3, list(KP_MID), [42.2, 36.4], list(KP_VIA), escape="bus_p")
    drill(g, "ocp_kelvin_p", *KP_VIA)
    put(g, "ocp_kelvin_p", "In1.Cu", 0.3, list(KP_VIA), [42.2, 40.0], [42.2, 42.6], [107.6, 42.6], [107.6, 53.5],
        escape="hv_ret")
    put(g, "ocp_kelvin_p", "In1.Cu", 0.2, [108.248, 57.5], [108.248, 56.3], [107.547, 55.6], [107.547, 55.1],
        [108.148, 54.5], [108.148, 43.1], [107.748, 42.7], [107.6, 42.6], escape="hv_ret")
    drill(g, "ocp_kelvin_n", *KN_MID)
    put(g, "ocp_kelvin_n", "In2.Cu", 0.3, list(KN_MID), [41.3, 35.5], [39.4, 37.4], list(KN_VIA), escape="bus_p")
    drill(g, "ocp_kelvin_n", *KN_VIA)
    put(g, "ocp_kelvin_n", "In1.Cu", 0.3, list(KN_VIA), [41.3, 40.6], [41.3, 43.4], escape="hv_ret")
    # Stage 21b (DECISIONS 26; rubric F8): the pair runs together on In1 to the pour-entry height (106.6, 53.5); from
    # there KELVIN_N drops to In2 and runs under the In1 ocp_kelvin_p protection pour to R33's via, so the sense loop
    # closes under its own return instead of crossing the pour on In1 (stage 16-21: In1 x 106.6 down to y 72.4).
    put(g, "ocp_kelvin_n", "In1.Cu", 0.3, [41.3, 43.4], [106.6, 43.4], escape=("hv_ret", "ocp_kelvin_p"))
    # nearest legal drop point to (106.6, 53.5): F.Cu there carries the Kelvin_P / HOT5-monitor tracks
    import math as _m
    from shapely.geometry import Point as _P
    spot = None
    for x, y in sorted(((round(104.0 + 0.1 * i, 2), round(48.0 + 0.1 * j, 2)) for i in range(51) for j in range(81)),
                       key=lambda q: _m.dist(q, (106.6, 53.5))):
        if g["GEO"].conflicts("ocp_kelvin_n", CU, _P(x, y).buffer(0.3), limit=1, via=True):
            continue
        try:
            put(g, "ocp_kelvin_n", "In1.Cu", 0.3, [106.6, 43.4], [106.6, y], [x, y], escape=("hv_ret", "ocp_kelvin_p"))
        except SystemExit:
            continue
        spot = (x, y)
        break
    if spot is None:
        raise SystemExit("stage 21b: no legal KELVIN_N drop via near (106.6, 53.5)")
    drill(g, "ocp_kelvin_n", *spot, size=0.6)
    print("stage 21b: KELVIN_N drops to In2 at", spot)
    drill(g, "ocp_kelvin_n", 119.95, 72.4, size=0.85)
    put(g, "ocp_kelvin_n", "F.Cu", 0.3, [119.95, 72.4], "R33.2")
    g["S21B_KN_SPOT"] = spot          # the run under the pour is linked last (add_stage21b_kn), round every fixed patch


def add_stage21b_kn(g):
    """Stage 21b: KELVIN_N from its drop via to R33's via, under the In1 ocp_kelvin_p pour. In2 first (0.5 mm under
    the pour); In2 is a dense HOT-protection signal layer here, so In2 + B.Cu (still under the pour footprint, about
    1 mm further) is the next try; failing both, In2 + B.Cu with its via kept out of bus_fault_hot's corridor.
    Linked after every fixed patch."""
    spot = g["S21B_KN_SPOT"]
    ends = [f"@{spot[0]},{spot[1]},In2.Cu", "@119.95,72.4,In2.Cu"]
    # single-layer runs first: a layer change adds a via whose antipad cuts the In1 Kelvin pour under bus_fault_hot
    # (return_path19 SI1 failed on a mixed In2 / B.Cu route); B.Cu sits 0.94 mm under the pour, In2 0.5 mm
    ends_b = [f"@{spot[0]},{spot[1]},B.Cu", "@119.95,72.4,B.Cu"]
    ok = g["link"]("ocp_kelvin_n", ("In2.Cu",), (103.0, 47.0, 123.0, 75.0), 0.3, ends) or \
        g["link"]("ocp_kelvin_n", ("B.Cu",), (103.0, 47.0, 123.0, 75.0), 0.3, ends_b)
    if not ok:
        # neither layer alone has a lane: allow In2 + B.Cu, but keep any layer-change via out of a 1.2 mm corridor
        # under bus_fault_hot's F.Cu run (its reference is this In1 pour: SI1), via a temporary In1 keep-out
        from shapely.geometry import LineString as _LS
        from shapely.ops import unary_union as _uu
        G = g["GEO"]
        lanes = [_LS([g["_xy"](q) for q in t["points"]]) for t in g["TRACKS"]
                 if t["net"] == "bus_fault_hot" and t["layer"] == "F.Cu"]
        keep = _uu([ln.buffer(1.2) for ln in lanes])
        G._add(("In1.Cu",), keep, "bus_fault_hot")
        G._trees.clear()
        try:
            ok = g["link"]("ocp_kelvin_n", ("In2.Cu", "B.Cu"), (103.0, 47.0, 123.0, 75.0), 0.3, ends)
        finally:
            G.items["In1.Cu"] = [it for it in G.items["In1.Cu"] if it[0] is not keep]
            G._trees.clear()
    if not ok:
        raise SystemExit("stage 21b: ocp_kelvin_n run under the Kelvin pour")


def add_r5(g):
    """Up to R5_MAX legal 0.6 / 0.3 vias per R5 current pad, 0.85 mm apart (so merge_close_vias
    keeps them), on a 0.15 mm grid in the pad and in the same-net F.Cu copper within R5_REACH of it,
    nearest the pad centre first. Every spot is checked against all copper on every layer (the
    Kelvin pair runs under R5.1 on In1). Vias inside the pad are filled and capped.
    Stage 21 (DECISIONS 25): R5.4 (hv_ret) takes 0.8 / 0.5 mm vias, 1.05 mm apart, so the field's fusing I2t
    (20 um barrels, equal sharing) is no longer the series limiter under F1's clearing energy."""
    from shapely.geometry import Point, Polygon, box as _box
    import rules21
    G = g["GEO"]
    sense = r5_sense(G)
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
        vsize, vdrill, pitch = (0.8, 0.5, 1.05) if net == "hv_ret" else (0.6, 0.3, 0.85)
        for c in sorted(cand, key=lambda c: (round(c.distance(Point(cx, cy)), 3), c.x, c.y)):
            if len(placed) >= R5_MAX:
                break
            if any(c.distance(q) < pitch for q in placed + own):
                continue
            bad = G.conflicts(net, CU, c.buffer(vsize / 2), limit=8, via=True)
            # a conflict with an R5 sense pad's bounding box only: judge it on the true outline
            if bad and all(lay == "F.Cu" and o in sense for lay, o in bad) and \
                    all(sense[o].distance(c) >= vsize / 2 + rules21.clearance(net, o) + 0.03 for _, o in bad):
                bad = []
            if bad:
                continue
            g["via"](net, c.x, c.y, size=vsize)
            g["VIAS"][-1]["drill"] = vdrill
            placed.append(c)
        print(f"R5 {ref_pad}: {len(placed)} vias ({sum(pad.contains(q) for q in placed)} in the pad)")
