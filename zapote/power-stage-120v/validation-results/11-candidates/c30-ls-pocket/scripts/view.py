#!/usr/bin/env python3
"""Render a window of a native-21 copper dump, one panel per copper layer, coloured by isolation domain.

    python3 -I view.py COPPER_DUMP.json X0 Y0 X1 Y1 OUT.png [--nets a,b,...] [--label]

Pads carry their net name (--label); --nets draws only those nets in full colour (others grey). Layout aid only.
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly, Circle

PS = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PS / "native-21/layout"))
import rules21  # noqa: E402

COL = {"SELV": "#2ca02c", "PE": "#8c564b", "NONE": "#bbbbbb"}
GRP = {"LOW": "#ff7f0e", "SW_A": "#d62728", "SW_B": "#9467bd"}


def colour(net):
    d = rules21.domain(net)
    if d == "HOT":
        return GRP.get(rules21.GROUP.get(net), "#e6b800")
    return COL.get(d, "#bbbbbb")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("x0", type=float); ap.add_argument("y0", type=float)
    ap.add_argument("x1", type=float); ap.add_argument("y1", type=float)
    ap.add_argument("out")
    ap.add_argument("--nets", default="")
    ap.add_argument("--label", action="store_true")
    ap.add_argument("--layers", default="F.Cu,In1.Cu,In2.Cu,B.Cu")
    a = ap.parse_args()
    d = json.loads(Path(a.dump).read_text())
    focus = set(filter(None, a.nets.split(",")))
    lays = a.layers.split(",")
    w, h = a.x1 - a.x0, a.y1 - a.y0
    fig, axs = plt.subplots(1, len(lays), figsize=(len(lays) * 6, 6 * h / w + 0.6), squeeze=False)

    def inwin(xs, ys):
        return max(xs) >= a.x0 and min(xs) <= a.x1 and max(ys) >= a.y0 and min(ys) <= a.y1

    def c(net):
        return colour(net) if not focus or net in focus else "#dddddd"

    for ax, lay in zip(axs[0], lays):
        for z in d["zones"]:
            if z["layer"] != lay:
                continue
            xs = [p[0] for p in z["pts"]]; ys = [p[1] for p in z["pts"]]
            if inwin(xs, ys):
                ax.add_patch(MPoly(z["pts"], closed=True, fc=c(z["net"]), alpha=0.25, ec=c(z["net"]), lw=0.3))
        for t in d["tracks"]:
            if t["layer"] != lay:
                continue
            xs = [t["a"][0], t["b"][0]]; ys = [t["a"][1], t["b"][1]]
            if inwin(xs, ys):
                ax.plot(xs, ys, color=c(t["net"]), lw=max(t["w"] * 72 * 6 / w / 25.4 * 1.0 * 25.4, 0.5),
                        solid_capstyle="round", alpha=0.9)
        for p in d["pads"]:
            if lay not in p["layers"] and not p["tht"]:
                continue
            xs = [q[0] for q in p["pts"]]; ys = [q[1] for q in p["pts"]]
            if inwin(xs, ys):
                ax.add_patch(MPoly(p["pts"], closed=True, fc=c(p["net"] or ""), ec="k", lw=0.3, alpha=0.9))
                if a.label and lay == "F.Cu" or (a.label and p["tht"]):
                    ax.text(sum(xs) / len(xs), sum(ys) / len(ys), f"{p['ref']}\n{(p['net'] or '')[:14]}",
                            fontsize=3.2, ha="center", va="center")
        for v in d["vias"]:
            x, y = v["at"]
            if a.x0 <= x <= a.x1 and a.y0 <= y <= a.y1:
                ax.add_patch(Circle((x, y), v["d"] / 2, fc=c(v["net"]), ec="k", lw=0.4))
        ax.set_xlim(a.x0, a.x1); ax.set_ylim(a.y1, a.y0); ax.set_aspect("equal")
        ax.set_title(lay, fontsize=8); ax.tick_params(labelsize=5)
        ax.grid(True, lw=0.2)
        import numpy as np
        ax.set_xticks(np.arange(round(a.x0), a.x1 + 0.01, 2 if w <= 40 else 5))
        ax.set_yticks(np.arange(round(a.y0), a.y1 + 0.01, 2 if h <= 40 else 5))
    fig.tight_layout()
    fig.savefig(a.out, dpi=220)


main()
