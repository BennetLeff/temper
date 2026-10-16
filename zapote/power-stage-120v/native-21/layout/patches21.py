"""Stage-6 hand fixes, applied by incr21.py on top of the frozen stage-5 copper (copper_base.json =
the routed stage-5 copper.json, c450f12c). The stage-4/5 record that produced it is patches21_v1.py;
its helpers are reused here.

REMOVE / add(g) / OPEN_IN1 / HANDLED as in patches21_v1.py. IN_PAD: references whose pad vias are
intended (filled and capped, DECISIONS.md 2026-10-08) and must not be moved off by dogbone().
"""
from patches21_v1 import CU, OPEN_IN1, drill  # noqa: F401  (OPEN_IN1 / CU re-exported for incr21)
import math  # noqa: E402
import rules21  # noqa: E402  (stage 35 clearance checks)
from layers21 import PLANE_ROLE, STACKUP  # noqa: E402  (stage 33: role planes from native-21/stackup.json)

# Stage 33, six-layer phase A: the routing layer sets of the authored groups (route_group, the L4 / HS sets) stay the
# four layers they were written for, so every patch lays the same copper on the six-layer stack as on four. Vias are
# still checked through the whole stack (CU). In3 / In4 are added deliberately (add_stage33_*), and the open-pair passes
# may use In3 (incr21; In4 carries the image planes).
ROUTE4 = tuple(lay for lay in CU if lay in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"))

# Stage 33 (layer-stack refactor): whole-stack layer sets (CU) and role planes (PLANE_ROLE: the hv_ret / bus_p trunks,
# the n_ls block) come from native-21/stackup.json; the layer of each hand-laid track or pour below is authored
# geometry and stays literal.

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
# stage 28: the OCP node / threshold nets come whole from stage28_ocp_lock.json; their base copper goes first
REMOVE += [{"net": "ocp_node"}, {"net": "ocp_thresh"}]
HANDLED = ("ocp_node", "ocp_thresh")   # stage 28: laid whole by add_stage28_ocp_lock (their router pairs are stale)

# R5 shunt current pads (task 04 round 5): native-21 fed R5.4 (HV_RET) through two 0.3 mm vias on
# a small F.Cu island and R5.1 (LEG_RET) through three at x 40.9. Up to 18 A in one via in the
# coherent return case, where native-17 had three 0.8 mm vias per side. Six filled 0.3 mm vias in
# each current pad take the layer transfer at the pad (a shunt's current pads carry their own vias).
IN_PAD = ("R5", "U26", "J2", "J5")   # stage 14: U27 / U28 / U35 removed; stage 35: the J2 / J5 land vias
# SW_B's B.Cu outline reaches under R5, but its fill never does (0 mm² in this box on the stage-5
# board): the outline alone kept HV_RET vias out of R5.4. Clip it there.
SWB_CLIP = (34.0, 12.0, 42.0, 18.0)


# Stage 12: F1 is a Class CC fuse in 10x38 clips at (252.00, 7.25) (owner-items/f1cc/). The F.Cu mains
# pours are redrawn round its new pads: ac_l_in shrinks to x 257-283 (pads 262.08 / 272.88 and J1.1);
# l_f's top block reaches x 243.5 (pads 231.12 / 241.92) and its strip under the ac_l_in clip starts at
# y 12.3, 3.2 mm from the clip pads (pad edge y 9.10).
MAINS_POURS = {("ac_l_in", "F.Cu"): [[251.35, 0.6], [251.35, 9.1], [271.0, 9.1], [271.0, 10.9], [279.4, 10.9], [279.4, 0.6]],
               ("l_f", "F.Cu"): [[229.5, 9.0], [229.5, 33.5], [236.8, 33.5], [236.8, 25.6], [240.0, 25.6],
                                 [240.0, 15.1], [265.0, 15.1], [265.0, 17.3], [273.5, 17.3], [273.5, 26.5],
                                 [279.5, 26.5], [279.5, 14.1], [267.8, 14.1], [267.8, 12.3], [240.0, 12.3],
                                 [240.0, 9.0], [237.85, 9.0], [237.85, 0.6], [223.5, 0.6], [223.5, 9.0]]}
# Stage 27 (DECISIONS 29): F1 moves 5.65 mm left and J1 becomes the 9.52 mm MKDS 5 with pin 1 (ac_l_in) at (274.6, 9.2)
# and pin 2 (ac_n_in) at (284.12, 9.2). ac_l_in follows F1 (x 251.35, the same 13.5 mm gap to l_f under the cartridge) and
# takes a tab round J1.1 down to y 10.9, ending 3.2 mm short of J1.2. l_f's top block ends 0.38 mm past F1's moved pads;
# beside J1 its strip and the RV1 column start at y 14.1 (3.2 mm from the tab) and the strip widens to y 17.3 there
# (3.2 mm thick; RV1's surge path), starting at x 265.0, 3.4 mm from C1's ac_n_in pad.


# Stage 13: resonant bank becomes 5 radial TDK B32654 (pins x 163.0 / 190.5, rows y 53.2-111.5). The B.Cu
# res_a strip widens to x 166 and spans y 52.0-112.9; the sw_b band's lower edge rises from y 50 to 46.8
# between x 150 and 188 (5 mm tank rule to the res_a strip), and the sw_b strip widens to x 188 and
# reaches y 112.9. The last pad edges stay >= 8 mm from the SELV line_zc_raw run (B.Cu, y 121.1).
RES_A_STRIP = (150.0, 52.0, 166.0, 112.9)
SWB_STRIP = (188.0, 46.8, 200.6, 112.9)
SWB_BAND_TRIM = (150.0, 46.8, 188.0, 50.1)


# Stage 22 (DECISIONS 27): DIS = NAND(permit_gate, BIAS_GOOD). The leg_x-dis nets (Q1/Q4 drain, R8/R16, U22/U23.1) are gone;
# U22/U23.1 now join permit_gate (re-joined by the pair passes). BIAS_BAD becomes BIAS_GOOD on the same three pins.
REMOVE += [{"net": "leg_a-dis"}, {"net": "leg_b-dis"}]
RENAME_NETS = {"bias_bad": "bias_good"}

# Stage 30 (DECISIONS 33; c24 M1b): the notice stages (Q7-Q9, D14-D16, R89 / R90 / R107 / R108 / R122 / R123), the HS
# monitor isolators U33 / U34 with C137 / C138 / C141 / C142, the bias OR U25 / C88 and its filter R126 / C143 are deleted.
# Their nets go whole, as does U32.13's 80 mm run to U25 (bias_ls_bad): the heartbeat pump now sits beside U32, so hb_rx is
# a fresh few-mm route. U32 stays where it was as the heartbeat isolator: the LS monitor's 5 V keeps its copper as ls_v5,
# U32's no-connect pins rename.
REMOVE += [{"net": n} for n in ("bias_bad_flt", "bias_bad_raw", "bias_ha_bad", "bias_hb_bad", "bias_ls_bad", "monitor_ls-isoin",
                                "monitor_ls-base", "bias_ha.monitor-base", "bias_ha.monitor-isoin",
                                "bias_hb.monitor-base", "bias_hb.monitor-isoin")]
REMOVE += [{"net": f"{m}.iso-nc{k}"} for m in ("bias_ha.monitor", "bias_hb.monitor") for k in (2, 5, 6, 8, 10, 11, 12, 15)]
RENAME_NETS.update({"monitor_ls-v5": "ls_v5"})
# U2.8's v3v3 drop via moves from (38.173, 57.632) to (37.7, 57.9) (add_stage30): 8.2 mm from U43's LS pins beside U41
REMOVE += [{"net": "v3v3", "box": [37.9, 57.4, 38.45, 57.9], "kind": "via"},
           {"net": "v3v3", "box": [37.9, 57.4, 38.45, 57.9], "kind": "track", "layer": "F.Cu", "touch": True}]
RENAME_NETS.update({f"monitor_ls.iso-nc{k}": f"hb.iso-nc{k}" for k in (2, 5, 6, 8, 10, 11, 12, 15)})

# Stage 27 (DECISIONS 29): R1 / R2 (the X-cap bleed pair) move 0.9 mm down with F1's clip courtyard; their bounded pad
# escapes follow (the R1.1 l_f escape also reaches the moved pad's track end).
MOVE_ESCAPES = {("R1", "2"): [223.637, 15.0, 228.363, 24.8], ("R2", "1"): [223.637, 15.0, 228.363, 24.8],
                ("R1", "1"): [223.4, 8.0, 225.7, 17.0], ("R2", "2"): [226.3, 22.9, 229.9, 26.8]}

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
        if (z["net"], z["layer"], z.get("name")) in (("hv_ret", PLANE_ROLE["hv_ret"], "hv_ret trunk"),
                                                     ("bus_p", PLANE_ROLE["bus_p"], "bus_p trunk")):
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
        for lay in CU[1:]:                  # every layer under the (F.Cu) exposed pad
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
    add_stage30_r91(g)      # first: R91.2's pocket escape, before the leg_ret relinks route through the pocket
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
    add_stage27(g)
    add_stage21b_kn(g)   # last: routes round every fixed patch
    add_stage28_ocp_lock(g)   # after the Kelvin pair, as on the stage-27 board it was taken from
    add_stage30(g)            # after every fixed lane: the long heartbeat-group links route round them
    add_stage32_in2(g)        # last: re-layers three hops that add_stage30 / the bias_bad group laid on B.Cu
    add_stage33(g)            # six-layer stacks only (stackup image_planes); a no-op on the four-layer board
    add_stage35(g)            # J2 / J5 SMT terminals: their F.Cu pads reach B.Cu only through these vias
    resolve_zone_priorities(g["ZONES"])


# Stage 35 (candidate 35, 11-candidates/c35-smt-terminals): J2 (coil_feed) / J5 (res_a) are Wuerth REDCUBE SMT WP-SMBU
# 7466004R, one F.Cu ring pad (OD 8.5) round a D5.2 NPTH, at the THR studs' poses. The THR's four plated D1.85 pins
# carried the terminal current into B.Cu (J5's only path to the bank: res_a has no F.Cu pour past its stud land); the
# SMT pad needs vias for it. Wuerth's REDCUBE SMD design guide (p.7 Fig. 3, vias in the copper round the pad; p.11,
# 0.3-0.4 mm vias, >= 25 um plating) supports it. 20 vias per terminal sit in the 9.2 mm stud land (route21, F and B):
# two per half-edge 4.1 mm off the centre lines plus one per corner, copper within +/-4.525 mm (the THR pads'
# +/-4.535 mm square envelope; the corner vias reach 0.47 mm further diagonally than the THR's round pads, checked by
# the chain's DRC and c35-smt-terminals/scripts/terminal_spacing.py). Barrels: 20 x pi x 0.3 = 18.8 mm of wall against
# the THR's 4 x pi x 1.85 = 23.2 mm. The vias are 0.85 / 0.3 (the 0.3 mm drill of every via, so no new drill), their
# rings 0.3 mm apart: on In1 / In2 the rings stand alone, and task 04's topology check needs each one resolved on its
# 0.125 mm grid. The first stage-35 chain failed it with 0.6 / 0.3 vias (a 0.15 mm ring does not resolve, as on the
# mains nets at stage 32; incr21.STD_VIA_KEEP), the second with touching 0.85 rings 0.85 mm apart (the physical union
# joins them, the grid does not). The inner edge of the first via on each side reaches 0.2 mm into the pad ring (filled
# and capped, as every 0.3 mm via on this board).
S35_TERMINALS = {"J5": ("res_a", (132.0, 70.5)), "J2": ("coil_feed", (132.0, 85.5))}
S35_EDGE, S35_ALONG, S35_VIA = 4.1, (1.8, 2.95), 0.85


def s35_spots(cx, cy):
    out = []
    for sx in (1, -1):
        for sy in (1, -1):
            out += [(cx + sx * S35_EDGE, cy + sy * a) for a in S35_ALONG]
            out += [(cx + sx * a, cy + sy * S35_EDGE) for a in S35_ALONG]
            out.append((cx + sx * S35_EDGE, cy + sy * S35_EDGE))
    return [(round(x, 3), round(y, 3)) for x, y in out]


S35_LAND = 4.6        # route21's stud lands: 9.2 mm squares on F.Cu and B.Cu round each terminal centre


def s35_conflicts(g, net, x, y, size=0.6):
    """Other-net tracks, vias and pads (THT / NPTH on every layer, SMD on F.Cu) closer than their rule to a land via.
    Pours are left out: GEO holds their authored outlines, not the fill, and a fill always yields to the via. A via
    inside the stud land (checked by the caller) cannot pull another net's fill closer than the land edge already does,
    on F / B or in plan view (barrier, RES_A 12.6 mm); on In1 / In2 there are no pours of these nets near J2 / J5."""
    from shapely.geometry import LineString, Point, box
    v = Point(x, y).buffer(size / 2)
    out = []
    for t in g["TRACKS"]:
        if t["net"] != net and t["layer"] in CU:
            geo = LineString([g["_xy"](q) for q in t["points"]]).buffer(t["width"] / 2)
            if geo.distance(v) < rules21.clearance_on(net, t["net"], t["layer"]) + 0.03:
                out.append((t["layer"], t["net"], "track"))
    for o in g["VIAS"]:
        if o["net"] != net:
            if Point(*o["at"]).buffer(o["size"] / 2).distance(v) < max(rules21.clearance_on(net, o["net"], lay) for lay in CU) + 0.03:
                out.append(("*", o["net"], "via"))
        elif math.dist(o["at"], (x, y)) - o.get("drill", 0.3) < 0.5:
            out.append(("*", net, "same-net via within 0.5 mm wall to wall"))
    for p in g["GEO"].pads:
        if p["net"] == net or not (p["net"] or p["npth"]):
            continue
        lays = CU if p["tht"] else ("F.Cu",)
        need = 0.3 if p["npth"] else max(rules21.clearance_on(net, p["net"], lay) for lay in lays)
        if box(*p["box"]).distance(v) < need + 0.03:
            out.append(("pad", p["net"] or "<npth>", f"{p['ref']}.{p['pad']}"))
    return out


def add_stage35(g):
    """Stage 35: the J2 / J5 land vias (S35_TERMINALS); a no-op unless the terminals are the SMT part."""
    pads = [p for p in g["GEO"].pads if p["ref"] in S35_TERMINALS and p["pad"] == "1"]
    if not pads or any(p["tht"] for p in pads):
        return
    n = 0
    for ref, (net, (cx, cy)) in S35_TERMINALS.items():
        for x, y in s35_spots(cx, cy):
            # stage 38: a frozen base from stage 35 on already holds these vias; adding them again is not a no-op
            if any(o["net"] == net and math.dist(o["at"], (x, y)) < 1e-3 and o["size"] == S35_VIA for o in g["VIAS"]):
                continue
            if max(abs(x - cx), abs(y - cy)) + S35_VIA / 2 > S35_LAND:
                raise SystemExit(f"stage 35 via {net} ({x}, {y}) leaves the {ref} stud land")
            bad = s35_conflicts(g, net, x, y, size=S35_VIA)
            if bad:
                raise SystemExit(f"stage 35 via {net} ({x}, {y}): {bad[:3]}")
            g["via"](net, x, y, size=S35_VIA)
            n += 1
    print(f"stage 35: {n} terminal land vias (J2 / J5)")


# Stage 37 (candidate 37, 11-candidates/c37-geometry-cleanup) is not a patch: it is a post-route transform of a finished,
# DRC-clean copper.json, track_cleanup21.py (fold-backs, acute corners, right angles, any-angle runs; DECISIONS 43). It
# needs the built board's export as its obstacle model and runs last, after every lane's patches and passes.


# Stage 38 (candidate 23, DECISIONS 47 item 1): PS1 (IRM-20-15) and its net v15_selv are deleted. The frozen base (the
# stage-35 copper) is edited before it is loaded (incr21.load), because its tracks name PS1's pads:
#  - every v15_selv track and via goes (PS1.4 -> J4.1, about 250 mm on B.Cu / F.Cu, three vias in the SELV spine);
#  - the selv_gnd B.Cu stub from PS1.3 up to the via at (210.8, 98.2) goes (that via keeps U36's return on the In2 pour);
#  - L_FILT: the 1.0 mm F.Cu run that dropped from the C3 via (230.5, 107) to PS1.1 and climbed back to F2.1 becomes one
#    run at the R67 junction (242.96, 121.7), east at y 121.7 and up at 45 deg to F2.1 on the stage-35 approach line
#    (262.2, 117.6), which keeps 3.6 mm to the N_FILT via (HOT functional 3.2 mm): 40.5 mm instead of 60.5 mm, and
#    the 42 deg corner it made at PS1.1 (a track_geometry acute corner) is gone;
#  - N_FILT: the B.Cu run to PS1.2 ends instead at the via that takes N_FILT to J11.2 on In1. That via (0.6 / 0.3 at
#    (257.0, 116.8)) sat inside PS1.2's pad; standing alone, its 0.15 mm F.Cu ring fragments on task 04's 0.125 mm grid
#    (the kit topology preflight fails), so it becomes a 0.85 / 0.3 via moved 0.28 mm down the same 45 deg line to
#    (256.8, 116.6), which keeps 3.375 mm to F2.1 and 3.6 mm to the new L_FILT run (HOT functional 3.2 mm).
# Nothing else in the base changes; the J11 / F2 / R130 / D3 / D17 poses are kept (no compaction, DECISIONS 47 item 6).
S38_V15 = "v15_selv"
S38_SELV_GND_STUB = ((210.8, 115.6), (210.8, 98.2))
S38_L_FILT = [[230.5, 107.0], [242.96, 121.7], [258.1, 121.7], [262.2, 117.6], [262.475, 117.6]]
S38_N_FILT_END = [[237.5, 113.0], [253.2, 113.0], [256.8, 116.6]]
S38_N_FILT_VIA = ((257.0, 116.8), (256.8, 116.6), 0.85)        # from, to, size


def edit_base(base):
    """Stage 38 edit of a frozen base copper dict (in place); a no-op on a base without PS1's copper."""
    pt = lambda q: tuple(round(v, 3) for v in q) if not isinstance(q, str) else q
    tr, vi = base["tracks"], base["vias"]
    n0 = (len(tr), len(vi))
    names = lambda t: {q for q in t["points"] if isinstance(q, str)}
    if not any(t["net"] == S38_V15 or any(q.startswith("PS1.") for q in names(t)) for t in tr) and \
            not any(v["net"] == S38_V15 for v in vi):
        return 0
    keep = []
    for t in tr:
        ps = [pt(q) for q in t["points"]]
        if t["net"] == S38_V15:
            continue
        if t["net"] == "selv_gnd" and t["layer"] == "B.Cu" and sorted(ps) == sorted(S38_SELV_GND_STUB):
            continue
        if t["net"] == "l_filt" and t["layer"] == "F.Cu" and t["width"] == 1.0 and \
                (ps == [(230.5, 107.0), (250.0, 130.0), "PS1.1"] or ps[:1] == [(255.8, 136.4)]):
            continue
        if t["net"] == "n_filt" and t["layer"] == "B.Cu" and ps[:1] == [(255.8, 115.6)]:
            continue
        if t["net"] == "n_filt" and t["layer"] == "B.Cu" and ps[-1:] == ["PS1.2"]:
            assert ps[-3:-1] == [(237.5, 113.0), (250.0, 113.0)], ps
            t = {**t, "points": t["points"][:-3] + [list(q) for q in S38_N_FILT_END]}
        if t["net"] == "n_filt" and t["layer"] == "In1.Cu" and ps[:1] == [S38_N_FILT_VIA[0]]:
            t = {**t, "points": [list(S38_N_FILT_VIA[1])] + t["points"][1:]}
        if any(isinstance(q, str) and q.startswith("PS1.") for q in t["points"]):
            raise SystemExit(f"stage 38: base track still names a PS1 pad: {t}")
        keep.append(t)
    keep.append({"net": "l_filt", "layer": "F.Cu", "width": 1.0, "points": [list(q) for q in S38_L_FILT]})
    base["tracks"] = keep
    base["vias"] = [v for v in vi if v["net"] != S38_V15]
    for v in base["vias"]:
        if v["net"] == "n_filt" and pt(v["at"]) == S38_N_FILT_VIA[0]:
            v["at"], v["size"] = list(S38_N_FILT_VIA[1]), S38_N_FILT_VIA[2]
    n = (n0[0] - len(base["tracks"]), n0[1] - len(base["vias"]))
    print(f"stage 38: PS1 copper removed from the frozen base (net {n[0]} tracks, {n[1]} vias); L_FILT / N_FILT re-laid to F2 / J11")
    return n


# Stage 41 (candidate 36, 11-candidates/c36-tank-copper; DECISIONS 51 targets): tank / FET-row copper at R5. The board
# copper at R5.4 and the FET row was over the laminate's 130 C MOT in still air (B3 ratings gate). Edits of the frozen
# s40 base (DECISIONS 52), made before it is loaded (incr21.load), like edit_base; outlines in stage41_pours.json (from
# c36-tank-copper/scripts/pours41.py, every other-net item and zone outline kept at its rules21 clearance):
#  - F.Cu hv_ret: the 3.8 x 3.6 mm island at R5.4 becomes an 86 mm2 spreader south to y 25.5 between the LOW-group gate
#    runs at x 35.95 (leg_b-out_l) and x 43.25 (leg_a-gate_l). It stops 1.5 mm short of C40.2, so C40's lead is not tied
#    to R5.4's heat (a version reaching C40.2 warmed C40 by 0.75 K on the body model);
#  - F.Cu leg_ret: R5.1's pour reaches east to Q3.1 (y <= 10.4, LOW group only there);
#  - B.Cu leg_ret (new): R5.1's via field and Q6.3 on B.Cu, 3.2 mm from the sw_b / sw_a outlines;
#  - In1 leg_ret: the leg-A neck under Q3.2's antipad (2.83 mm at (50.05, 11.07), task 04's hottest In1 cells) widens
#    to y 14.7 between the Kelvin run (x 42.2) and x 58; the zone already outranks the hv_ret trunk there;
#  - two of R5.4's six hv_ret vias (0.8 / 0.5) move from the pad's south-east corner to its north-west, keeping the
#    via field's drills (the F1 fusing row counts them within 6 mm of R5.4), so the sw_b B.Cu lane, which kept 3.2 mm
#    from them, can rise over R5 (outline raised to y 15.7 over x 33-42): the lane's pinch between R5.4 and C40.2's
#    antipad was 4.4 mm.
S41 = "stage41_pours.json"
S41_NEW_B = "leg_ret R5.1-Q6.3 (B)"


def edit_base41(base):
    """Stage 41 edit of a frozen base copper dict (in place); a no-op on a base that already carries it."""
    import json
    from pathlib import Path
    from shapely.geometry import Polygon, box
    if any(z.get("name") == S41_NEW_B for z in base["zones"]):
        return 0
    spec = json.loads(Path(__file__).with_name(S41).read_text())
    zones = base["zones"]
    for p in spec["pours"]:
        if p["replaces"]:
            hit = [z for z in zones if z.get("name") == p["replaces"] and z["layer"] == p["layer"] and z["net"] == p["net"]]
            if len(hit) != 1:
                raise SystemExit(f"stage 41: base zone {p['replaces']!r} on {p['layer']} not found once ({len(hit)})")
            hit[0]["outline"], hit[0]["holes"] = p["outline"], p["holes"]
        else:
            zones.append({"net": p["net"], "layer": p["layer"], "priority": 3, "name": p["name"],
                          "outline": p["outline"], "holes": p["holes"]})
    r = spec.get("sw_b_raise")
    if r:
        swb = [z for z in zones if z["net"] == r["net"] and z["layer"] == r["layer"]]
        assert len(swb) == 1, len(swb)
        poly = Polygon(swb[0]["outline"], swb[0]["holes"]).union(box(*r["box"])).simplify(0)
        assert poly.geom_type == "Polygon", poly.geom_type
        swb[0]["outline"] = [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]]
        swb[0]["holes"] = [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in poly.interiors]
    for net, (x, y), size, dr in spec.get("via_adds", []):
        if any(v["net"] == net and math.dist(v["at"], (x, y)) < 1e-3 for v in base["vias"]):
            raise SystemExit(f"stage 41: a {net} via already sits at ({x}, {y})")
        base["vias"].append({"net": net, "at": [x, y], "size": size, "drill": dr})
    moved = 0
    for a, b in spec.get("via_moves", []):
        hit = [v for v in base["vias"] if v["net"] == "hv_ret" and math.dist(v["at"], a) < 1e-3]
        if len(hit) != 1:
            raise SystemExit(f"stage 41: hv_ret via at {a} not found once ({len(hit)})")
        hit[0]["at"] = list(b)
        moved += 1
    print(f"stage 41: {len(spec['pours'])} tank / FET-row pours at R5 ({spec.get('variant', '')}); sw_b B.Cu lane "
          f"{'raised over R5' if r else 'unchanged'}; {moved} R5.4 vias moved, {len(spec.get('via_adds', []))} added")
    return moved


