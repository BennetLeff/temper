"""Plot a board region from dump_copper.py JSON, for hand routing.

python3 cad/tools/region_view.py DUMP.json OUT.png x0 y0 x1 y1 [layers] [highlight-nets]
  layers: comma list, default F.Cu,B.Cu,In2.Cu (In1 fill drawn faintly underneath)
  highlight-nets: comma list drawn in bold colours and labelled
Needs matplotlib. Board y grows downward, as in KiCad.
"""
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon

dump, out = sys.argv[1], sys.argv[2]
x0, y0, x1, y1 = map(float, sys.argv[3:7])
layers = sys.argv[7].split(",") if len(sys.argv) > 7 and sys.argv[7] else ["F.Cu", "B.Cu", "In2.Cu"]
hl = set(sys.argv[8].split(",")) if len(sys.argv) > 8 else set()
items = json.load(open(dump))["items"]
COL = {"F.Cu": "#c83737", "B.Cu": "#3771c8", "In2.Cu": "#c8a037", "In1.Cu": "#999999"}
HL = ["#00a000", "#a000a0", "#008b8b", "#ff7f00", "#000000", "#e6194b", "#4363d8"]
hlcol = {n: HL[i % len(HL)] for i, n in enumerate(sorted(hl))}
fig, ax = plt.subplots(figsize=(14, 14 * (y1 - y0) / (x1 - x0)))


def inside(x, y, m=3):
    return x0 - m <= x <= x1 + m and y0 - m <= y <= y1 + m


for it in items:
    if it["kind"] == "fill" and it["layer"] == "In1.Cu":
        for p in it["polys"]:
            ax.add_patch(Polygon(p, closed=True, fc="#eeeeee", ec="none", zorder=0))
for it in items:
    if it["kind"] == "keepout" and it["layer"] in ("In1.Cu",):
        for p in it["polys"]:
            ax.add_patch(Polygon(p, closed=True, fc="none", ec="#888", ls=":", lw=0.8, zorder=1))
order = {name: i for i, name in enumerate(reversed(layers))}
for it in items:
    k = it["kind"]
    if k == "track" and it["layer"] in layers and (inside(*it["a"]) or inside(*it["b"])):
        c = hlcol.get(it["net"], COL[it["layer"]])
        lw_pts = it["w"] * 72 / 25.4 * 14 / (x1 - x0) * 1.0
        ax.plot([it["a"][0], it["b"][0]], [it["a"][1], it["b"][1]], color=c, lw=max(lw_pts * (x1 - x0) / 14 * 14 / (x1 - x0), 0.6),
                solid_capstyle="round", alpha=0.95 if it["net"] in hl else 0.55, zorder=2 + order[it["layer"]])
    elif k == "pad" and it["layer"] in layers:
        for p in it["polys"]:
            if any(inside(*q) for q in p):
                c = hlcol.get(it["net"], COL[it["layer"]])
                ax.add_patch(Polygon(p, closed=True, fc=c, ec="k", lw=0.3, alpha=0.8 if it["net"] in hl else 0.45, zorder=6))
    elif k == "via" and inside(it["x"], it["y"]):
        ax.add_patch(Circle((it["x"], it["y"]), it["d"] / 2, fc=hlcol.get(it["net"], "#555"), ec="k", lw=0.3, zorder=7))
    elif k == "fp" and inside(it["x"], it["y"], 0):
        for p in it["courtyard"]:
            ax.add_patch(Polygon(p, closed=True, fc="none", ec="#aa00aa", lw=0.4, zorder=8))
        ax.text(it["x"], it["y"], it["ref"], fontsize=7, ha="center", va="center", zorder=9, color="#400040")
# Label highlighted nets once per pad.
for it in items:
    if it["kind"] == "pad" and it["net"] in hl and it["layer"] == "F.Cu":
        p = it["polys"][0]
        cx, cy = sum(q[0] for q in p) / len(p), sum(q[1] for q in p) / len(p)
        if inside(cx, cy, 0):
            ax.text(cx, cy, f'{it["ref"]}.{it["num"]}', fontsize=5, color="k", zorder=10)
ax.set_xlim(x0, x1)
ax.set_ylim(y1, y0)
ax.set_aspect("equal")
ax.grid(True, lw=0.2)
step = 1 if x1 - x0 <= 30 else 5
ax.set_xticks([x for x in range(int(x0), int(x1) + 1, step)])
ax.set_yticks([y for y in range(int(y0), int(y1) + 1, step)])
ax.tick_params(labelsize=6)
ax.set_title(f"{','.join(layers)}  highlight: {','.join(sorted(hl))}", fontsize=8)
fig.savefig(out, dpi=170, bbox_inches="tight")
print(out)
