"""Hand fixes applied by incr21.py on top of the frozen base copper (copper_base.json).

REMOVE: base items to drop, {"net", ["box": [x0, y0, x1, y1]], ["kind": "track" | "via"],
["layer"]} (every point inside the box; no box = the whole net). add(g): new explicit copper,
with route21's helpers in g (track, via, link, zone, ESCAPES, GEO, ...), applied before the
open pairs are routed. put()/drill() refuse illegal copper loudly.
"""
from shapely.geometry import LineString, Point, Polygon, box

CU = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")

# U34 (leg-B monitor isolator): its SELV pins 16 / 14 / 9 had no room for plane vias because the
# SELV long runs (PWM_HB on F, PERMIT and BIAS_*_BAD on B) were laid first, hugging the pin row.
# Drop those runs, drill the pin vias, re-lay the runs around them.
REMOVE = [{"net": "pwm_hb"}, {"net": "permit"}, {"net": "bias_ha_bad"}, {"net": "bias_hb_bad"}]
# U2 / U23 pocket: the leg-B disable and dead-time nets and BIAS_BAD are short pin-to-pin runs at
# the pocket's left edge (the 8 mm barrier line); lay them before the long runs reclaim the edge.
REMOVE += [{"net": "leg_b-dis"}, {"net": "leg_b.driver-dt"}, {"net": "bias_bad"}]

# LINE_ZC string re-folded (place.py): each LED node beside its opto pin. L_FILT now feeds r1
# (R67) from below off the PS1 diagonal; its F-to-B via moves up to y 89 clear of R69.1 (LED2);
# N_FILT feeds r4 (R70) from above with a B spur off its x 237.5 run.
REMOVE += [{"net": "l_filt", "box": [229.9, 59.9, 230.1, 92.6], "layer": "F.Cu"},
           {"net": "l_filt", "box": [229.9, 92.4, 230.6, 107.1], "layer": "B.Cu"},
           {"net": "l_filt", "box": [229.9, 92.4, 230.1, 92.6], "kind": "via"},
           {"net": "n_filt", "box": [243.4, 106.9, 243.6, 107.1], "kind": "via"},
           {"net": "n_filt", "box": [243.4, 106.9, 243.6, 107.1], "layer": "F.Cu"},
           {"net": "n_filt", "box": [237.4, 106.9, 243.6, 107.1], "layer": "B.Cu"}]
# SELV reference planes (In1 V3V3, In2 SELV_GND) were sliced into strips, and the pocket columns
# under the isolators cut off the band, by long SELV signals the router had put on In1 / In2
# along the band (> 600 mm in all). Those nets go back to F / B; inner layers stay planes.
SELV_OUTER = {"v15_selv": ["PS1.4", "J4.1"], "line_zc-raw": ["U36.4", "R125.2", "U24.2"],
              "ct_sense_mon": ["U10.3", "R42.2", "D4.2", "D5.1", "R47.1", "U12.3", "U11.4"],
              "bus_fault_iso": ["U9.13", "U13.1"], "bias_bad_raw": ["U25.4", "R126.1"],
              "bias_bad_flt": ["R126.2", "C143.1", "U40.2"], "bias_ls_bad": ["U25.1", "U32.13"]}
REMOVE += [{"net": n} for n in SELV_OUTER]
HANDLED = ("led1", "led2")     # joined explicitly below
REMOVE_ESCAPES = [("R67", "1"), ("R67", "2"), ("R68", "1"), ("R69", "2"), ("R70", "1"), ("R70", "2")]


# SELV spur under PS1 / the LINE_ZC opto: the In1 HV_RET and In2 BUS_P planes were poured before
# the spur, clearing only the SELV pads, so the spur's top (U36 pins 3/4) was pinched shut. Cut
# the whole spur plus the barrier out of those planes and re-pour the spur's SELV planes.
SPUR = (205.0, 92.8, 216.8, 139.4)


