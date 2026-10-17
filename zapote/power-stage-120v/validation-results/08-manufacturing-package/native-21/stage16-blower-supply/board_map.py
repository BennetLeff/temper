#!/usr/bin/env python3
"""Domain map of native-21 stage 15b with the stage-16 boxes drawn on it.

    python3 -B board_map.py board/dump.json out/board-map-stage16.png

Copper from dump_board.py (pour outlines), coloured by the unit's domains.py. Red dashed: J11/F2 tap block
at (266.5, 123.5) 12.9 x 14.2 (tap_spot.py); orange dashed: the least-displacing IRM-60 courtyard on the
tongue (45, 145) and option (c)'s best corner box (176.5, 87.0) long-y (free_space.py), both rejected.
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MPoly, Rectangle  # noqa: E402

from common import domain, load  # noqa: E402

COL = {"SELV": "#2e9d3a", "PE": "#d4b106", "MAINS": "#c0392b", "HOT": "#e67e22", "SW_A": "#8e44ad", "SW_B": "#2c3e90"}
d = load(sys.argv[1])
fig, ax = plt.subplots(figsize=(22, 15))
for z in d["zones"]:
    ax.add_patch(MPoly(z["pts"], closed=True, fc=COL.get(domain(z["net"]), "#999"), ec="none", alpha=0.15))
for t in d["tracks"]:
    ax.plot([t["a"][0], t["b"][0]], [t["a"][1], t["b"][1]], color=COL.get(domain(t["net"]), "#999"),
            lw=max(0.4, t["w"] * 1.2), alpha=0.6, solid_capstyle="round")
for p in d["pads"]:
    if len(p["pts"]) > 2:
        ax.add_patch(MPoly(p["pts"], closed=True, fc=COL.get(domain(p["net"]), "#999") if p["net"] else "#999", ec="none"))
for f in d["footprints"]:
    x0, y0, x1, y1 = f["crtyd"]
    big = (x1 - x0) * (y1 - y0) > 120
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="k", lw=0.6 if big else 0.25))
    if big or f["ref"].startswith("H"):
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, f["ref"], ha="center", va="center", fontsize=7)
for (cx, cy, w, h, c, lab) in ((266.5, 123.5, 12.9, 14.2, "red", "J11+F2 tap"),
                               (45, 145, 88, 53, "darkorange", "IRM-60 tongue (rejected)"),
                               (176.5, 87.0, 53, 88, "darkorange", "option (c) corner (rejected)")):
    ax.add_patch(Rectangle((cx - w / 2, cy - h / 2), w, h, fill=False, ec=c, lw=2, ls="--"))
    ax.text(cx, cy - h / 2 - 1.5, lab, color=c, ha="center", fontsize=9, weight="bold")
ax.plot([0, 290, 290, 91, 91, 0, 0], [0, 0, 140, 140, 190, 190, 0], "k-", lw=1.5)
ax.set_xlim(-5, 295); ax.set_ylim(195, -5); ax.set_aspect("equal")
ax.set_xticks(range(0, 291, 10)); ax.set_yticks(range(0, 191, 10)); ax.grid(lw=0.2)
ax.set_title("native-21 stage 15b (copper.json a831e90c, pour outlines): SELV green, PE yellow, MAINS red, HOT orange, SW_A purple, SW_B blue")
fig.savefig(sys.argv[2], dpi=100, bbox_inches="tight")
print("wrote", sys.argv[2])