# Stage 42 (candidate 39, DECISIONS 54; 11-candidates/c39-gate-network): R10 / R12 / R18 / R20 become 68 ohm 2512 on the
# same axis, turned 180 deg by place.py (pad 1 = OUT at y 9.4375 north, pad 2 = gate at y 15.3625 south; centre y 12.4,
# 0.2 mm north so the courtyard clears the PMEG's), and the 0603 pull-downs R11 / R13 / R19 / R21 move 0.5 mm west. The
# 2512's pads would sit on the old gate run (x g - 1.35), and a gate run down the resistor's west side to y 20 would
# come within 3.2 mm of the other potential group's R_off / OUT copper (R54 / R57 at x g - 5.5), so each gate is re-laid
# locally, edited into the frozen base before it is loaded, like edit_base41:
#  - FET gate pin -> pad 2: the 0.8 mm stub to y 6.2, then 0.4 mm down x g - 2.15 (between the pull-down and the OUT
#    pad, 0.375 / 0.275 mm) into pad 2's north-west corner; every point keeps >= 3.4 mm from the R_off pad / OUT track;
#  - pad 2 -> D6 anode / Cgs: the old run down x g - 1.35, unchanged below pad 2;
#  - pull-down pad 1 -> the new run; the pull-down moves 0.5 mm west and 0.5 mm north (its gate pad keeps 3.2 mm from
#    the other group's OUT run), its source via 0.5 mm west with any track that ended on it (R21's In2 leg_ret run);
#  - OUT run: the old one, turned north at x g + 2.4 (it ran along y 14.3, now 0.15 mm from pad 2) and up x g + 1.0
#    under the resistor body to pad 1;
#  - R10 only: the sw_a stub via at (60.925, 11.275) (a redundant second via of R11.2) goes: it sits in the new channel;
#  - R11 only: turned 180 deg (gate pad north, sw_a pad south) and its sw_a via goes to (59.6, 13.3), south-east of the
#    pad. Left at (59.4, 9.7), the via's 3.5 mm In1 antipad narrowed the Q3 source -> R5 leg_ret neck 2.869 -> 2.415 mm
#    (shoot-through-f1 s42 first build: F1 ratio 0.993 -> 0.882); east of x 59.75 it would meet the channel.
S42_GATES = (("leg_a-gate_h", "leg_a-out_h", "R11", 62.6), ("leg_a-gate_l", "leg_a-out_l", "R13", 44.6),
             ("leg_b-gate_h", "leg_b-out_h", "R19", 4.5), ("leg_b-gate_l", "leg_b-out_l", "R21", 22.5))
S42_PD_VIAS = {"R11": ("sw_a", (59.9, 9.7), (59.6, 13.3)), "R19": ("sw_b", (1.8, 9.9), (1.3, 9.9)),
               "R21": ("leg_ret", (19.8, 9.7), (19.3, 9.7))}
S42_PD_FLIP = {"R11"}                              # pull-downs at rotation 270 (place.py): pad 1 (gate) north
S42_DROP = {"sw_a": [((59.9, 11.275), (60.925, 11.275))]}, [("sw_a", (60.925, 11.275))]
S42_PAD1_Y, S42_PAD2_Y = 9.4375, 15.3625         # 2512 pad centres at rotation 270, centre y 12.4


