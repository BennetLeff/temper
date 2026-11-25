"""2-D placement render (courtyards coloured by block, pads, holes and keep-outs, routing channels).

Matplotlib, top view in world mm (X right, Y rear). Writes PNG and SVG.
"""
from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402

import geom  # noqa: E402

COLORS = {
    "connectors": "#8c8c8c", "mcu": "#3b6fb6", "buck_3v3": "#d9822b", "blower_buck": "#c0392b",
    "rtd": "#2e8b57", "thermal_sense": "#8e44ad", "interlock": "#b8860b", "trip_glue": "#e1a95f",
    "capmode": "#16a085", "rms": "#1f77b4", "d11_ctmon": "#17becf", "ntc_afe": "#bcbd22",
    "j4_if": "#7f7f7f", "expander": "#5dade2", "ui_bus": "#f39c12", "unassigned": "#000000",
}
LABEL_BLOCKS = True


def draw(parts, poses, outline, holes, out_base, title, channels=(), zones=(), keepout_d=8.0, notes=(),
         label_refs=None):
    x0, y0, x1, y1 = outline
    w, h = x1 - x0, y1 - y0
    fig, ax = plt.subplots(figsize=(max(8, w / 9), max(5, h / 9 + 1)), dpi=150)
    ax.add_patch(Rectangle((x0, y0), w, h, fill=True, fc="#eef3ea", ec="black", lw=1.2, zorder=0))
    for (zx0, zy0, zx1, zy1, label, col) in zones:
        ax.add_patch(Rectangle((zx0, zy0), zx1 - zx0, zy1 - zy0, fc=col, ec=col, alpha=0.18, lw=0.6, zorder=1))
        ax.text((zx0 + zx1) / 2, zy1 - 0.8, label, fontsize=4.5, ha="center", va="top", color=col, zorder=6)
    for cx0, cy0, cx1, cy1 in channels:
        ax.add_patch(Rectangle((cx0, cy0), cx1 - cx0, cy1 - cy0, fill=False, ec="#999999", ls="--", lw=0.5, zorder=1))
    for hx, hy in holes:
        ax.add_patch(Circle((hx, hy), keepout_d / 2, fc="#ffffff", ec="#555555", ls=":", lw=0.6, zorder=2))
        ax.add_patch(Circle((hx, hy), 2.0, fc="#444444", ec="none", zorder=3))
    for ref, (X, Y, t) in poses.items():
        p = parts[ref]
        col = COLORS.get(p["block"], "#000000")
        for loop in geom.crtyd_world(p, X, Y, t):
            ax.add_patch(Polygon(loop, closed=True, fc=col, ec=col, alpha=0.55, lw=0.3, zorder=4))
        for q in geom.pads_world(p, X, Y, t):
            ax.add_patch(Rectangle((q["x"] - q["w"] / 2, q["y"] - q["h"] / 2), q["w"], q["h"], fc="#b87333",
                                   ec="none", alpha=0.8, zorder=5))
        big = (p["crtyd_area_mm2"] or 0) > 12 or ref.startswith(("U", "J", "L"))
        if label_refs is None and big or (label_refs is not None and ref in label_refs):
            r = geom.rect(p, X, Y, t)
            ax.text((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, ref, fontsize=3.6, ha="center", va="center", zorder=7)
    ax.set_xlim(x0 - 3, x1 + 3)
    ax.set_ylim(y0 - 3, y1 + 3)
    ax.set_aspect("equal")
    ax.set_xlabel("world X (mm)")
    ax.set_ylabel("world Y (mm), rear up")
    ax.set_title(title, fontsize=8)
    handles = [Rectangle((0, 0), 1, 1, fc=c, alpha=0.6) for c in COLORS.values()]
    ax.legend(handles, list(COLORS), fontsize=4.5, loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False)
    for i, n in enumerate(notes):
        fig.text(0.01, 0.01 + 0.025 * i, n, fontsize=5)
    fig.tight_layout()
    fig.savefig(str(out_base) + ".png")
    fig.savefig(str(out_base) + ".svg")
    plt.close(fig)
