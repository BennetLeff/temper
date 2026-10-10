#!/usr/bin/env python3
"""Plot the FET-row copper (four layers) from a copper dump, nets coloured, with a 1 mm grid.

    python3 plot_fetrow.py <copper-dump.json> <out.png> [x0 y0 x1 y1]
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point, Polygon, box

if sys.argv[1].endswith(".gz"):   # all-copper export (extract_geometry.py) -> dump-like dict
    import gzip
    a = json.load(gzip.open(sys.argv[1], "rt"))
    d = {"zones": [], "tracks": [], "vias": [], "pads": []}
    for q in a["primitives"]:
        if q["kind"] == "zone":
            d["zones"].append({"net": q["net"], "layer": q["layer"], "pts": q["shell"], "holes": q["holes"]})
        elif q["kind"] == "track":
            d["tracks"].append({"net": q["net"], "layer": q["layer"], "w": q["width_mm"], "a": q["start"], "b": q["end"]})
        elif q["kind"] == "via" and q["layer"] == "F.Cu":
            d["vias"].append({"net": q["net"], "at": q["centre"], "d": q["diameter_mm"]})
        elif q["kind"] == "pad":
            d["pads"].append({"net": q["net"], "ref": q["ref"].split(".")[0], "layer": q["layer"], "pts": q["shell"]})
else:
    d = json.load(open(sys.argv[1]))
win = box(*(map(float, sys.argv[3:7]) if len(sys.argv) > 6 else (0, 0, 82, 32)))
COL = {"sw_a": "tab:red", "sw_b": "tab:blue", "leg_ret": "tab:green", "hv_ret": "olive", "bus_p": "tab:orange",
       "leg_a-gate_h": "m", "leg_a-gate_l": "m", "leg_b-gate_h": "m", "leg_b-gate_l": "m"}
fig, axs = plt.subplots(4, 1, figsize=(16, 4 * win.bounds[3] / 8 + 2))
for ax, layer in zip(axs, ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")):
    def draw(poly, net, alpha=0.55):
        poly = poly.intersection(win)
        for g in getattr(poly, "geoms", [poly]):
            if g.geom_type != "Polygon" or g.is_empty:
                continue
            ax.fill(*g.exterior.xy, color=COL.get(net, "0.6"), alpha=alpha, lw=0)
            for h in g.interiors:
                ax.fill(*h.xy, color="white", lw=0)
    for z in d["zones"]:
        if z["layer"] == layer:
            draw(Polygon(z["pts"], z.get("holes", [])), z["net"], 0.45)
    for t in d["tracks"]:
        if t["layer"] == layer:
            draw(LineString([t["a"], t["b"]]).buffer(t["w"] / 2), t["net"], 0.8)
    for p in d["pads"]:
        if p.get("layer", layer) == layer and (p.get("tht") or "layer" in p or layer == "F.Cu"):
            pg = Polygon(p["pts"])
            if pg.intersects(win):
                draw(pg, p["net"], 0.9)
                c = pg.centroid
                if win.contains(c):
                    ax.text(c.x, c.y, f"{p['ref']}", fontsize=5, ha="center")
    for v in d["vias"]:
        pt = Point(v["at"])
        if win.contains(pt):
            draw(pt.buffer(v["d"] / 2), v["net"], 1.0)
    x0, y0, x1, y1 = win.bounds
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
    ax.set_xticks(range(int(x0), int(x1) + 1, 2)); ax.set_yticks(range(int(y0), int(y1) + 1, 2))
    ax.tick_params(labelsize=5); ax.grid(lw=0.2)
    ax.set_title(layer, fontsize=8)
fig.tight_layout()
fig.savefig(sys.argv[2], dpi=170)