def edit_base42(base):
    """Stage 42 edit of a frozen base copper dict (in place); a no-op on a base that already carries it."""
    r3 = lambda q: (round(q[0], 3), round(q[1], 3))
    pts = lambda t: [q if isinstance(q, str) else r3(q) for q in t["points"]]
    tr = base["tracks"]
    if any(t["net"] == "leg_a-gate_h" and pts(t)[:2] == [(62.6, 4.21), (62.6, 6.2)] for t in tr):
        return 0

    def take(net, width, want, layer="F.Cu"):
        hit = [t for t in tr if t["net"] == net and t["layer"] == layer and abs(t["width"] - width) < 1e-6 and want(pts(t))]
        if len(hit) != 1:
            raise SystemExit(f"stage 42: {net} {width} mm base track not found once ({len(hit)})")
        return hit[0]

    n = 0
    for gate, out, pd, g in S42_GATES:
        x_c, x_d = round(g - 2.15, 3), round(g - 1.35, 3)
        t = take(gate, 0.8, lambda p: p == [(g, 4.21), (g, 11.14)])
        t["points"] = [[g, 4.21], [g, 6.2]]
        tr.append({"net": gate, "layer": "F.Cu", "width": 0.4,
                   "points": [[g, 6.2], [x_c, 8.35], [x_c, 14.55], [x_d, 15.35]]})
        t = take(gate, 0.4, lambda p: p[:3] == [(g, 11.14), (x_d, 12.0), (x_d, 20.3)])
        t["points"] = [[x_d, S42_PAD2_Y]] + t["points"][2:]
        t = take(gate, 0.4, lambda p: len(p) == 2 and abs(p[0][0] - (g - 2.7)) < 1e-3 and p[1] == (x_d, 12.93))
        y_pd1 = 10.775 if pd in S42_PD_FLIP else 12.425
        t["points"] = [[round(g - 3.2, 3), y_pd1], [x_c, y_pd1]]
        t = take(out, 0.6, lambda p: p[-1] == (g, 14.3) and p[-2][1] == 14.3)
        t["points"] = t["points"][:-1] + [[round(g + 2.4, 3), 14.3], [round(g + 1.0, 3), 12.9], [round(g + 1.0, 3), S42_PAD1_Y]]
        n += 4
    for pd, (net, at, new) in S42_PD_VIAS.items():
        hv = [v for v in base["vias"] if v["net"] == net and r3(v["at"]) == at]
        ht = [t for t in tr if t["net"] == net and pts(t) == [f"{pd}.2", at]]
        if len(hv) != 1 or len(ht) != 1:
            raise SystemExit(f"stage 42: {pd} source via / track at {at} not found once ({len(hv)}, {len(ht)})")
        hv[0]["at"] = list(new)
        ht[0]["points"] = [f"{pd}.2", list(new)]
        for t in tr:                     # other tracks that ended on the via (any layer) follow it
            if t is not ht[0] and t["net"] == net:
                t["points"] = [list(new) if not isinstance(q, str) and r3(q) == at else q for q in t["points"]]
    drop_t, drop_v = S42_DROP
    for net, segs in drop_t.items():
        for a, b in segs:
            t = take(net, 0.25, lambda p: p == [a, b])
            tr.remove(t)
    for net, at in drop_v:
        hv = [v for v in base["vias"] if v["net"] == net and r3(v["at"]) == at]
        if len(hv) != 1:
            raise SystemExit(f"stage 42: {net} via at {at} not found once ({len(hv)})")
        base["vias"].remove(hv[0])
    print(f"stage 42: four gate runs re-laid for the 68 ohm 2512 turn-on resistors ({n} tracks edited, 4 added); "
          f"pull-down source vias moved (R11's to (59.6, 13.3)); R10's sw_a stub via removed")
    return n


# Stage 44 (candidate 44, SELV-spine lane; OPEN-ITEMS S10; 11-candidates/c44-selv-spine): the SELV return-path open
# changes. The slow SELV lines' F.Cu runs ride the In1 v3v3 pour and their B.Cu runs the In2 selv_gnd pour, so every
# F.Cu <-> B.Cu via of PERMIT / BUS_FAULT / BUS_FAULT_ISO / BIAS_GOOD needs a v3v3-selv_gnd capacitor within 3.0 mm
# (return_path19). Seven 100 nF 0603 transfer caps (c_ref_xfer_6..12, C169-C175) sit beside those vias, each pad on its
# own plane via 0.85 mm off the pad (the C153-C156 rule: <= 1.6 mm), or on an existing plane via (C171 pad 2). Poses
# from scripts/cap_spots.py on the s43 board (no other-net copper within rules21 clearance + 0.02 mm on any layer,
# >= 8.1 mm plan view from HOT copper, above the 8.047 mm D5 floor). Two vias move:
#  - BUS_FAULT: U13.4's drop via (34.843, 131.565) moves 0.97 mm down its own B.Cu trunk to (35.0, 132.523), 2.60 mm
#    from C170 (0.2 mm from R134.1), past the U13 / R134 / C167 row that leaves no legal cap pose within 3 mm of the
#    old spot;
#  - BIAS_GOOD: the U40 feed's In2 hop ended on an In2 -> B.Cu via at (69.2, 127.0) on the SELV pour edge (no pour
#    under its ring on either side: an open change with no reference). The In2 leg now runs on along the B.Cu trunk's
#    own path (the stair-step on the 8 mm line) to the leg-A drop via (74.0, 123.4), which C171 serves; the (69.2, 127.0)
#    via goes and the B.Cu trunk is unchanged.
# Each entry: ref -> (path, cx, cy, angle, v3v3 plane via, selv_gnd plane via); pad 1 = v3v3 (C_0603: at angle 0 west,
# 90 south, as xfer_spots.py), pad 2 = selv_gnd; place.py takes the poses from here.
S44_CAPS = {
    "C169": ("c_ref_xfer_6", 32.1, 119.4, 90.0, (31.25, 120.175), (31.25, 118.625)),     # PERMIT leg-B drop (33.2, 120.2)
    "C170": ("c_ref_xfer_7", 35.1, 135.9, 90.0, (34.25, 136.675), (34.25, 135.125)),     # BUS_FAULT drop (35.0, 132.523)
    "C171": ("c_ref_xfer_8", 76.0, 122.512, 0.0, (74.375, 122.512), (77.401, 122.512)),  # BIAS_GOOD leg-A drop (74.0, 123.4)
    "C172": ("c_ref_xfer_9", 67.8, 128.2, 0.0, (66.425, 128.8), (69.175, 128.8)),        # PERMIT leg-A drop (70.0, 127.8)
    "C173": ("c_ref_xfer_10", 78.73, 125.78, 0.0, (77.355, 125.18), (80.105, 125.18)),   # BUS_FAULT_ISO (76.825, 125.875)
    "C174": ("c_ref_xfer_11", 36.5, 175.4, 90.0, (37.35, 176.175), (37.35, 174.625)),    # PERMIT at J4 (36.5, 178.6)
    "C175": ("c_ref_xfer_12", 33.0, 73.1, 90.0, (32.15, 73.875), (32.15, 72.325)),       # BIAS_GOOD leg-B drop (33.2, 70.4)
}
S44_EXISTING_VIAS = {(77.401, 122.512)}          # plane vias already in the base (C171 pad 2 lands on it)
S44_BUS_FAULT_VIA = ((34.843, 131.565), (35.0, 132.523))
S44_BIAS_GOOD_VIA = (69.2, 127.0)


def s44_pads(ref):
    """(v3v3 pad centre, selv_gnd pad centre) of a stage-44 cap."""
    _, cx, cy, ang, _, _ = S44_CAPS[ref]
    dx, dy = {0: (-0.775, 0.0), 90: (0.0, 0.775), 180: (0.775, 0.0), 270: (0.0, -0.775)}[int(ang)]
    return (round(cx + dx, 3), round(cy + dy, 3)), (round(cx - dx, 3), round(cy - dy, 3))


def edit_base44(base):
    """Stage 44 edit of a frozen base copper dict (in place); a no-op on a base that already carries it."""
    r3 = lambda q: (round(q[0], 3), round(q[1], 3))
    pts = lambda t: [q if isinstance(q, str) else r3(q) for q in t["points"]]
    tr, vias = base["tracks"], base["vias"]
    if any(t["net"] == "v3v3" and t["points"][0] == "C169.1" for t in tr):
        return 0

    def one(seq, what):
        if len(seq) != 1:
            raise SystemExit(f"stage 44: {what} not found once ({len(seq)})")
        return seq[0]
    # BUS_FAULT: the drop via moves down its own B.Cu trunk; the F.Cu escape follows (45 / 90 deg), the B.Cu stub and
    # the trunk's tail under U13.4 go
    old, new = S44_BUS_FAULT_VIA
    one([v for v in vias if v["net"] == "bus_fault" and r3(v["at"]) == old], "bus_fault via")["at"] = list(new)
    t = one([t for t in tr if t["net"] == "bus_fault" and t["layer"] == "F.Cu" and pts(t)[-1] == old], "bus_fault F.Cu escape")
    t["points"] = t["points"][:-1] + [[34.843, 131.565], [34.843, 132.366], list(new)]
    tr.remove(one([t for t in tr if t["net"] == "bus_fault" and t["layer"] == "B.Cu" and pts(t)[-1] == old], "bus_fault B.Cu stub"))
    corner = (35.172, 132.695)          # the trunk's last bend; the via sits on its next (45 deg) leg
    t = one([t for t in tr if t["net"] == "bus_fault" and t["layer"] == "B.Cu" and corner in pts(t)], "bus_fault B.Cu trunk")
    t["points"] = t["points"][:pts(t).index(corner) + 1] + [list(new)]
    # BIAS_GOOD: the In2 leg runs on to the leg-A drop along the B.Cu trunk's path; the edge via goes
    bv = S44_BIAS_GOOD_VIA
    vias.remove(one([v for v in vias if v["net"] == "bias_good" and r3(v["at"]) == bv], "bias_good edge via"))
    trunk = one([t for t in tr if t["net"] == "bias_good" and t["layer"] == "B.Cu" and pts(t)[0] == (74.0, 123.4)], "bias_good B.Cu trunk")
    stair = pts(trunk)[:pts(trunk).index(bv) + 1]
    t = one([t for t in tr if t["net"] == "bias_good" and t["layer"] == "In2.Cu" and pts(t)[0] == bv], "bias_good In2 leg")
    t["points"] = [list(q) for q in stair] + t["points"][1:]
    # the transfer caps: each pad to its plane via (0.3 mm, as C168)
    n = 0
    for ref, (_, _, _, _, v1, v2) in S44_CAPS.items():
        for k, (net, at, pad) in enumerate(zip(("v3v3", "selv_gnd"), (v1, v2), s44_pads(ref)), 1):
            if at not in S44_EXISTING_VIAS:
                if any(math.dist(v["at"], at) < 0.6 for v in vias):
                    raise SystemExit(f"stage 44: a via already sits at {at}")
                vias.append({"net": net, "at": list(at), "size": 0.6, "drill": 0.3})
            else:
                one([v for v in vias if v["net"] == net and r3(v["at"]) == at], f"{net} via at {at}")
            tr.append({"net": net, "layer": "F.Cu", "width": 0.3, "points": [f"{ref}.{k}", list(at)]})
            n += 1
    print(f"stage 44: {len(S44_CAPS)} SELV transfer caps C169-C175 with {n} plane-via stubs; bus_fault drop via -> "
          f"{new}; bias_good In2 leg on to (74.0, 123.4), edge via {bv} removed")
    return n


# Stage 48 (candidate 48, c48-ldo-en-ref-watch; OPEN-ITEMS S19, B13 H1 / H2): the parts this stage adds, one source for
# place.py (poses, put before the zone packs so no packed part moves) and edit_base48 (the base copper they replace).
#   S19: EN of U3 / U37 / U38 / U39 (TPS70950QDBVRQ1) from 100 k / 27 k dividers instead of IN (SBVS186H 7.4 p.13);
#   H1: the REF25 watchdog 63.4 k / 11.7 k into U14 INB- (pin 4), OUTB (pin 6) onto HOT5_UV_RAW, U14 VDD and C48 on HOT5;
#   H2: BIAS_GOOD -> 220 k (1206) -> J4 pin 1.
# Each entry: ref -> (path, cx, cy, angle, footprint); at angle 0 pad 1 is west, 90 south, 180 east, 270 north.
# Poses checked with c48-ldo-en-ref-watch/scripts/fit_check.py (rules21 clearance on every layer, 0.1 mm courtyards).
S48_PARTS = {
    "R136": ("r_ldo_en_top", 113.3, 63.1, 270.0, "0603"),          # V15_LS north, HOT5_EN south
    "R137": ("r_ldo_en_bot", 115.0, 63.1, 90.0, "0603"),           # HOT5_EN south, Kelvin north
    "R138": ("monitor_ls.rldo_en_top", 108.158, 89.845, 0.0, "0603"),
    "R139": ("monitor_ls.rldo_en_bot", 108.921, 91.895, 180.0, "0603"),
    "R140": ("bias_ha.monitor.rldo_en_top", 57.958, 100.545, 270.0, "0603"),
    "R141": ("bias_ha.monitor.rldo_en_bot", 56.25, 100.807, 90.0, "0603"),
    "R142": ("bias_hb.monitor.rldo_en_top", 14.958, 94.195, 0.0, "0603"),
    "R143": ("bias_hb.monitor.rldo_en_bot", 15.07, 92.445, 180.0, "0603"),
    "R144": ("r_ref_wd_top", 112.4, 52.4, 180.0, "0603"),          # REF25 east, REF25_WD west (U3's old slot)
    "R145": ("r_ref_wd_bot", 112.4, 54.1, 0.0, "0603"),            # REF25_WD west, Kelvin east
    "R146": ("r_bias_good_j4", 33.0, 173.5, 270.0, "1206"),        # BIAS_GOOD north, BIAS_GOOD_J4 south (J4.1)
    # H2: BIAS_GOOD's branch to R146 changes layer at (68.463, 133.0), (60.6, 140.838) and (43.6, 153.238); one v3v3 -
    # selv_gnd transfer cap beside each (return_path19, <= 3.0 mm; poses from c44-selv-spine/scripts/cap_spots.py on the
    # s48 run-1 board, each pad on its own plane via 0.85 mm off). Pad 1 v3v3, pad 2 selv_gnd. The fourth change, at
    # (37.0, 172.0), sits 2.7 mm from C174.
    "C176": ("c_ref_xfer_13", 66.06, 133.4, 0.0, "0603"),
    "C177": ("c_ref_xfer_14", 61.7, 141.94, 90.0, "0603"),
    "C178": ("c_ref_xfer_15", 44.3, 152.14, 0.0, "0603"),
}
# Parts that leave their packed slots (place.py applies these after the HOT-protection pack, so no other part moves):
# U3 next to its output cap C26, where its EN divider fits; C48 (U14's VDD cap, now on HOT5) beside it.
S48_MOVES = {
    "U3": ("u_ldo", 118.3, 61.75, 0.0, "SOT23-5"),
    "C48": ("c_hot5_uv", 121.3, 61.9, 270.0, "0603"),
}

