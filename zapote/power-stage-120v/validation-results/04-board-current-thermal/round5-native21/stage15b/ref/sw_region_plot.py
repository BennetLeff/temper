#!/usr/bin/env python3
"""Plot SW_A / SW_B copper and their neighbours per layer from a routed copper dump.
usage: python3 sw_region_plot.py <copper-dump.json> <out.png> [x0 y0 x1 y1]
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

d = json.load(open(sys.argv[1]))
out = sys.argv[2]
x0, y0, x1, y1 = (float(v) for v in sys.argv[3:7]) if len(sys.argv) > 6 else (0, 0, 200, 120)
HI = {"sw_a": "tab:red", "sw_b": "tab:blue", "res_a": "tab:green", "coil_feed": "tab:olive",
      "bus_p": "tab:orange", "hv_ret": "tab:purple", "leg_ret": "tab:brown"}
import os
layers = os.environ.get("LAYERS", "F.Cu,In1.Cu,In2.Cu,B.Cu").split(",")
n = len(layers)
fig, axs = plt.subplots(n, 1, figsize=(18, n * 18 * (y1 - y0) / (x1 - x0) + 1), squeeze=False)
axs = axs[:, 0]
for ax, L in zip(axs, layers):
    for z in d["zones"]:
        if z["layer"] != L:
            continue
        c = HI.get(z["net"], "0.75")
        ax.add_patch(Polygon(z["pts"], closed=True, fc=c, ec="k", lw=0.2, alpha=0.55))
        for h in z.get("holes") or []:
            ax.add_patch(Polygon(h, closed=True, fc="white", ec="k", lw=0.2))
    for t in d["tracks"]:
        if t["layer"] != L:
            continue
        c = HI.get(t["net"], "0.4")
        ax.plot([t["a"][0], t["b"][0]], [t["a"][1], t["b"][1]], color=c, lw=max(0.3, t["w"] * 2.0), solid_capstyle="round")
    for p in d["pads"]:
        if not p["tht"] and L not in ("F.Cu", "B.Cu"):
            continue
        c = HI.get(p["net"], "0.2")
        ax.add_patch(Polygon(p["pts"], closed=True, fc=c, ec="k", lw=0.3, alpha=0.9))
    for v in d["vias"]:
        ax.plot(v["at"][0], v["at"][1], "o", ms=1.2, color=HI.get(v["net"], "k"))
    ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect("equal"); ax.set_title(L)
    ax.set_xticks(range(int(x0), int(x1) + 1, 5), minor=True); ax.grid(True, which="both", lw=0.2)
fig.tight_layout()
fig.savefig(out, dpi=110)
