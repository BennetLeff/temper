#!/usr/bin/env python3
"""Zoom plot of a copper dump: per-layer panels of pours, tracks, vias and pads in a window (study aid, not a gate).
    python3 zoom.py COPPER_DUMP.json X0 Y0 X1 Y1 OUT.png [--hl NET,NET] [--mark X,Y ...]"""
import argparse, json, hashlib
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP, Circle
from shapely.geometry import Polygon, box

ap = argparse.ArgumentParser()
ap.add_argument("dump"); ap.add_argument("x0", type=float); ap.add_argument("y0", type=float)
ap.add_argument("x1", type=float); ap.add_argument("y1", type=float); ap.add_argument("out")
ap.add_argument("--hl", default=""); ap.add_argument("--mark", nargs="*", default=[])
a = ap.parse_args()
d = json.load(open(a.dump))
W = box(a.x0, a.y0, a.x1, a.y1)
hl = set(filter(None, a.hl.split(",")))
LAY = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
def col(net):
    if net in hl: return "red"
    h = int(hashlib.md5(net.encode()).hexdigest()[:6], 16)
    return "#%06x" % (h & 0x7f7f7f | 0x404040)
fig, axs = plt.subplots(2, 2, figsize=(22, 22 * (a.y1 - a.y0) / (a.x1 - a.x0) + 1))
for ax, lay in zip(axs.flat, LAY):
    ax.set_title(lay); ax.set_xlim(a.x0, a.x1); ax.set_ylim(a.y1, a.y0); ax.set_aspect("equal")
    for z in d["zones"]:
        if z["layer"] != lay or len(z["pts"]) < 3: continue
        p = Polygon(z["pts"])
        if not p.intersects(W): continue
        ax.add_patch(MP(z["pts"], closed=True, fc={"v3v3": "#b8e0b8", "selv_gnd": "#9fc0e8"}.get(z["net"], "#eee0c0"), ec="none", alpha=0.7))
        for h in z["holes"]:
            if len(h) > 2: ax.add_patch(MP(h, closed=True, fc="white", ec="none"))
    for t in d["tracks"]:
        if t["layer"] != lay: continue
        (xa, ya), (xb, yb) = t["a"], t["b"]
        if max(xa, xb) < a.x0 or min(xa, xb) > a.x1 or max(ya, yb) < a.y0 or min(ya, yb) > a.y1: continue
        ax.plot([xa, xb], [ya, yb], color=col(t["net"]), lw=max(0.5, t["w"] * 72 * 22 / (a.x1 - a.x0) / 2.54 * 0.3), solid_capstyle="round")
        if t["net"] in hl or (a.x1 - a.x0) < 30:
            ax.text((xa + xb) / 2, (ya + yb) / 2, t["net"], fontsize=5, color=col(t["net"]), clip_on=True)
    for p in d["pads"]:
        if lay not in p.get("layers", ["F.Cu"]) and not p.get("tht"): continue
        P = Polygon(p["pts"])
        if not P.intersects(W): continue
        ax.add_patch(MP(p["pts"], closed=True, fc=col(p["net"]) if p["net"] else "grey", ec="k", lw=0.3, alpha=0.8))
        c = P.centroid; ax.text(c.x, c.y, f"{p['ref']}\n{p['net']}", fontsize=4.5, ha="center", va="center", clip_on=True)
    for v in d["vias"]:
        x, y = v["at"]
        if not (a.x0 <= x <= a.x1 and a.y0 <= y <= a.y1): continue
        ax.add_patch(Circle((x, y), v["d"] / 2, fc=col(v["net"]), ec="k", lw=0.3))
        ax.text(x, y + v["d"], v["net"], fontsize=4, ha="center", clip_on=True)
    for m in a.mark:
        x, y = map(float, m.split(",")); ax.add_patch(Circle((x, y), 3.0, fc="none", ec="magenta", lw=1, ls="--"))
    ax.grid(True, lw=0.2)
plt.tight_layout(); plt.savefig(a.out, dpi=110)
