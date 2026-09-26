#!/usr/bin/env python3
"""Render a domain-coloured placement preview from placement_metrics --world output."""

from __future__ import annotations

import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

COLOURS = {"SELV": "#1a9850", "PE": "#d4a017", "HOT": "#d73027", "NONE": "#999999"}
TANK = {"res_a", "crbleed_1", "crbleed_2", "crbleed_3", "sw_a", "sw_b", "coil_feed"}
MAINS = {"ac_l_in", "l_f", "l_filt", "ac_n_in", "n_filt", "tco_l", "xbleed_mid", "rect_p", "rect_n"}


def colour(net: str, domains: dict[str, str]) -> str:
    if net in TANK:
        return "#7b3294"
    if net in MAINS:
        return "#2166ac"
    return COLOURS[domains.get(net, "NONE")]


def main() -> None:
    world = json.load(open(sys.argv[1]))
    fig, ax = plt.subplots(figsize=(22, 17), dpi=90)
    ax.add_patch(Rectangle((0, 0), 220, 160, fill=False, lw=2, ec="k"))
    ax.add_patch(Rectangle((5, -6), 155, 6, fc="#bbbbbb", ec="k"))
    ax.text(82.5, -3, "HEATSINK (D2, x 5-160)", ha="center", va="center", fontsize=11)
    for ref, (x1, y1, x2, y2) in world["courtyards"].items():
        ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, ec="#e377c2", lw=0.8))
        ax.text((x1 + x2) / 2, (y1 + y2) / 2, ref, ha="center", va="center",
                fontsize=7 if x2 - x1 < 8 else 10, weight="bold")
    for pad in world["pads"]:
        x1, y1, x2, y2 = pad["box"]
        c = colour(pad["net"], world["domains"])
        ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fc="white" if pad["npth"] else c,
                               ec="k" if pad["npth"] else c, lw=0.5))
    ax.set_xlim(-3, 223)
    ax.set_ylim(163, -9)
    ax.set_aspect("equal")
    ax.grid(True, ls=":", lw=0.4)
    ax.set_xticks(range(0, 221, 10))
    ax.set_yticks(range(0, 161, 10))
    ax.legend(handles=[Patch(color=c, label=l) for c, l in (
        ("#1a9850", "SELV (earthed ELV)"), ("#d4a017", "PE"), ("#2166ac", "mains / rectifier"),
        ("#d73027", "HOT"), ("#7b3294", "switch nodes / tank"))],
        loc="upper center", bbox_to_anchor=(0.5, -0.03), ncol=5)
    ax.set_title("power-stage-120v native-03 placement (mm; mains left, coil right, heatsink top)")
    plt.savefig(sys.argv[2], bbox_inches="tight")


if __name__ == "__main__":
    main()