# Base copper stage 48 removes: (net, layer, first point) of whole s47 tracks, and vias (net, at).
S48_RM_TRACKS = [
    ("v15_ls", "F.Cu", (112.537, 52.195), (112.537, 54.095)),      # U3 EN tied to IN (the S19 loop)
    ("ocp_kelvin_p", "F.Cu", (112.537, 53.145), (110.729, 55.301)), # U3.2's Kelvin loop to its drop via
    ("v15_ls", "F.Cu", (109.522, 53.145), (112.537, 52.195)),      # U14.5 (VDD, now HOT5) to U3.1
    ("v15_ls", "F.Cu", (109.8, 53.2), (111.2, 54.4)),              # U14.5 to U3's IN via
    ("v15_ls", "In1.Cu", (111.2, 54.4), (109.0, 40.8)),            # U3's IN via stub (overlaps the trunk)
    ("v15_ls", "In1.Cu", (109.0, 40.8), (108.3, 63.2)),            # the x 108.9 detour round U3's IN via (re-laid below)
    ("v15_ls", "In2.Cu", (108.27, 63.4), (111.27, 57.4)),          # U3 IN feed, In2 leg
    ("v15_ls", "B.Cu", (111.27, 57.4), (111.07, 54.4)),            # U3 IN feed, B.Cu leg
    ("v15_ls", "F.Cu", (111.07, 54.4), (112.537, 52.195)),         # U3 IN feed, F.Cu leg
    ("ocp_kelvin_p", "F.Cu", "U14.4", (110.729, 55.301)),          # U14 INB- tied to ground (now the watchdog)
    ("ocp_kelvin_p", "F.Cu", (107.248, 53.145), (109.748, 55.1)),  # U14.2's ground diagonal (crosses pin 4, now REF25_WD)
    ("ocp_kelvin_p", "F.Cu", "C48.2", (118.865, 61.355)),          # C48's old ground drop
    ("ocp_kelvin_p", "F.Cu", (120.45, 57.635), (118.865, 61.355)), # C26.2 to C48's drop (crosses U3's new pads)
    ("v15_ls", "F.Cu", (115.84, 61.355), (116.284, 62.428)),       # C48.1's old V15_LS feed
    ("v15_ls", "In1.Cu", (115.8, 61.4), (116.284, 62.428)),
    ("v15_ls", "F.Cu", (108.858, 88.095), (102.07, 95.095)),       # U37 EN tied to IN (S19)
    ("v15_ls", "F.Cu", (108.858, 88.295), (110.457, 90.895)),
    ("v15_ls", "In1.Cu", (110.457, 90.895), (110.858, 85.295)),
    ("p_ha", "F.Cu", (59.858, 101.595), (59.843, 104.245)),        # U38 EN tied to IN
    ("p_hb", "F.Cu", (14.758, 97.845), (14.957, 95.845)),          # U39 EN tied to IN (the loop) ...
    ("p_hb", "F.Cu", (14.758, 97.845), (13.358, 99.245)),          # ... and its run to the In2 drop
]
S48_RM_VIAS = [("v15_ls", (111.2, 54.4)), ("v15_ls", (111.27, 57.4)), ("ocp_kelvin_p", (110.729, 55.301)),
               ("v15_ls", (116.284, 62.428)), ("ocp_kelvin_p", (118.865, 61.355)), ("v15_ls", (110.457, 90.895))]
# Copper stage 48 adds: (net, layer, width, points); vias (net, at), 0.6 / 0.3 mm.
S48_TRACKS = [
    # U14: OUTB (pin 6) joins OUTA (pin 1) under the body; VDD (pin 5) on HOT5 by the lane above U3's old slot; INB-
    # (pin 4) to the watchdog tap
    ("hot5_uv_raw", "F.Cu", 0.2, ["U14.6", "U14.1"]),
    ("hot5", "F.Cu", 0.25, ["U14.5", (110.55, 53.145), (110.55, 51.95), (110.95, 51.55), (116.0, 51.55), (116.2, 51.75),
                            (116.2, 52.2)]),
    ("ocp_kelvin_p", "F.Cu", 0.2, [(107.248, 53.145), (107.347, 53.1), (107.748, 53.1), (108.25, 53.602), (108.25, 54.75),
                                   (109.748, 55.1)]),                          # U14.2 to its drop via, west of pin 4
    ("ref25_wd", "F.Cu", 0.2, ["U14.4", "R145.1"]),
    ("ref25_wd", "F.Cu", 0.2, ["R144.2", "R145.1"]),
    ("ocp_kelvin_p", "F.Cu", 0.2, ["R145.2", (113.225, 54.65), (112.975, 54.9), (111.45, 54.9), (111.2, 55.15), (111.2, 55.4)]),
    # REF25 to the watchdog: In2 from U5's REF25 via east past the corridor, up the F.Cu lane west of the HOT5 riser
    ("ref25", "In2.Cu", 0.25, [(112.618, 57.635), (113.4, 56.853), (115.75, 56.853), (115.75, 56.85)]),
    ("ref25", "F.Cu", 0.2, [(115.75, 56.85), (115.75, 53.0), (115.15, 52.4), "R144.1"]),
    # V15_LS: the In1 run to (108.3, 63.2) straight off the x 109 trunk; U3's IN from the x 115.8 trunk
    ("v15_ls", "In1.Cu", 0.4, [(109.0, 60.0), (108.3, 60.7), (108.3, 63.2)]),
    ("v15_ls", "F.Cu", 0.4, [(115.85, 60.8), "U3.1"]),
    ("v15_ls", "F.Cu", 0.25, [(115.85, 60.8), (115.4, 61.25), (114.2, 61.25), (113.55, 61.85), "R136.1"]),
    # U3 ground, EN divider, output. U3.2 (GND, the DBV heat path) leaves 0.4 mm wide both ways: west to its Kelvin drop
    # via and east under the body (no pin opposite pin 2) to C48.2 and its drop via (120.25, 63.65): "heavier copper ...
    # plated through-holes to heat-dissipating layers" (SLVSCE6D 7.4.1.2). The B3 row read +0.2 K without it.
    ("ocp_kelvin_p", "F.Cu", 0.4, ["U3.2", (116.0, 61.75), (115.8, 61.95), (115.8, 62.3)]),
    ("ocp_kelvin_p", "F.Cu", 0.4, ["U3.2", (120.375, 61.75), "C48.2"]),   # 45 deg into C48.2: 92 deg to its via run
    ("ocp_kelvin_p", "F.Cu", 0.25, ["R137.2", (115.8, 62.275)]),     # level with the pad: no acute corner at the via
    ("hot5_en", "F.Cu", 0.2, ["U3.3", (116.45, 63.0), (116.2, 63.25), (115.525, 63.925), "R137.1"]),
    ("hot5_en", "F.Cu", 0.2, ["R137.1", "R136.2"]),
    ("hot5", "F.Cu", 0.3, [(120.6, 60.8), (120.6, 60.2), (120.0, 59.6)]),   # off the C48 run, not U3.5 (no 45 deg corner)
    ("hot5", "In2.Cu", 0.4, [(120.0, 59.6), (117.49, 59.6)]),
    ("hot5", "F.Cu", 0.4, ["U3.5", (120.6, 60.8)]),
    ("hot5", "F.Cu", 0.25, [(120.6, 60.8), (120.875, 61.075), "C48.1"]),
    ("ocp_kelvin_p", "F.Cu", 0.25, ["C48.2", (120.6, 63.425), (120.25, 63.65)]),
    # U37 / U38 / U39 EN dividers
    ("monitor_ls-ldo_en", "F.Cu", 0.2, ["U37.3", (108.983, 88.6), "R138.2"]),
    ("monitor_ls-ldo_en", "F.Cu", 0.2, ["R138.2", (109.746, 90.608), "R139.1"]),
    ("bias_ha.monitor-ldo_en", "F.Cu", 0.2, ["U38.3", (58.183, 101.595), "R140.2"]),
    ("bias_ha.monitor-ldo_en", "F.Cu", 0.2, ["R140.2", (57.7, 101.632), "R141.1"]),
    ("p_ha", "F.Cu", 0.25, ["R140.1", (58.5, 99.72), (59.058, 99.695)]),
    ("bias_hb.monitor-ldo_en", "F.Cu", 0.2, ["R143.1", (15.895, 97.4), (15.45, 97.845), "U39.3"]),
    ("p_hb", "F.Cu", 0.25, ["R142.1", (14.133, 94.878)]),
    # H2: BIAS_GOOD from U40's feed via (68.463, 133.0) to R146 (the router's stage-48 path, its last via moved beside
    # C174), BIAS_GOOD_J4 from R146 to J4.1, and the three transfer caps' plane-via stubs
    ("bias_good", "B.Cu", 0.25, [(68.463, 133.0), (68.2, 133.237), (60.6, 140.838)]),
    ("bias_good", "F.Cu", 0.25, [(60.6, 140.838), (48.2, 153.238), (43.6, 153.238)]),
    ("bias_good", "B.Cu", 0.25, [(43.6, 153.238), (43.6, 162.037), (37.0, 168.637), (37.0, 172.0)]),
    ("bias_good", "F.Cu", 0.25, [(37.0, 172.0), "R146.1"]),
    ("bias_good_j4", "F.Cu", 0.25, ["R146.2", (33.0, 177.363), (33.6, 177.963), (33.6, 178.363), (33.8, 178.562),
                                    (33.8, 179.162), (34.6, 179.963), "J4.1"]),
    ("v3v3", "F.Cu", 0.3, ["C176.1", (64.48, 133.1)]),
    ("selv_gnd", "F.Cu", 0.3, ["C176.2", (67.54, 132.9)]),
    ("v3v3", "F.Cu", 0.3, ["C177.1", (61.2, 143.41)]),
    ("selv_gnd", "F.Cu", 0.3, ["C177.2", (62.5, 140.86)]),
    ("v3v3", "F.Cu", 0.3, ["C178.1", (42.92, 151.54)]),
    ("selv_gnd", "F.Cu", 0.3, ["C178.2", (45.37, 151.34)]),
]
S48_VIAS = [("ocp_kelvin_p", (111.2, 55.4)), ("ref25", (115.75, 56.85)), ("v15_ls", (115.85, 60.8)),
            ("ocp_kelvin_p", (115.8, 62.3)), ("hot5", (120.0, 59.6)), ("ocp_kelvin_p", (120.25, 63.65)),
            ("bias_good", (60.6, 140.838)), ("bias_good", (43.6, 153.238)), ("bias_good", (37.0, 172.0)),
            ("v3v3", (64.48, 133.1)), ("selv_gnd", (67.54, 132.9)), ("v3v3", (61.2, 143.41)), ("selv_gnd", (62.5, 140.86)),
            ("v3v3", (42.92, 151.54)), ("selv_gnd", (45.37, 151.34))]
# bus_fault_hot leaves the strip U3 now stands in: from (118.6, 59.0) it runs at y 59.75 above U3's pads to (114.6, 60.4)
S48_BUS_FAULT_OLD = [(118.6, 59.0), (117.2, 60.4), (114.6, 60.4)]
S48_BUS_FAULT_NEW = [(118.6, 59.0), (117.85, 59.75), (115.25, 59.75), (114.6, 60.4)]


def edit_base48(base):
    """Stage 48 edit of a frozen base copper dict (in place); a no-op on a base that already carries it."""
    r3 = lambda q: q if isinstance(q, str) else (round(q[0], 3), round(q[1], 3))
    tr, vias = base["tracks"], base["vias"]
    if any(t["net"] == "ref25_wd" for t in tr):
        return 0

    def one(seq, what):
        if len(seq) != 1:
            raise SystemExit(f"stage 48: {what} not found once ({len(seq)})")
        return seq[0]
    for net, lay, first, last in S48_RM_TRACKS:
        tr.remove(one([t for t in tr if t["net"] == net and t["layer"] == lay and r3(t["points"][0]) == first
                       and r3(t["points"][-1]) == last], f"{net} {lay} track {first}..{last}"))
    for net, at in S48_RM_VIAS:
        vias.remove(one([v for v in vias if v["net"] == net and r3(v["at"]) == at], f"{net} via {at}"))
    # U3's OUT leaves the HOT5 run to U8: the run now starts at its (116.2, 52.2) tee
    t = one([t for t in tr if t["net"] == "hot5" and t["layer"] == "F.Cu" and r3(t["points"][0]) == (114.812, 52.195)],
            "hot5 U3.5 run")
    t["points"] = t["points"][2:]
    # the In1 V15_LS trunk fed C48.1's old via from (115.8, 61.4); it now ends on U3's IN via (115.85, 60.8)
    t = one([t for t in tr if t["net"] == "v15_ls" and t["layer"] == "In1.Cu" and r3(t["points"][-1]) == (115.8, 61.4)
             and r3(t["points"][-2]) == (115.8, 58.8)], "v15_ls In1 trunk to (115.8, 61.4)")
    t["points"][-1] = [115.85, 60.8]
    t = one([t for t in tr if t["net"] == "bus_fault_hot" and t["layer"] == "F.Cu"
             and S48_BUS_FAULT_OLD[0] in [r3(q) for q in t["points"]]], "bus_fault_hot run")
    p = [r3(q) for q in t["points"]]
    i = p.index(S48_BUS_FAULT_OLD[0])
    if p[i:i + 3] != S48_BUS_FAULT_OLD:
        raise SystemExit(f"stage 48: bus_fault_hot run not as frozen at {p[i:i + 3]}")
    t["points"] = t["points"][:i] + [list(q) for q in S48_BUS_FAULT_NEW] + t["points"][i + 3:]
    for net, lay, w, pts in S48_TRACKS:
        tr.append({"net": net, "layer": lay, "width": w, "points": [q if isinstance(q, str) else list(q) for q in pts]})
    for net, at in S48_VIAS:
        if any(math.dist(v["at"], at) < 0.6 for v in vias):
            raise SystemExit(f"stage 48: a via already sits at {at}")
        vias.append({"net": net, "at": list(at), "size": 0.6, "drill": 0.3})
    print(f"stage 48: {len(S48_RM_TRACKS)} base tracks and {len(S48_RM_VIAS)} vias removed (EN-to-IN ties, U3's and "
          f"C48's old copper), {len(S48_TRACKS)} tracks and {len(S48_VIAS)} vias added; bus_fault_hot re-laid above U3")
    return len(S48_TRACKS)


