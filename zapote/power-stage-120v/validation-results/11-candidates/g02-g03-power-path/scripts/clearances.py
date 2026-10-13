#!/usr/bin/env python3
"""Measure the copper clearances the stage-19c pours actually keep (calibration for whatif_lib.clr()).
Prints the minimum gap between each net's plane copper and every other net's non-zone copper in the corridor window.
    python3 -I clearances.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import box
from shapely.ops import unary_union
from pp_common import geom, load_copper, net_layer_geom
from whatif_lib import clr

d = load_copper(); P = d["primitives"]; W = box(62, 22, 100, 50)
for layer, net in (("In1.Cu", "hv_ret"), ("In2.Cu", "bus_p")):
    z = unary_union([geom(p) for p in P if p["net"] == net and p["layer"] == layer and p["kind"] == "zone"])
    by = {}
    for p in P:
        if p["layer"] == layer and p["net"] != net and p["kind"] != "zone":
            g = geom(p, via_ring=False)
            if g.intersects(W):
                by.setdefault(p["net"], []).append(g)
    print(layer, net)
    for n, gs in sorted(by.items(), key=lambda kv: unary_union(kv[1]).distance(z)):
        gap = unary_union(gs).distance(z)
        print("   %-14s min gap %.3f mm   rule used by whatif_lib %.1f mm   %s" % (n, gap, clr(net, n), "OK" if gap + 0.01 >= clr(net, n) else "BELOW RULE"))
