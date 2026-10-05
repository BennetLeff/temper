"""Render dimensioned fixture sections; apparatus envelopes are explicitly labeled."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent
fig, axes = plt.subplots(1, 2, figsize=(16, 8), layout="constrained")
a, b = axes
for ax in axes:
    ax.set_aspect("equal")
    ax.set_xlabel("x / mm")
    ax.set_ylabel("z / mm")
    ax.grid(alpha=0.15)


def rect(ax, x, z, w, h, color, **kwargs):
    ax.add_patch(Rectangle((x, z), w, h, facecolor=color, edgecolor="#374151", **kwargs))


rect(a, -60, -65, 120, 10, "#9ca3af")
for x in [-55, 45]:
    rect(a, x, -55, 10, 155, "#9ca3af")
rect(a, -55, 100, 110, 10, "#9ca3af")
rect(a, -16, 80, 32, 20, "#fbbf24")
rect(a, -10, 65, 20, 15, "#fb923c")
rect(a, -2, 3.6, 4, 61.4, "#e5e7eb")
rect(a, -3, 0.6, 6, 3, "#60a5fa")
for x in [-45, 15]:
    rect(a, x, -12, 30, 8, "#9ca3af")
for x in [-25, 9]:
    rect(a, x, -4, 16, 4, "#bfdbfe")
for x in [-35, 14.1]:
    rect(a, x, -22, 20.9, 10, "#94a3b8")
for x in [-38, 32]:
    rect(a, x, -55, 6, 43, "#cbd5e1")
rect(a, -14, -47, 28, 47.6, "none", linestyle="--", linewidth=1.4)
a.annotate(
    "R7 cartridge interface\n(cartridge not included)",
    xy=(14, -35),
    xytext=(65, -35),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
a.annotate(
    "Independent load cell envelope",
    xy=(10, 72),
    xytext=(65, 75),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
a.annotate(
    "Stage envelope\n0.4 mm challenge measured\nat carrier, not command",
    xy=(16, 90),
    xytext=(65, 100),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
a.annotate(
    "Cap-force coupon Ø6 × 3\nØ36 pan accessory is separate",
    xy=(3, 2),
    xytext=(65, 28),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
a.annotate(
    "z0 glass datum\nØ18 aperture / Ø30 plate clearance",
    xy=(-25, 0),
    xytext=(-115, 20),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
a.annotate(
    "Ø28.2 split clamp\nfor Ø28 fixed housing\nClamp deformation unqualified",
    xy=(-25, -17),
    xytext=(-115, -30),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
a.text(
    -55,
    -78,
    "Independent optical targets: pan, carrier and island.\nProduction witness readings are not the reference.",
    fontsize=9,
)
a.set_xlim(-120, 165)
a.set_ylim(-85, 120)
a.set_title("A · Force/displacement station\nNominal dry fixture; unselected metrology")

rect(b, -10, -12, 20, 12, "#9ca3af")
rect(b, -6, -9.953, 12, 7.953, "#bfdbfe")
rect(b, -4, -2, 8, 2, "#bfdbfe")
rect(b, -25, -7.5, 137, 3, "#9ca3af")
rect(b, -25, -6.75, 145, 1.5, "#60a5fa")
rect(b, 108, -23.9155, 24, 35.831, "#9ca3af")
rect(b, 110, -21.9155, 20, 31.831, "#bfdbfe")
rect(b, 118, 9.9155, 4, 10.0845, "#9ca3af")
rect(b, 119, 9.9155, 2, 10.0845, "#bfdbfe")
rect(b, 18.5, -6, 3, 26, "#9ca3af")
rect(b, 19.25, -6, 1.5, 26, "#bfdbfe")
rect(b, 15, 20, 10, 6, "#fb923c")
rect(b, -10, 0, 20, 0.1, "#ef4444")
for x in [-10, 4]:
    rect(b, x, 0.1, 6, 3, "#6b7280")
rect(b, -3, 0.1, 6, 4, "#fde68a")
b.annotate(
    "Replaceable test diaphragm\nØ8 aperture ≠ effective area\nNo250°C qualification",
    xy=(0, 0.1),
    xytext=(-30, 47),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
b.annotate(
    "Bidirectional low-pressure source\nnot selected; open coupling",
    xy=(-25, -6),
    xytext=(-42, -37),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
b.annotate(
    "Closed pressure transducer\nenvelope; measure Δp at cell",
    xy=(20, 23),
    xytext=(45, 42),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
b.annotate(
    "Connected1.5 mm ID path\n104 mm wall-to-wall tube span",
    xy=(65, -6),
    xytext=(35, -30),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
b.annotate(
    "10mL cold plenum\n2mm open dry reference\nBlock only as controlled fault",
    xy=(120, 20),
    xytext=(90, 58),
    arrowprops={"arrowstyle": "->"},
    fontsize=9,
)
b.text(
    -30,
    -58,
    "B is a separate seal-coupon cell, not connected to A's unsealed cartridge.\nNo selected membrane, pressure rating, leak limit or hot feedthrough.\nBlue region is one connected CAD fluid domain; see geometry.json.",
    fontsize=9,
)
b.set_xlim(-45, 155)
b.set_ylim(-63, 75)
b.set_title(
    "B · Connected pressure-reference cell\nSection schematic; STEP has actual circular chambers"
)
fig.suptitle(
    "R7 bench fixture preparation · ALL PHYSICAL RESULTS NOT_RUN", fontsize=15, weight="bold"
)
fig.savefig(ROOT / "fixture-sections.png", dpi=160)
