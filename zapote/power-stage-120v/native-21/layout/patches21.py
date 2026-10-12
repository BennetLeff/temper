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
    add_stack(g)
    add_stage8(g)
    add_stage13(g)
    add_stage14(g)
    add_stage16(g)


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
    put(g, "p_hb", "F.Cu", 0.3, [12.2, 72.6], [11.4, 71.8], "R94.1")
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
    # the stage-16 N run crosses the In1 ocp_kelvin_p protection pour (a pour; the base copper did the same,
    # DRC-clean in stage 16, and the pour split is in the Kelvin budget)
    put(g, "ocp_kelvin_n", "In1.Cu", 0.3, [41.3, 43.4], [106.6, 43.4], [106.6, 72.4], [119.95, 72.4],
        escape=("hv_ret", "ocp_kelvin_p"))
    drill(g, "ocp_kelvin_n", 119.95, 72.4, size=0.85)
    put(g, "ocp_kelvin_n", "F.Cu", 0.3, [119.95, 72.4], "R33.2")


def add_r5(g):
    """Up to R5_MAX legal 0.6 / 0.3 vias per R5 current pad, 0.85 mm apart (so merge_close_vias
    keeps them), on a 0.15 mm grid in the pad and in the same-net F.Cu copper within R5_REACH of it,
    nearest the pad centre first. Every spot is checked against all copper on every layer (the
    Kelvin pair runs under R5.1 on In1). Vias inside the pad are filled and capped."""
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
        for c in sorted(cand, key=lambda c: (round(c.distance(Point(cx, cy)), 3), c.x, c.y)):
            if len(placed) >= R5_MAX:
                break
            if any(c.distance(q) < 0.85 for q in placed + own):
                continue
            bad = G.conflicts(net, CU, c.buffer(0.3), limit=8, via=True)
            # a conflict with an R5 sense pad's bounding box only: judge it on the true outline
            if bad and all(lay == "F.Cu" and o in sense for lay, o in bad) and \
                    all(sense[o].distance(c) >= 0.3 + rules21.clearance(net, o) + 0.03 for _, o in bad):
                bad = []
            if bad:
                continue
            g["via"](net, c.x, c.y, size=0.6)
            placed.append(c)
        print(f"R5 {ref_pad}: {len(placed)} vias ({sum(pad.contains(q) for q in placed)} in the pad)")