# Stage 49 (candidate 34, DECISIONS 68; c49-c34-bank): the resonant bank becomes 5 x TDK B32643B8104J000 (P22.5, 14.5 x
# 29.5 x 26.5 mm). RES_A pins stay at x 163.0; SW_B pins move 190.5 -> 185.5; rows y 53.2 / 68.2 / 83.2 / 98.2 / 113.2
# (place.py). The bank is joined by its B.Cu strips only (the R22.1 -> C21.1 res_a tap is pad to pad and C21.1 does not
# move), so the edit is outline-only plus one SELV run:
#  - sw_b strip: left edge x 188.0 -> 183.0 (1.3 mm left of the new pads, as before at 190.5), bottom y 112.9 -> 114.4 at
#    x 183-192 (the row-5 pad edge); x 192-200.6 keeps y 113.0 (line_zc_raw's corner at (203.87, 120.67) is 7.1 mm off a
#    y 114.4 corner there). KiCad's refill keeps the 8 mm HOT-SELV rule either way;
#  - res_a strip: bottom y 112.9 -> 114.6 at x 163-166 (0.2 mm past the row-5 pad, as before); x 161-163 keeps y 112.9,
#    the notch that holds the plan-view 8 mm to the In1 / In2 SELV planes' corner at (160.0, 122.2) (8.17 mm from
#    (163.0, 114.6); pass 1 with the whole x 161-166 at 114.6 read 7.71 mm). RES_A outer 12.6 mm to the y 127.5
#    line_zc_raw run holds (127.375 - 114.6 = 12.78 mm);
#  - line_zc_raw (SELV, B.Cu): the x 184.0-203.3 run moves from y 121.27 to y 122.75 (c34's slot study: >= 122.55), so
#    the row-5 SW_B pad keeps 8.225 mm (122.625 - 114.4). Its 45 deg legs stay on the same lines: (203.87, 120.67) ->
#    (201.79, 122.75) and (182.52, 122.75) -> (177.77, 127.5). No other copper on any layer within x 176-206, y 121-127
#    on s48 (nearest: the H8 NPTH, 5.5 mm). The run is outside the SELV-spine region (x 30-110, y 130-180).
S49_SWB_OLD = [[188.0, 50.0], [188.0, 112.9], [192.0, 112.9], [192.0, 113.0], [200.6, 113.0]]
S49_SWB_NEW = [[183.0, 50.0], [183.0, 114.4], [192.0, 114.4], [192.0, 113.0], [200.6, 113.0]]
S49_RESA_OLD = [[161.0, 114.0], [161.0, 112.9], [166.0, 112.9]]
S49_RESA_NEW = [[161.0, 114.0], [161.0, 112.9], [163.0, 112.9], [163.0, 114.6], [166.0, 114.6]]
S49_LZC_OLD = [(203.87, 120.67), (203.27, 121.27), (184.0, 121.27), (177.77, 127.5), (141.23, 127.5)]
# y 122.75, not c34's 122.55: the run sits 8.225 mm (edge to edge) below the SW_B column's last pad (C152.2, bottom
# y 114.4) instead of 8.025, so the HOT-SELV minimum stays s48's 8.047 mm (D5 must not fall); nearest other copper the
# H8 NPTH (5.5 mm)
# The y 127.5 run (x 141.2-177.8) dips to y 128.2 over x 157.7-171.3 (45 deg legs): the row-5 RES_A strip corner
# (163.0-166.0, 114.6) keeps 13.475 mm to it on B.Cu (was 12.775 on pass p3), so RES_A's outer minimum stays s48's
# 13.375 mm (the strip's y 114.0 edge west of x 161 to the y 127.5 run, unchanged). Nothing else on B.Cu within 3.7 mm
# of the dip; J6's PE pads (y 133.2) come to 4.88 mm (5.58 before), SELV to PE.
S49_LZC_NEW = [(203.87, 120.67), (201.79, 122.75), (182.52, 122.75), (177.77, 127.5), (172.0, 127.5), (171.3, 128.2),
               (157.7, 128.2), (157.0, 127.5), (141.23, 127.5)]


def edit_base49(base):
    """Stage 49 edit of a frozen base copper dict (in place); a no-op on a base that already carries it."""
    r3 = lambda q: q if isinstance(q, str) else (round(q[0], 3), round(q[1], 3))

    def splice(seq, old, new, what):
        pts = [r3(q) for q in seq]
        old_t = [r3(q) for q in old]
        hits = [i for i in range(len(pts) - len(old_t) + 1) if pts[i:i + len(old_t)] == old_t]
        if len(hits) != 1:
            raise SystemExit(f"stage 49: {what} not found once ({len(hits)})")
        i = hits[0]
        return seq[:i] + [list(q) for q in new] + seq[i + len(old_t):]
    zs = [z for z in base["zones"] if z["net"] == "sw_b" and z["layer"] == "B.Cu" and z.get("name") == "sw_b leg B-C21..C23"]
    za = [z for z in base["zones"] if z["net"] == "res_a" and z["layer"] == "B.Cu" and z.get("name") == "res_a J5-C21..C23"]
    if len(zs) != 1 or len(za) != 1:
        raise SystemExit(f"stage 49: bank strip zones not found once ({len(zs)}, {len(za)})")
    if any(r3(q) == (183.0, 114.4) for q in zs[0]["outline"]):
        return 0
    zs[0]["outline"] = splice(zs[0]["outline"], S49_SWB_OLD, S49_SWB_NEW, "sw_b strip outline")
    za[0]["outline"] = splice(za[0]["outline"], S49_RESA_OLD, S49_RESA_NEW, "res_a strip outline")
    t = [t for t in base["tracks"] if t["net"] == "line_zc_raw" and t["layer"] == "B.Cu"
         and (184.0, 121.27) in [r3(q) for q in t["points"]]]
    if len(t) != 1:
        raise SystemExit(f"stage 49: line_zc_raw B.Cu run at y 121.27 not found once ({len(t)})")
    t[0]["points"] = splice(t[0]["points"], S49_LZC_OLD, S49_LZC_NEW, "line_zc_raw y 121.27 run")
    print("stage 49: sw_b / res_a bank strips re-cut for the P22.5 bank (SW_B column x 185.5, rows to y 113.2); "
          "line_zc_raw x 182.5-201.8 run y 121.27 -> 122.75, x 157.7-171.3 y 127.5 -> 128.2")
    return 3