def edit_zones(zones):
    import rules21
    cut = box(*SPUR).buffer(rules21.BARRIER + 0.2, join_style=2)
    out = []
    for z in zones:
        poly = Polygon(z["outline"], z["holes"])
        if z["net"] in ("v3v3", "selv_gnd") and poly.intersects(box(*SPUR)):
            rest = poly.difference(box(*SPUR))      # re-poured by add()
        elif z["net"] in ("hv_ret", "bus_p") and z["layer"] in ("In1.Cu", "In2.Cu") and poly.intersects(cut):
            rest = poly.difference(cut)
        else:
            out.append(z)
            continue
        for q in getattr(rest, "geoms", [rest]):
            if q.area < 1.0:
                continue
            q = q.simplify(0.001)
            out.append({**z, "outline": [[round(x, 3), round(y, 3)] for x, y in list(q.exterior.coords)[:-1]],
                        "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in q.interiors]})
    return out


def put(g, net, layer, width, *pts, escape=None):
    """escape: the partner net of a bounded pad escape (its pad may sit closer, per the DRU rule)."""
    xy = [g["_xy"](p) for p in pts]
    bad = [c for c in g["GEO"].conflicts(net, (layer,), LineString(xy).buffer(width / 2), limit=6)
           if c[1] not in ((escape,) if isinstance(escape, str) else (escape or ()))]
    if bad:
        raise SystemExit(f"patch track {net} {layer} {pts}: {bad}")
    g["track"](net, layer, width, *pts)


def drill(g, net, x, y, size=0.6):
    bad = g["GEO"].conflicts(net, CU, Point(x, y).buffer(size / 2), limit=3, via=True)
    if bad:
        raise SystemExit(f"patch via {net} ({x}, {y}): {bad}")
    if size >= 1.6:
        g["via"](net, x, y, power=True)
    else:
        g["via"](net, x, y, size=size)


# HV_RET core plane (In1) continuity. The Kelvin pair's In1 wedge ran from R5 (inside the LEG_RET
# region, which meets the board edge) to the bottom band: an In1 cut from edge to edge, leaving
# R5 + leg B's C40 on one piece and leg A's C38/C39 + the trunk on another (KiCad listed it as
# zone-to-zone ratsnest). The pair now runs down on In2, where BUS_P wraps over R5 so the run is
# only a notch, and rejoins its In1 band route at the bottom; the wedge closes. Likewise C63.2's
# Cgs source joined the LEG_RET region by an In1 slot that, with C40.1's antipad, sealed off leg
# B's C41 piece: it now reaches R21.2's LEG_RET via on In2.
OPEN_IN1 = [(30.0, 0.6, 58.0, 12.5), (0.6, 38.5, 101.0, 47.0), (77.0, 27.2, 214.0, 50.5)]
REMOVE += [{"net": "ocp_kelvin_p", "box": [35.9, 7.9, 107.7, 53.6], "layer": "In1.Cu"},
           {"net": "ocp_kelvin_n", "box": [41.2, 15.1, 120.0, 72.5], "layer": "In1.Cu"},
           {"net": "leg_ret", "box": [24.2, 12.1, 24.3, 23.4], "layer": "In1.Cu"}]
KP_VIA, KN_VIA = (40.4, 38.2), (39.4, 40.6)
KP_MID, KN_MID = (42.2, 30.8), (41.3, 31.8)   # below the B SW_B lane (y < 27) + 3.2 mm


# HV_RET trunk: PS2's N_LS / V24_RAW feeds must cross the In1 trunk band (F/B there carry the
# mains lanes), and their In1 L (down x 211, left along y 75) cut the core plane off the trunk's
# bulk-cap leg (C5/C6). Bridge the cut on F and B beside it, power vias into both In1 pieces.
BRIDGE = (203.5, 52.5, 226.0, 75.0)
BRIDGE_VIAS = [(205.6, 55.2), (207.8, 55.2), (205.6, 72.6), (207.8, 72.6),
               (216.0, 61.0), (216.0, 66.0), (216.0, 71.0), (220.5, 61.0), (220.5, 66.0), (220.5, 71.0)]


def merge_zones(g, net, layer):
    """One outline per connected piece of `net`'s pours on `layer` (no overlapping same-net zones)."""
    from shapely.ops import unary_union
    mine = [z for z in g["ZONES"] if z["net"] == net and z["layer"] == layer]
    shape = unary_union([Polygon(z["outline"], z["holes"]).buffer(0.001, join_style=2) for z in mine])
    g["ZONES"][:] = [z for z in g["ZONES"] if not (z["net"] == net and z["layer"] == layer)]
    for q in getattr(shape, "geoms", [shape]):
        q = q.buffer(-0.001, join_style=2).simplify(0.001)
        g["ZONES"].append({**mine[0], "outline": [[round(x, 3), round(y, 3)] for x, y in list(q.exterior.coords)[:-1]],
                           "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in q.interiors]})


def add(g):
    g["zone"]("v3v3", "In1.Cu", SPUR, name="v3v3 SELV island")
    g["zone"]("selv_gnd", "In2.Cu", SPUR, name="selv_gnd SELV island")
    merge_zones(g, "v3v3", "In1.Cu")
    merge_zones(g, "selv_gnd", "In2.Cu")
    esc = g["ESCAPES"]
    for lay in ("F.Cu", "B.Cu"):
        g["zone"]("hv_ret", lay, BRIDGE, name="hv_ret trunk bridge", priority=2)
    for x, y in BRIDGE_VIAS:
        drill(g, "hv_ret", x, y, size=1.6)
    # In1 notch off the LEG_RET region to the gap between C40.2 / C38.2, In2 notch from there to the
    # bottom band (each plane is cut from one edge only), In1 band onward.
    put(g, "ocp_kelvin_p", "In1.Cu", 0.3, [36.0, 8.0], [39.4, 11.4], [42.2, 11.4], list(KP_MID), escape="hv_ret")
    drill(g, "ocp_kelvin_p", *KP_MID)
    put(g, "ocp_kelvin_p", "In2.Cu", 0.3, list(KP_MID), [42.2, 36.4], list(KP_VIA), escape="bus_p")
    drill(g, "ocp_kelvin_p", *KP_VIA)
    put(g, "ocp_kelvin_p", "In1.Cu", 0.3, list(KP_VIA), [42.2, 40.0], [42.2, 42.6], [107.6, 42.6], [107.6, 53.5],
        escape="hv_ret")       # dead-end notch from the plane edge to the via
    put(g, "ocp_kelvin_n", "In1.Cu", 0.3, [41.3, 15.2], list(KN_MID), escape="hv_ret")
    drill(g, "ocp_kelvin_n", *KN_MID)
    put(g, "ocp_kelvin_n", "In2.Cu", 0.3, list(KN_MID), [41.3, 35.5], [39.4, 37.4], list(KN_VIA), escape="bus_p")
    drill(g, "ocp_kelvin_n", *KN_VIA)
    if not g["link"]("ocp_kelvin_n", "In1.Cu", (37.0, 38.5, 44.0, 45.0), 0.3,
                     [f"@{KN_VIA[0]},{KN_VIA[1]},In1.Cu", "@41.3,43.4,In1.Cu"]):
        raise SystemExit("patch: KELVIN_N via to band")
    put(g, "ocp_kelvin_n", "In1.Cu", 0.3, [41.3, 43.4], [106.6, 43.4], [106.6, 72.4],
        [119.95, 72.4], escape="hv_ret")
    put(g, "leg_ret", "In2.Cu", 0.3, [24.27, 23.3], [19.8, 9.7], escape="bus_p")
    put(g, "l_filt", "F.Cu", 1.0, "L1.4", [230.0, 60.0], [230.0, 89.0])
    drill(g, "l_filt", 230.0, 89.0, size=0.85)
    put(g, "l_filt", "B.Cu", 1.0, [230.0, 89.0], [230.5, 90.0], [230.5, 107.0])
    put(g, "l_filt", "B.Cu", 0.6, [230.5, 102.8], "C3.1")
    esc.append({"ref": "R67", "pad": "1", "rect": [242.1, 100.6, 244.4, 106.6]})
    put(g, "l_filt", "F.Cu", 0.6, "R67.1", [242.96, 106.0], escape="r1mid")
    put(g, "l_filt", "F.Cu", 0.6, [242.96, 106.0], [242.96, 121.7])
    put(g, "n_filt", "B.Cu", 0.6, [237.5, 91.0], [243.5, 91.0])
    drill(g, "n_filt", 243.5, 91.0, size=0.85)
    esc.append({"ref": "R70", "pad": "2", "rect": [242.1, 90.0, 244.4, 96.4]})
    put(g, "n_filt", "F.Cu", 0.6, [243.5, 91.0], "R70.2", escape="r2mid")
    esc += [{"ref": "R67", "pad": "2", "rect": [233.562, 100.6, 240.938, 102.4]},
            {"ref": "R68", "pad": "1", "rect": [233.562, 100.6, 240.938, 102.4]},
            {"ref": "R69", "pad": "2", "rect": [233.562, 94.6, 240.938, 96.4]},
            {"ref": "R70", "pad": "1", "rect": [233.562, 94.6, 240.938, 96.4]}]
    put(g, "led2", "F.Cu", 0.3, "U36.2", [226.5, 93.73], [228.27, 95.5])
    esc.append({"ref": "R69", "pad": "1", "rect": [227.8, 94.6, 232.2, 96.4]})
    put(g, "led2", "F.Cu", 0.3, [228.27, 95.5], "R69.1", escape="r2mid")
    put(g, "led1", "F.Cu", 0.3, "U36.1", [226.5, 96.27], [229.3, 99.07], [229.3, 100.0])
    esc.append({"ref": "R68", "pad": "2", "rect": [228.5, 99.5, 232.2, 102.4]})
    put(g, "led1", "F.Cu", 0.3, [229.3, 100.0], [229.3, 101.5], "R68.2", escape="r1mid")
    for pin, net in (("16", "selv_gnd"), ("14", "v3v3"), ("9", "selv_gnd")):
        y = g["GEO"].pad(f"U34.{pin}")["y"]
        drill(g, net, 32.3, y)
        put(g, net, "F.Cu", 0.25, f"U34.{pin}", [32.3, y])
    link = g["link"]
    L4 = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    link("leg_b-dis", L4, (22, 50, 45, 75), 0.25, ["R16.1", "U23.1", "Q4.3"])
    link("leg_b.driver-dt", L4, (22, 50, 45, 75), 0.25, ["R17.1", "U2.6"])
    link("bias_bad", L4, (5, 55, 95, 140), 0.25, ["U23.2", "U22.2", "U40.4"])
    link("pwm_hb", "F+B", (20, 50, 62, 189), 0.3, ["U2.1", "J4.7"])
    link("permit", "F+B", (20, 60, 95, 189), 0.3, ["R14.1", "R6.1", "J4.9"])
    link("bias_hb_bad", "F+B", (0.6, 100, 40, 140), 0.3, ["U34.13", "U25.6"])
    link("bias_ha_bad", "F+B", (0.6, 100, 90, 140), 0.3, ["U33.13", "U25.3"])
    for net, pads_ in SELV_OUTER.items():
        link(net, "F+B", (0.6, 52.0, 217.0, 189.4), 0.4 if net == "v15_selv" else 0.25, pads_)