def add_stage33(g):
    """Six-layer phase A additions (no-op without image_planes): image pours, then their stitching vias."""
    if not IMAGE_PLANES:
        return
    add_stage33_images(g)
    add_stage33_stitch(g)
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
ZONE_WINNERS = [(PLANE_ROLE["n_ls"], "n_ls LS block", "ocp_kelvin_p protection"),
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
    # (stage 30: C137 / U33 are deleted; bias_ha.monitor-v5 now feeds U43 / C157 through the pair passes)
    route_group(g, [("bias_ha.monitor-spanuv", ROUTE4, (44.0, 78.0, 58.0, 116.0), 0.2, ["U30.9", "C78.1"]),
                    ("bias_hb.monitor-ov", ROUTE4, (0.6, 70.0, 20.0, 114.0), 0.2, ["U31.4", "C84.1"])])


def add_stage16(g):
    """Stage 16 (DECISIONS 16): the blower-supply mains tap. L_FILT from PS1.1 into F2, F2 out (BLW_L) to
    J11.1, N_FILT from PS1.2 to J11.2; 1.0 mm, since F2 (3.15 A T) rather than F1 protects this branch.
    The three groups (L_F, BLW_L, MAINS_N) keep 3.2 mm from each other; the router chooses layers."""
    from patches21_v1 import route_group
    # stage 28 (DECISIONS 30): F2 is the 1.5 kA UMT-H and the 0.15 ohm limiter R130 follows it (blw_l -> R130 -> blw_lr -> J11.1;
    # blw_lr shares blw_l's potential group); the box reaches the limiter at x 289
    box = (248.0, 108.0, 290.0, 140.0)
    route_group(g, [("l_filt", ROUTE4, box, 1.0, ["PS1.1", "F2.1"]),
                    ("blw_l", ROUTE4, box, 1.0, ["F2.2", "R130.1"]),
                    ("blw_lr", ROUTE4, box, 1.0, ["R130.2", "J11.1"]),
                    ("n_filt", ROUTE4, box, 1.0, ["PS1.2", "J11.2"])])



def add_stage27(g):
    """Stage 27 (DECISIONS 29): R1 / R2 moved 0.9 mm down with F1, so their base links (served by the moved pads) were
    dropped and the pair router cannot fit them in the 3.2 mm mains corner. Re-laid on their base geometry: l_f drops
    from F1's top block to R1.1, and R2.2's ac_n_in stub goes to the base via at (229.0, 25.0) and on B.Cu into the
    ac_n_in pour (both inside the moved bounded pad escapes, MOVE_ESCAPES)."""
    from patches21_v1 import put, drill
    put(g, "l_f", "F.Cu", 0.4, [224.54, 8.6], "R1.1", escape="xbleed_mid")
    drill(g, "ac_n_in", 229.0, 25.0, size=0.85)
    put(g, "ac_n_in", "F.Cu", 0.4, "R2.2", [229.0, 25.0], escape="xbleed_mid")
    put(g, "ac_n_in", "B.Cu", 0.6, [229.0, 25.0], [238.5, 25.0], [240.5, 26.8])


def add_stage28_ocp_lock(g):
    """Stage 28 (DECISIONS 30): the OCP comparator's node and threshold nets are laid from stage 27's copper
    (stage28_ocp_lock.json) instead of by the pair router. Stage 22's OCP pickup gain (4.78 -> 4.17 A) came from the router
    happening to lay ocp_thresh on F.Cu; the stage-28 passes routed both nets elsewhere and the pickup went back to 4.78 A,
    which the scorecard rejected. put() / drill() still check every item against the current copper."""
    import json
    from pathlib import Path
    from patches21_v1 import put, drill
    lock = json.loads((Path(__file__).with_name("stage28_ocp_lock.json")).read_text())
    for v in lock["vias"]:
        drill(g, v["net"], *v["at"], size=v["size"])
    for t in lock["tracks"]:
        put(g, t["net"], t["layer"], t["width"], *t["points"])


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
    route_group(g, [("hot5", ROUTE4, box49, 0.3, ["C49.1", "U15.5"]),
                    ("ocp_kelvin_p", ROUTE4, box49, 0.25, ["C49.2", "U15.3"])])   # (bias_hb_bad: deleted in stage 30)

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
    L4 = ROUTE4
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
    # pwm_hb's fixed vias first (stage 22: with Q4 / R16 gone, pwm_lb's F.Cu lane otherwise runs through (35.2, 125.0))
    put(g, "pwm_hb", "F.Cu", 0.3, "U2.1", [28.955, 55.875])
    drill(g, "pwm_hb", 28.955, 55.875, size=0.6)
    drill(g, "pwm_hb", 34.4, 110.6, size=0.6)
    drill(g, "pwm_hb", 35.2, 125.0, size=0.6)
    if not link("pwm_lb", ("F.Cu",), (20.0, 54.0, 70.0, 189.0), 0.3, ["U2.2", "J4.8"]):
        raise SystemExit("stage 19: pwm_lb F.Cu lane")
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
    L4 = ROUTE4
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
    route_group(g, [("bias_ha-en", ROUTE4, (57.0, 57.0, 68.0, 67.0), 0.25, ["U41.4", "R62.2", "R127.1"]),
                    ("bias_hb-en", ROUTE4, (11.0, 53.0, 22.0, 62.0), 0.25, ["U42.4", "R128.2", "R129.1"]),
                    ("v24_raw", ROUTE4, (52.0, 56.0, 67.0, 60.4), 0.3, ["C74.1", "C105.1", "C103.1"]),
                    ("p_ha", ROUTE4, (44.0, 34.0, 79.0, 92.0), 0.3, ["U41.28", "R92.1", "U30.3", "C104.1", "U1.16"]),
                    ("p_hb", ROUTE4, (0.6, 60.0, 20.0, 84.0), 0.3, ["U42.29", "R94.1", "U31.3"]),
                    ("n_ls", ROUTE4, (55.0, 56.0, 67.0, 66.0), 0.3, ["U41.1", "U41.5", "U41.8", "R127.2"]),
                    ("n_ls", ROUTE4, (8.0, 44.0, 22.0, 58.0), 0.3, ["C107.2", "U42.1"]),
                    ("n_ls", ROUTE4, (8.0, 40.0, 42.0, 54.0), 0.3, ["C107.2", "U2.9"]),
                    ("v24_raw", ROUTE4, (8.0, 50.0, 20.0, 58.5), 0.3, ["U42.7", "C81.1", "C106.1", "C109.1", "C107.1", "R128.1"]),
                    ("v24_raw", ROUTE4, (60.0, 56.0, 68.0, 63.0), 0.3, ["R62.1", "C103.1"]),
                    ("v24_raw", ROUTE4, (52.0, 56.5, 60.0, 60.0), 0.3, ["C102.1", "C74.1"]),
                    ("v24_raw", ROUTE4, (55.0, 56.5, 61.0, 62.2), 0.25, ["U41.7", "U41.6", "C74.1"]),
                    ("n_ha", ROUTE4, (44.0, 64.0, 66.0, 86.0), 0.3, ["U41.19", "U30.12"]),
                    ("bias_ha-fbm", ROUTE4, (55.0, 68.0, 64.0, 78.0), 0.2, ["U41.34", "U41.33", "R92.2", "R93.1", "C71.1"]),
                    ("sw_b", ROUTE4, (0.6, 40.0, 30.0, 95.0), 0.3, ["U20.2", "C95.1"])])


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
    drill(g, "ocp_kelvin_n", 119.95, 72.4)
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


def add_stage30_r91(g):
    """Stage 30: R91 (the LS monitor's pull-up) now ends on the GOOD node instead of the deleted notice transistor's
    collector. Its stage-29 escape (F stub, via, B.Cu column at x 118.35, all removed with monitor_ls-isoin) is
    re-laid on monitor_ls-good before anything else, as stage 8 laid ISOIN before the leg_ret / halfref hops round it;
    add_stage30 joins the column's top via to the GOOD node."""
    from patches21_v1 import put
    drill(g, "monitor_ls-good", 114.435, 110.535)
    put(g, "monitor_ls-good", "F.Cu", 0.25, "R91.2", [114.235, 109.735], [114.235, 110.335], [114.435, 110.535])
    put(g, "monitor_ls-good", "B.Cu", 0.25, [114.435, 110.535], [114.35, 110.345], [114.35, 109.345], [118.35, 105.345],
        [118.35, 92.745])
    drill(g, "monitor_ls-good", 118.35, 92.745)


def add_stage30(g):
    """Stage 30 (DECISIONS 33): the links the open-pair passes cannot close, because attach() searches 40 mm round a
    pad and these run 6-150 mm through set corridors. Each job is (net, layers, box, width, pads).
    HS-A: U43's HS pins (5 V, GOOD) back to the island's monitor LDO and comparator output, on F / In2 / B (In1 holds the
    n_ha plane), 3.2 mm clear of the LS pocket. LS: MON_GOOD_HA to the vote (D18, BAT54S pin 3) below U29 along the In1
    LS corridor (y 39-47), and ls_v5 to U43's side 2. U2.8's v3v3 drop via moves 0.4 mm (see REMOVE).
    HS-B: U44 (ISO7710F) is back on U34's stage-29 pose, so its supply / return copper is the stage-29 copper; only IN
    (pin 4, the monitor GOOD node) is new on the HS side. SELV: HSB_GOOD from U44.13 to U46.1 (static, push-pull: it takes
    the long run, the heartbeat legs stay short), U32.13 into U46 from the right (U46.3 sits above U46.2), BUS_FAULT_ISO
    from U9.13 to R134 (its base run ended on U13.1, now BUS_FAULT_FLT), and R40's ct_s2 stub to its B.Cu run."""
    from patches21_v1 import route_group, put, drill
    # U29.12 (LM339B GND) to the n_ls plane first: the GOOD node's new runs below U29 leave it one F escape, which the
    # passes otherwise hand to a monitor_ls-spanov via
    drill(g, "n_ls", 109.82, 78.355)
    put(g, "n_ls", "F.Cu", 0.2, "U29.12", [107.82, 78.955], [108.82, 77.955], [109.42, 77.955], [109.82, 78.355])
    drill(g, "v3v3", 37.7, 57.9)
    put(g, "v3v3", "F.Cu", 0.4, "U2.8", [37.445, 57.645], [37.7, 57.9])
    HS = tuple(lay for lay in ROUTE4 if lay != PLANE_ROLE["n_ha"])   # every routing layer but the high-side islands' plane
    L4 = ROUTE4
    route_group(g, [("hb_rx", ("F.Cu",), (92.5, 124.5, 99.0, 133.5), 0.25, ["U32.13", "U46.2"]),
                    ("bus_fault_iso", "F+B", (28.0, 118.0, 122.0, 140.0), 0.25, ["U9.13", "R134.1"]),
                    ("ct_s2", "F+B", (0.6, 126.0, 32.0, 146.0), 0.25, ["R40.2", "@18.183,139.695,B.Cu"])])
    route_group(g, [("bias_ha.monitor-v5", HS, (44.0, 64.0, 70.0, 104.0), 0.25, ["U43.1", "C157.1", "U38.5"]),
                    ("bias_ha.monitor-good", HS, (44.0, 64.0, 66.0, 90.0), 0.25, ["U43.3", "U30.1"]),
                    ("bias_hb.monitor-good", HS, (0.6, 36.0, 36.0, 118.0), 0.25, ["U44.4", "U31.1", "R124.2"])])
    route_group(g, [("ls_v5", L4, (24.0, 36.0, 60.0, 60.0), 0.25, ["U43.8", "C158.1"]),
                    ("mon_good_ha", L4, (40.0, 36.0, 112.0, 92.0), 0.25, ["U43.6", "D18.3"]),
                    ("monitor_ls-good", HS, (98.0, 74.0, 122.0, 114.0), 0.25, ["U29.14", "D18.1", "U45.1", "@118.35,92.745,*"])])
    # HB_TX (U45.4 -> R131.1 and U32.4): drops through U45.4's pad onto In1 to (106.45, 101.112), then B / In2 east
    # round the R91 column (add_stage30_r91) and back on In2 to U32. Laid before U45's VCC so pin 5 keeps the F
    # corridor to C132 (the passes otherwise take it for one of the two and strand the other).
    for v in [[96.45, 114.713], [98.85, 114.713], [101.25, 116.312], [103.45, 99.112], [106.45, 101.112], [106.925, 98.85], [112.45, 102.713], [115.65, 102.912], [119.05, 104.312]]:
        drill(g, "hb_tx", *v)
    for lay, w, a, b in [
            ("F.Cu", 0.25, [106.925, 98.25], [106.925, 98.85]),
            ("In1.Cu", 0.25, [104.85, 101.112], [106.45, 101.112]),
            ("In1.Cu", 0.25, [106.725, 100.85], [106.45, 101.112]),
            ("In1.Cu", 0.25, [103.45, 99.112], [103.45, 99.713]),
            ("In1.Cu", 0.25, [106.925, 100.65], [106.725, 100.85]),
            ("In1.Cu", 0.25, [106.925, 98.85], [106.925, 100.65]),
            ("In1.Cu", 0.25, [103.45, 99.713], [104.85, 101.112]),
            ("F.Cu", 0.2, [118.45, 103.713], [119.05, 104.312]),
            ("F.Cu", 0.2, [116.45, 103.713], [118.45, 103.713]),
            ("F.Cu", 0.2, [101.05, 116.112], [101.05, 115.912]),
            ("F.Cu", 0.2, [115.65, 102.912], [116.45, 103.713]),
            ("F.Cu", 0.2, [95.85, 115.312], [95.85, 115.912]),
            ("F.Cu", 0.2, [101.25, 116.312], [101.05, 116.112]),
            ("F.Cu", 0.2, [95.85, 115.912], [95.635, 116.125]),
            ("F.Cu", 0.2, [96.45, 114.713], [95.85, 115.312]),
            ("F.Cu", 0.2, [101.05, 115.912], [99.85, 114.713]),
            ("F.Cu", 0.2, [99.85, 114.713], [98.85, 114.713]),
            ("B.Cu", 0.2, [106.45, 101.112], [108.05, 102.713]),
            ("B.Cu", 0.2, [108.05, 102.713], [112.45, 102.713]),
            ("In2.Cu", 0.2, [112.85, 116.312], [101.25, 116.312]),
            ("In2.Cu", 0.2, [115.65, 104.112], [115.65, 102.912]),
            ("In2.Cu", 0.2, [117.65, 111.513], [112.85, 116.312]),
            ("In2.Cu", 0.2, [115.05, 104.713], [115.65, 104.112]),
            ("In2.Cu", 0.2, [117.65, 105.713], [117.65, 111.513]),
            ("In2.Cu", 0.2, [98.85, 114.713], [96.45, 114.713]),
            ("In2.Cu", 0.2, [114.45, 104.713], [115.05, 104.713]),
            ("In2.Cu", 0.2, [112.45, 102.713], [114.45, 104.713]),
            ("In2.Cu", 0.2, [119.05, 104.312], [117.65, 105.713]),
    ]:
        put(g, "hb_tx", lay, w, a, b)
    # U45's VCC (pin 5) to the LS 5 V at C132, F / B round the oscillator's RC (the passes do not close it)
    route_group(g, [("ls_v5", "F+B", (96.0, 92.0, 110.0, 104.0), 0.25, ["U45.5", "C132.1"])])
    # the oscillator's RC node: R131.2 straight down to C162.1 (1.6 mm F)
    route_group(g, [("hb_rc", ("F.Cu",), (106.0, 96.0, 111.0, 101.0), 0.25, ["R131.2", "C162.1"])])
    # bypass_check plane-backed return: C89 (U24's cap) lost the selv_gnd via the stage-29 passes had laid beside it.
    # (C161, U45's cap, has no n_ls pour on any layer under its pads, and vsense_in's In1 run and monitor_ls-ref's F run
    # wall it from the In1 n_ls fill; see bypass_check.py U45.)
    print("stage 30 plane via:", plane_via(g, "C89.2", reach=(0.85, 2.0)))
    # HSB_GOOD. U44's SELV pins sit in a pocket closed by the permit / PWM / bias_good bundle, which runs on both F and
    # B from leg B's driver (y 60) down x 32-36 and east along y 126-128, and by the 8 mm floor to HS-A (no via fits
    # between the bundles). The U12 / U13 links it would otherwise take are laid first; then one In2 leg (the
    # selv_gnd plane) passes under the bundle, where B.Cu carries only bias_good and permit (static, not asserted by
    # return_path19; the PWM lines on F keep In1), and F / B take it east to U46.
    route_group(g, [("bus_fault_flt", "F+B", (28.0, 124.0, 40.0, 138.0), 0.25, ["C167.1", "U13.1"]),
                    ("ct_s2", "F+B", (0.6, 124.0, 32.0, 146.0), 0.25, ["R40.2", "U12.4"]),
                    ("ct_sense_mon", "F+B", (18.0, 124.0, 142.0, 140.0), 0.25,
                     ["@26.907,130.695,F.Cu", "@124.935,130.195,F.Cu"])])
    drill(g, "hsb_good", 30.875, 109.765)
    put(g, "hsb_good", "F.Cu", 0.25, "U44.13", [30.875, 109.765])
    put(g, "hsb_good", "In2.Cu", 0.25, [30.875, 109.765], [31.1, 110.0], [34.1, 113.0], [34.1, 120.2], [41.9, 128.0],
        [43.7, 128.0], [44.5, 128.8], [44.5, 129.0])
    drill(g, "hsb_good", 44.5, 129.0)
    route_group(g, [("hsb_good", "F+B", (41.5, 124.0, 100.0, 142.0), 0.25, ["@44.5,129.0,*", "U46.1"])])


# Stage 32 (DECISIONS 35): slow SELV hops move from B.Cu to In2. In the SELV area F.Cu rides In1 (v3v3) and B.Cu rides
# In2 (selv_gnd), and B has no pour, so a line that ducks under an F run on B changes its reference at both vias, and
# return_path19 lists each change open when no v3v3-selv_gnd capacitor is within 3 mm. A hop on In2 rides In1 on both
# sides (In2 looks through the empty B to In1), so neither via is a reference change. Only short hops with no asserted
# signal on B above them move (the stage-30 HSB_GOOD In2 leg is the precedent); each In2 run is checked against the
# board (GEO) and skipped with a note if it does not fit. A via left joining In2 to In2 only is dropped.
S32_IN2_HOPS = [("hsb_good", [[44.5, 129.0], [49.2, 133.7]]),            # under bus_fault_iso / ct_s2 / ct_sense_mon (F)
                ("bus_fault_iso", [[39.025, 133.475], [36.025, 133.475]])]   # under pwm_lb (F, x 38.225)
# BIAS_GOOD's branch to U40.4 was left to the pair router, which dropped from the B.Cu trunk to F at (69.2, 127.0), back
# to B at (68.463, 128.6) to pass under the F bundle at y 130.9-132.1 and up again at (68.463, 133.0). Authored here on
# In2 from the trunk via: one via fewer, and the two vias at x 68.463 change no reference.
S32_BIAS_GOOD = [("via", [69.2, 127.0]), ("In2.Cu", [[69.2, 127.0], [68.463, 127.737], [68.463, 133.0]]),
                 ("via", [68.463, 133.0]), ("F.Cu", [[68.463, 133.0], [71.663, 133.0], [72.663, 132.0], "U40.4"])]


def add_stage32_in2(g):
    import math
    from shapely.geometry import LineString, Point
    geo = g["GEO"]

    def same(a, b):
        return all(not isinstance(q, str) and math.dist(q, p) < 0.01 for q, p in zip(a, b))

    def unregister(net, layers, geom):
        for lay in (*layers, "PLAN"):
            geo.items[lay] = [(gg, n) for gg, n in geo.items[lay]
                              if not (n == net and gg.symmetric_difference(geom).area < 1e-6)]
            geo._trees.pop(lay, None)

    for net, pts in S32_IN2_HOPS:
        t = next((t for t in g["TRACKS"] if t["net"] == net and t["layer"] == "B.Cu" and len(t["points"]) == 2
                  and (same(t["points"], pts) or same(t["points"], pts[::-1]))), None)
        if t is None:
            print(f"stage 32: {net} B hop {pts} not found, left as is")
            continue
        w = t["width"]
        geom = LineString(pts).buffer(w / 2, cap_style=1)
        bad = geo.conflicts(net, ("In2.Cu",), geom, limit=3)
        if bad:
            print(f"stage 32: {net} In2 hop {pts} blocked by {bad}, left on B")
            continue
        g["TRACKS"].remove(t)
        unregister(net, ("B.Cu",), geom)
        g["track"](net, "In2.Cu", w, *[list(p) for p in pts])
        dropped = []
        for p in pts:
            v = next((v for v in g["VIAS"] if v["net"] == net and math.dist(v["at"], p) < 0.01), None)
            if v is None:
                continue
            lays = {u["layer"] for u in g["TRACKS"] if u["net"] == net and any(
                not isinstance(q, str) and math.dist(q, p) < v["size"] / 2 for q in (u["points"][0], u["points"][-1]))}
            pad = any(q["net"] == net and q["box"][0] <= p[0] <= q["box"][2] and q["box"][1] <= p[1] <= q["box"][3]
                      for q in geo.pads)
            if lays == {"In2.Cu"} and not pad:
                g["VIAS"].remove(v)
                unregister(net, CU, Point(*v["at"]).buffer(v["size"] / 2))
                dropped.append(p)
        print(f"stage 32: {net} hop {pts} on In2" + (f", via(s) {dropped} dropped" if dropped else ""))
    pieces = [(Point(*a).buffer(0.3), CU) if k == "via" else
              (LineString([g["_xy"](q) for q in a]).buffer(0.125, cap_style=1), (k,)) for k, a in S32_BIAS_GOOD]
    bad = [c for geom, lays in pieces for c in geo.conflicts("bias_good", lays, geom, limit=3, via=lays == CU)]
    if bad:
        print(f"stage 32: bias_good In2 branch blocked by {bad}, left to the pair router")
        return
    for k, a in S32_BIAS_GOOD:
        if k == "via":
            g["via"]("bias_good", *a, size=0.6)
        else:
            g["track"]("bias_good", k, 0.25, *a)
    print("stage 32: bias_good branch to U40.4 on In2")


# Stage 33 (candidate 33 phase A, six layers; c33-six-layer/PHASE-A.md): image planes. The stack file's
# "image_planes" {net: layer} repeats each listed net's role-plane pours (same outline, holes and priority) on that
# layer: In4.Cu under B.Cu, so a B.Cu run sees the same reference net as an F.Cu run over In1 and an F <-> B via is a
# same-net stitch instead of a v3v3 / selv_gnd (or island-to-nothing) reference change. The image is protected
# against other nets' tracks (the router keeps In4 for the planes) but lets vias through, like the role plane. The
# four-layer stack has no image_planes, so this is a no-op on the board of record.
IMAGE_PLANES = {k: v for k, v in STACKUP.get("image_planes", {}).items() if not k.startswith("_")}
# return_path19.SIGNALS: asserted / reported fast nets -> their acceptable return nets
_KELVIN, _SELV, _LS = {"ocp_kelvin_p"}, {"v3v3", "selv_gnd"}, {"n_ls", "hv_ret", "leg_ret"}
S33_EXPECT = {**{n: _KELVIN for n in ("bus_fault_hot", "ocp_ok_hot", "hot5_ok_hot", "ovp_ok_hot")},
              **{n: _SELV for n in ("pwm_hb", "ct_zc", "pwm_ha", "pwm_la", "pwm_lb", "permit", "bus_fault_iso", "bus_fault",
                                    "bias_good", "line_zc", "hb_rx", "bus_fault_flt", "hsb_good")},
              "mon_good_ha": _LS}


def add_stage33_images(g):
    from shapely.geometry import Point, Polygon
    if not IMAGE_PLANES:
        return
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    geo = g["GEO"]
    new = []
    # An image must not become the reference of a signal that returns on another net: B.Cu / In3 runs of the
    # return-path-asserted nets (return_path19 SIGNALS) whose expected return is not the image's net keep the
    # four-layer reference there (the image is cut 1.0 mm round them). Stage-33 build 1: the n_ls image under
    # bus_fault_hot's B.Cu run (expects ocp_kelvin_p) failed SI1.
    def runs_over(lay, net):
        from layers21 import ADJ
        below = [l for l in CU if l != lay and lay in ADJ[l][:2]]   # layers for which the image is a near reference
        cut = []
        for t in g["TRACKS"]:
            exp = S33_EXPECT.get(t["net"])
            if exp is None or net in exp or t["layer"] not in below:
                continue
            pts = [g["_xy"](q) for q in t["points"]]
            cut.append(LineString(pts).buffer(t["width"] / 2 + 1.0) if len(pts) > 1 else None)
        return unary_union([c for c in cut if c is not None])
    for z in g["ZONES"]:
        lay = IMAGE_PLANES.get(z["net"])
        if lay is None or z["layer"] != PLANE_ROLE[z["net"]]:
            continue
        poly = Polygon(z["outline"], z["holes"]).buffer(0).difference(runs_over(lay, z["net"]))
        # a piece with no via or through-hole pad of its net inside would be an isolated island: dropped
        anchors = [Point(*v["at"]) for v in g["VIAS"] if v["net"] == z["net"]] + \
                  [Point(q["x"], q["y"]) for q in geo.pads if q["net"] == z["net"] and q["tht"]]
        parts = [p for p in getattr(poly, "geoms", [poly]) if p.area > 4.0 and any(p.buffer(-0.4).contains(a) for a in anchors)]
        for k, p in enumerate(parts):
            p = p.simplify(0.02)
            img = dict(z, layer=lay, name=f"{z.get('name', z['net'])} ({lay.split('.')[0]} image{'' if len(parts) == 1 else f' {k + 1}'})",
                       outline=[list(c) for c in p.exterior.coords[:-1]],
                       holes=[[list(c) for c in r.coords[:-1]] for r in p.interiors])
            new.append(img)
            geo.protect(z["net"], lay, p, via_ok=True)
    g["ZONES"].extend(new)
    # the role layer's declared pour winners hold on the image layer too (every piece of a cut image)
    names = {}
    for z in new:
        base_name = z["name"].rsplit(" (", 1)[0]
        names.setdefault((z["layer"], base_name), []).append(z["name"])
    for lay0, w, l_ in list(ZONE_WINNERS):
        if lay0 not in PLANE_ROLE.values():
            continue
        for net_lay in set(IMAGE_PLANES.values()):
            for wn in names.get((net_lay, w), []):
                for ln in names.get((net_lay, l_), []):
                    ZONE_WINNERS.append((net_lay, wn, ln))
    print(f"stage 33: {len(new)} image pours: " + ", ".join(sorted(f"{z['net']} {z['layer']}" for z in new)))


# Stage 33: with In4 imaging In1, an F.Cu <-> B.Cu signal via no longer changes reference net (v3v3 -> selv_gnd, or an
# island net -> nothing); it changes reference LAYER, In1 -> In4, of the same net. The return then crosses on the
# nearest via of that net, so return_path19 (stage 33) counts the change closed only with one within 3.0 mm. These are
# the changes the stage-32 copper left farther than that (c33-six-layer/layer_plan_screen.py, plan 6L-A; refreshed
# from the six-layer build's return-path.json): each gets a plain stitching via of the reference net at the nearest
# legal spot inside that net's role-plane outline, 0.8-2.8 mm from the signal via. A via in both pours needs no track.
S33_STITCH = [("v3v3", (38.955, 127.075)),   # pwm_hb
              ("v3v3", (35.2, 125.0)),       # pwm_hb (build 1: 3.45 mm)
              ("v3v3", (28.955, 55.875), 2.0),   # pwm_hb (2.95 mm: under stage 32's worst asserted 2.72 mm)
              ("v3v3", (26.907, 128.795)),   # ct_zc
              ("v3v3", (75.9, 56.275)),      # pwm_ha
              ("v3v3", (76.825, 56.075)),    # pwm_la
              ("v3v3", (70.0, 127.8)),       # permit
              ("v3v3", (36.5, 178.6)),       # permit
              ("v3v3", (113.298, 125.875)),  # bus_fault_iso
              ("v3v3", (74.0, 123.4)),       # bias_good
              ("v3v3", (33.2, 70.4)),        # bias_good
              ("ocp_kelvin_p", (114.448, 55.695))]   # ovp_ok_hot


def add_stage33_stitch(g):
    import math
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    if not IMAGE_PLANES:
        return
    geo = g["GEO"]
    done = []
    for net, (cx, cy), *keep in S33_STITCH:     # keep: an existing via this close already counts (default 2.8 mm)
        if net not in IMAGE_PLANES:
            continue
        plane = unary_union([Polygon(z["outline"], z["holes"]).buffer(0) for z in g["ZONES"]
                             if z["net"] == net and z["layer"] == PLANE_ROLE[net]]).buffer(-0.6)
        have = [v for v in g["VIAS"] if v["net"] == net and math.dist(v["at"], (cx, cy)) <= (keep[0] if keep else 2.8)]
        if have:
            done.append(f"{net} ({cx}, {cy}) has one at {min(math.dist(v['at'], (cx, cy)) for v in have):.2f}")
            continue
        spot = None
        for r in [0.8 + 0.2 * k for k in range(11)] + [2.95]:     # the gate's limit is 3.0 mm
            for a in range(24):
                x, y = round(cx + r * math.cos(a * math.pi / 12), 3), round(cy + r * math.sin(a * math.pi / 12), 3)
                if plane.contains(Point(x, y)) and not geo.conflicts(net, CU, Point(x, y).buffer(0.3), limit=1, via=True):
                    spot = (x, y)
                    break
            if spot:
                break
        if spot is None:
            done.append(f"{net} ({cx}, {cy}) NO legal spot within 2.8 mm")
            continue
        drill(g, net, *spot)
        done.append(f"{net} ({cx}, {cy}) -> {spot} {math.dist(spot, (cx, cy)):.2f} mm")
    print("stage 33 stitch vias: " + "; ".join(done))



# Stage 40 (candidate 30a): HS-B's verdict crosses to LS on an ISO6721FB link (U44) as HS-A's does on U43, instead of
# to SELV on the ISO7710F. U44 sits in the north-west corner of U42's n_ls pocket (place.py STAGE40), HS-B row north,
# LS row south. The HS-B side reaches the island down the B.Cu lane sw_b already takes past the pocket (east of it,
# 0.7 / 1.375 mm off its centre line), the LS side joins the In1 LS corridor (y 38.5-47) south of the v24_raw lane.
# The pocket's two joints to that corridor are re-laid on In1 so the HS-B lane has room: the n_ls trunk drops
# straight into the pocket's In1 pour (its F diagonal and the via at (9.8, 44.6) go), and v24_raw turns south at
# x 11.2 instead of 8.0. The via at (15.4, 50.1) (C107 / C109 / R129's n_ls to the In1 pour) goes too: that cluster
# keeps its F joint to the pocket through C109 / C81 / C106.
S40_OPEN_IN1 = [(9.0, 46.0, 13.5, 48.6),      # incr21: the LS lanes cross the HV_RET plane's y 47-48 band here
                (50.4, 46.0, 52.2, 47.4),     # and MON_GOOD_HB steps out of ls_v5's way to its via beside the vote,
                (56.4, 46.0, 58.0, 47.8)]     # and GOOD's In1 lane steps down to its via
S40_SW_B_INNER = [[5.155, 41.5], [5.155, 40.6], [5.655, 40.1], [8.5, 40.1], [8.9, 40.5], [8.9, 47.922], [14.288, 53.31],
                  [14.288, 57.09], [10.078, 61.3]]       # 0.7 mm off sw_b's centre line (east / south side)
S40_GOOD_IN1 = [[57.1, 46.9], [57.4, 46.6], [63.4, 46.6], [63.8, 46.2], [81.2, 46.2], [81.8, 46.8], [88.0, 46.8], [90.0, 48.8],
                [90.2, 48.8], [99.0, 57.6], [99.0, 75.8], [98.6, 76.2], [98.6, 85.2], [101.0, 87.6],
                [101.0, 88.2], [101.7, 88.9]]   # MON_GOOD_HA's s38 lane, its In1 -> F change moved onto the LS-block plane
S40_STITCH = [(56.0, 47.1), (51.0, 47.5),    # n_ls stitches in the vote area (beside GOOD's and MON_GOOD_HB's vias)
              (102.8, 89.1)]                 # and beside GOOD's change in the LS block
S40_SW_B_OUTER = [[3.25, 43.25], [3.25, 39.825], [3.65, 39.425], [9.175, 39.425], [9.575, 39.825], [9.575, 47.642], [14.963, 53.03],
                  [14.963, 57.37], [9.733, 62.6]]        # 1.375 mm off it


def merge_zone(g, net, layer, rect, name, priority=1, clip=True, selv_mm=None):
    """g["zone"], but a pour that overlaps a same-net pour on the layer (same priority) is merged into it (KiCad flags
    overlapping same-priority zones; one outline also keeps the fill whole), and the outline keeps its clearance from
    other nets' pours on the layer (zone_priority_gate: no contested copper). Stage 40."""
    import rules21
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    Z = g["ZONES"]
    n0 = len(Z)
    g["zone"](net, layer, rect, name=name, priority=priority)
    new, Z[n0:] = Z[n0:], []
    keep = [Polygon(o["outline"], o["holes"]).buffer(rules21.clearance(net, o["net"]) + 0.05)
            for o in Z if o["layer"] == layer and o["net"] != net] if clip else []
    if selv_mm:      # a HOT pour near SELV pours: keep selv_mm (plan view) from every SELV / PE pour outline
        keep += [Polygon(o["outline"], o["holes"]).buffer(selv_mm) for o in Z if rules21.domain(o["net"]) in ("SELV", "PE")]
    keep = unary_union(keep) if keep else None
    for z in new:
        shape, names = Polygon(z["outline"], z["holes"]), [z["name"]]
        if keep is not None:
            shape = shape.difference(keep)
            if shape.is_empty:
                continue
            shape = max(getattr(shape, "geoms", [shape]), key=lambda q: q.area)
        for k in range(len(Z) - 1, -1, -1):
            o = Z[k]
            if (o["net"], o["layer"], o.get("priority", 1)) == (net, layer, z["priority"]):
                po = Polygon(o["outline"], o["holes"])
                if po.intersects(shape):
                    shape, names = unary_union([po, shape]), [o.get("name", "")] + names
                    del Z[k]
        for poly in getattr(shape, "geoms", [shape]):
            poly = poly.simplify(0.001)
            Z.append({**z, "name": " + ".join(dict.fromkeys(names)),
                      "outline": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
                      "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in poly.interiors]})


def add_stage40(g):
    """Stage 40 (candidate 30): the HS-B link U44 (ISO6721FB) in U42's pocket, the pocket copper it needs, and C161's
    n_ls plane (30b). Runs on the frozen s38 base after incr21's prune step (INCR21_PRUNE)."""
    from patches21_v1 import put, route_group
    r = lambda q: q if isinstance(q, str) else [round(v, 3) for v in q]
    has = lambda t, q: any(not isinstance(p, str) and r(p) == q for p in t["points"])
    # ---- the pocket's corridor joints, re-laid on In1
    n = rip(g, "n_ls", lambda it: ("at" in it and r(it["at"]) in ([9.8, 44.6], [15.4, 50.1])) or
            ("points" in it and it["layer"] == "F.Cu" and has(it, [9.8, 44.6])) or
            ("points" in it and it["layer"] == "F.Cu" and r(it["points"][0]) == [15.325, 50.025] and len(it["points"]) == 2) or
            ("points" in it and it["layer"] == "In1.Cu" and (has(it, [15.4, 50.1]) or has(it, [15.325, 50.025]) or
                                                              has(it, [9.725, 55.425]) or has(it, [9.8, 55.3]))))
    n += rip(g, "v24_raw", lambda it: "points" in it and it["layer"] == "In1.Cu" and has(it, [8.0, 45.5]))
    put(g, "n_ls", "F.Cu", 0.3, [17.8, 50.175], [17.6, 50.2], [15.6, 50.2], [14.9, 50.9], [14.9, 51.5])   # C107 / R129 to C109.2
    put(g, "n_ls", "In1.Cu", 0.3, [9.8, 44.6], [9.8, 48.4])
    put(g, "v24_raw", "In1.Cu", 0.4, [54.6, 45.5], [11.6, 45.5], [11.2, 45.9], [11.2, 48.6], [7.0, 52.8], [7.0, 53.1])
    # ---- C160 (U44 VCC2) below the LS row: two of the pocket's 18 stitch vias and C106's F stub to one of them go
    n += rip(g, "n_ls", lambda it: ("at" in it and r(it["at"]) in ([3.4, 52.0], [5.0, 52.0])) or
             ("points" in it and it["layer"] == "F.Cu" and has(it, [5.2, 51.725])))
    print(f"stage 40: {n} base items ripped round U42's pocket")
    merge_zone(g, "n_ls", "F.Cu", (0.8, 48.2, 11.1, 51.0), "n_ls U44 LS side (stage 40)")
    put(g, "n_ls", "F.Cu", 0.3, "U44.5", [1.345, 51.07], "C160.2")
    put(g, "n_ls", "F.Cu", 0.3, "U44.7", [3.885, 51.1])
    drill(g, "n_ls", 3.885, 51.1)
    put(g, "ls_v5", "F.Cu", 0.25, "U44.8", [5.155, 52.2], [6.0, 52.2])
    put(g, "ls_v5", "F.Cu", 0.25, "C160.1", [5.155, 52.2])
    drill(g, "ls_v5", 6.0, 52.2)
    put(g, "mon_good_hb", "F.Cu", 0.25, "U44.6", [2.615, 51.15])
    drill(g, "mon_good_hb", 2.615, 51.15)
    # LS lanes: south of the v24_raw via, east under the pocket, north at x 12.3 / 12.8, east at y 46.1 / 46.6 (between
    # v24_raw and the HV_RET plane, which the In1 corridor opens to y 47)
    put(g, "ls_v5", "In1.Cu", 0.25, [6.0, 52.2], [6.0, 53.5], [6.4, 53.9], [11.9, 53.9], [12.3, 53.5], [12.3, 46.5],
        [12.7, 46.1], [20.0, 46.1])
    put(g, "mon_good_hb", "In1.Cu", 0.25, [2.615, 51.15], [2.615, 54.0], [3.015, 54.4], [12.4, 54.4], [12.8, 54.0],
        [12.8, 47.0], [13.2, 46.6], [20.0, 46.6])
    # ---- HS-B side: C159 between pins 1 / 4, GOOD by a via between C159 and the row, n_hb into a B pour that joins
    # the n_hb bank at x 12
    put(g, "bias_hb.monitor-v5", "F.Cu", 0.25, "U44.1", [5.155, 42.2], "C159.1")
    put(g, "bias_hb.monitor-v5", "F.Cu", 0.25, [5.155, 42.2], [5.155, 41.5])
    drill(g, "bias_hb.monitor-v5", 5.155, 41.5)
    put(g, "bias_hb.monitor-good", "F.Cu", 0.25, "U44.3", [2.615, 43.6], [3.25, 43.25])
    drill(g, "bias_hb.monitor-good", 3.25, 43.25)
    put(g, "n_hb", "F.Cu", 0.3, "U44.4", [1.345, 42.2], "C159.2")
    put(g, "n_hb", "F.Cu", 0.3, [1.345, 42.2], [1.345, 41.4])
    drill(g, "n_hb", 1.345, 41.4)
    # the two lanes beside sw_b's B run past the pocket, then In2 into the island (south of U42's LS row by 3.5 mm)
    put(g, "bias_hb.monitor-v5", "B.Cu", 0.25, *S40_SW_B_INNER)
    drill(g, "bias_hb.monitor-v5", *S40_SW_B_INNER[-1])
    put(g, "bias_hb.monitor-good", "B.Cu", 0.25, *S40_SW_B_OUTER)
    drill(g, "bias_hb.monitor-good", *S40_SW_B_OUTER[-1])
    merge_zone(g, "n_hb", "B.Cu", (0.8, 37.0, 12.4, 44.5), "n_hb U44 HS-B side (stage 40)")
    # ---- R135 (U46.1's pull-up) on the old SELV pocket's vias. The old U44's SELV stubs: incr21 keeps SELV copper
    # (C47.2 still reaches its selv_gnd via through U44.9's old land) and drops what meets R135's pads; the two runs
    # left ending in the open go here.
    n = rip(g, "v3v3", lambda it: "points" in it and it["layer"] == "F.Cu" and has(it, [32.9, 109.275]))
    n += rip(g, "selv_gnd", lambda it: "points" in it and it["layer"] == "B.Cu" and has(it, [32.475, 108.045]))
    print(f"stage 40: {n} old U44 SELV stubs ripped")
    put(g, "v3v3", "F.Cu", 0.25, "R135.1", [32.5, 109.675])
    put(g, "hsb_good", "F.Cu", 0.25, "R135.2", [30.875, 109.765])
    # C168 (pwm_hb's fifth transfer cap, 2.6 mm from its via at (34.4, 110.6)): v3v3 to R135's plane via, selv_gnd to
    # the plane via C47 already uses at the old U44.9 land
    put(g, "v3v3", "F.Cu", 0.3, "C168.1", [32.5, 109.675])
    put(g, "selv_gnd", "F.Cu", 0.3, "C168.2", [31.85, 112.1], [30.475, 113.475], [30.475, 114.045])
    # ---- the long runs
    HS = ("F.Cu", "In2.Cu", "B.Cu")
    route_group(g, [("bias_hb.monitor-v5", HS, (0.6, 58.0, 24.0, 118.0), 0.25,
                     ["@10.078,61.3,In2.Cu", "@1.6,95.035,In2.Cu", "U39.5"]),   # (C140.1 - R124.1: s38 copper)
                    ("bias_hb.monitor-good", HS, (0.6, 58.0, 24.0, 118.0), 0.25,
                     ["@9.733,62.6,In2.Cu", "U31.13", "R124.2"])])
    # ---- the vote beside U43 (place.py STAGE40). The LS corridor east of x 55 holds one lane south of v24_raw, so the
    # GOOD node takes MON_GOOD_HA's old lane to the LS block and both verdict lines end at the diodes (D18 / D20).
    # MON_GOOD_HA keeps its s38 U43.6 stub (incr21's prune took the rest: D18 moved) and its s38 path, re-laid: via
    # (48.0, 63.4), B.Cu to (55.6, 49.8), F.Cu to D18.3
    vias = {(v["net"], tuple(r(v["at"]))) for v in g["VIAS"]}
    for xy in ((48.0, 63.4), (55.6, 49.8)):
        if ("mon_good_ha", xy) not in vias:
            drill(g, "mon_good_ha", *xy)
    put(g, "mon_good_ha", "B.Cu", 0.25, [48.0, 63.4], [48.0, 63.2], [49.0, 62.2], [49.0, 56.4], [55.6, 49.8])
    put(g, "mon_good_ha", "F.Cu", 0.25, [55.6, 49.8], [56.9, 49.8], "D18.3")
    # MON_GOOD_HB: the pocket lane east, stepping out of ls_v5's way at (51.6, 46.9), F to D20.2
    put(g, "mon_good_hb", "In1.Cu", 0.25, [20.0, 46.6], [51.3, 46.6], [51.6, 46.9])
    drill(g, "mon_good_hb", 51.6, 46.9)
    put(g, "mon_good_hb", "F.Cu", 0.25, [51.6, 46.9], [52.8, 48.1], "D20.2")
    # ls_v5: the pocket lane to (52.6, 46.3), F past v24_raw's branch to the via on its B.Cu run at x 55.075
    put(g, "ls_v5", "In1.Cu", 0.25, [20.0, 46.1], [52.4, 46.1], [52.6, 46.3])
    drill(g, "ls_v5", 52.6, 46.3)
    put(g, "ls_v5", "F.Cu", 0.25, [52.6, 46.3], [53.4, 46.3], [54.6, 47.5], [55.075, 47.5])
    drill(g, "ls_v5", 55.075, 47.5)
    # GOOD: D20.3 - D18.1, then MON_GOOD_HA's old corridor lane to the LS block and the node's via at (106.438, 87.6)
    put(g, "monitor_ls-good", "F.Cu", 0.25, "D20.3", [54.35, 53.05], [57.8, 53.05], [58.3, 52.55], "D18.1")
    put(g, "monitor_ls-good", "F.Cu", 0.25, "D18.1", [58.3, 47.5], [57.7, 46.9], [57.1, 46.9])
    drill(g, "monitor_ls-good", 57.1, 46.9)     # (south-west of MON_GOOD_HA's s38 via: on the vote's F / In1 n_ls pours)
    put(g, "monitor_ls-good", "In1.Cu", 0.25, *S40_GOOD_IN1)
    drill(g, "monitor_ls-good", 101.7, 88.9)
    put(g, "monitor_ls-good", "F.Cu", 0.25, [101.7, 88.9], [102.4, 88.2], [105.838, 88.2], [106.438, 87.6])
    if not any(v["net"] == "monitor_ls-good" and [round(c, 3) for c in v["at"]] == [106.438, 87.6] for v in g["VIAS"]):
        drill(g, "monitor_ls-good", 106.438, 87.6)     # the node's via to its B.Cu run (incr21 took it with D18's old stub)
    # ---- return paths (return_path19 LS_REF). Beside the vote: an F n_ls pour over an In1 n_ls patch, stitched by n_ls
    # vias (S40_STITCH)
    merge_zone(g, "n_ls", "F.Cu", (50.0, 45.6, 58.4, 54.6), "n_ls vote (stage 40)")   # x 58.4: TP30 (sw_a) keeps its F spot
    # In1 under the vote: no plane of any net fills there (the hv_ret trunk's outline reaches in, unfilled); an n_ls
    # patch (priority over that outline) references the vote's F and B runs on In1
    merge_zone(g, "n_ls", "In1.Cu", (50.0, 47.25, 59.4, 54.6), "n_ls vote inner (stage 40)", priority=2, clip=False)
    merge_zone(g, "n_ls", "In1.Cu", (53.0, 46.0, 59.4, 47.25), "n_ls vote inner (stage 40)", priority=2, clip=False)
    # MON_GOOD_HA's F -> B change at (48.0, 63.4) beside U43: U41's F / B heat-spread pours reach west under it
    merge_zone(g, "n_ls", "F.Cu", (46.35, 60.6, 50.0, 64.5), "n_ls U43 LS row (stage 40)")   # x 46.35: 8 mm from the SELV planes
    merge_zone(g, "n_ls", "B.Cu", (46.35, 60.6, 50.0, 64.6), "n_ls U43 LS row (stage 40)")
    # the GOOD node's In1 -> F change (MON_GOOD_HA's at (101.0, 87.6) in s38, In1 plane on 6 of 16 ring points) moves to
    # (101.7, 88.9) on the In1 LS-block plane; an F n_ls patch, stitched, references its In1 side
    merge_zone(g, "n_ls", "F.Cu", (100.0, 87.0, 104.0, 91.0), "n_ls GOOD change (stage 40)")
    # 30b: C161 sits in a pocket that monitor_ls-ref (F), vsense_in (In1), ocp_kelvin_p (In2) and bus_fault_hot (B) wall off
    # at x ~100.3-100.8. The In1 n_ls LS-block plane reaches into it under bus_fault_hot's x 100.35 run, where In2's
    # ocp_kelvin_p run lies directly under that line (SI1 counts it coupled), and round C161's n_ls via (99.5, 95.035).
    # North of y 90.75 it stays off: bus_fault_hot's x 99.05 run and its jog have no Kelvin track under them.
    # (8.2 mm plan view from the SELV pours: the first build put its south-west corner 8.042 mm from selv_gnd's In2 fill)
    merge_zone(g, "n_ls", "In1.Cu", (97.9, 90.75, 100.8, 97.4), "n_ls LS block west (stage 40)", priority=2, selv_mm=8.2)
    for xy in S40_STITCH:
        drill(g, "n_ls", *xy)
    # (the GOOD node's B -> F change into U45.1 at (104.4, 99.65) stays open: it sits in an In1 island hb_rc / hb_tx's
    # In1 runs close off, monitor_ls-uv's In2 run passes 0.7 mm from it, and no legal spot for the via is on a plane)
