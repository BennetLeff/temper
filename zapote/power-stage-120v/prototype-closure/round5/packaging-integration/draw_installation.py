"""Dimensioned installation index from CAD route and support records."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/packaging-integration"
h = json.loads((OUT / "harness-probe.json").read_text())
colors = {"BUS_P": "#b93131", "HV_RET": "#3465a4", "RES_A": "#c17711", "SW_B": "#7d49a0"}
a = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="1050" viewBox="0 0 1440 1050">',
    '<rect width="1440" height="1050" fill="#fff"/>',
    "<style>text{font-family:Arial,sans-serif;fill:#152334} .small{font-size:15px}.label{font-size:18px}.title{font-size:25px;font-weight:bold}.note{font-size:16px} .dim{stroke:#8c9aaa;stroke-width:1;fill:none}</style>",
]


def text(x, y, t, c="label"):
    a.append(f'<text x="{x}" y="{y}" class="{c}">{t}</text>')


def line(x1, y1, x2, y2, col="#566a7a", w=1):
    a.append(f'<path d="M{x1},{y1} L{x2},{y2}" stroke="{col}" stroke-width="{w}" fill="none"/>')


def rect(x, y, w, h, fill="#eaf0f5", stroke="#8796a5"):
    a.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}"/>')


def top(x, y):
    return 340 + x * 1.45, 870 - y * 1.45


text(40, 40, "Temper • candidate support and sense-harness installation", "title")
text(
    40,
    69,
    "R4 datum • mm • proposal only • nominal CAD fit does not establish insulation, EMC or build release",
    "note",
)
text(40, 105, "R4 top projection / front at bottom", "label")
x, y = top(-185, 440)
rect(x, y, 370 * 1.45, 440 * 1.45, "#fafbfd")
for name, xywh in [
    ("Power board", [-110.5, 162, 240, 160]),
    ("Fan / sink", [-101, 93.9, 250, 68]),
    ("D22 cover", [-140, 332, 110, 80]),
    ("TANK", [-75, 27, 135, 55]),
    ("BUS", [65, 45, 60, 35]),
    ("OUT", [-130, 375, 60, 35]),
]:
    x, y = top(xywh[0], xywh[1] + xywh[3])
    rect(x, y, xywh[2] * 1.45, xywh[3] * 1.45, "#eaf0f5")
    text(x + 4, y + (95 if name == "D22 cover" else 18), name, "small")
for name, d in h["routes"].items():
    pts = [top(p[0], p[1]) for p in d["centerline_401_samples"]]
    a.append(
        '<polyline points="'
        + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        + f'" fill="none" stroke="{colors[name]}" stroke-width="3"/>'
    )
    for p in (d["points"][0], d["points"][-1]):
        x, y = top(p[0], p[1])
        a.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{colors[name]}"/>')
for d in h["candidate_changes"].values():
    if "floor_hole_xy_d_mm" in d:
        x, y, diam = d["floor_hole_xy_d_mm"]
        px, py = top(x, y)
        a.append(
            f'<circle cx="{px}" cy="{py}" r="5" fill="white" stroke="#187b52" stroke-width="2"/>'
        )
for x, y in [
    (-86, 26),
    (131, 26),
    (-86, 70),
    (131, 80),
    (-133, 316),
    (-126, 316),
    (-76.5, 316),
    (-69.5, 316),
]:
    px, py = top(x, y)
    line(px - 4, py, px + 4, py, "#187b52", 2)
    line(px, py - 4, px, py + 4, "#187b52", 2)
text(66, 907, "Crosses: tray/OUT floor anchors; circles: guide blocks.", "small")
text(66, 929, "Routes are actual rounded paths projected into XY.", "small")
text(66, 951, "Z separation is essential where projections overlap.", "small")
text(680, 115, "OUT side section (schematic datum view)", "label")


# Y grows right, Z grows up; section is dimensioned, not CAD topology.
def sec(y, z):
    return 695 + (y - 308) * 5.7, 545 - z * 4.2


for _label, lo, sz, col in [
    ("floor", (308, 8), (111, 2), "#bec6cf"),
    ("PE allocation", (318, 16), (9, 1), "#5ca26a"),
    ("filter cover", (332, 12), (80, 50), "#eaf0f5"),
    ("bracket foot", (312, 10), (19, 5), "#929eae"),
    ("upright", (328, 15), (3, 49.5), "#929eae"),
    ("flange", (328, 64.5), (10, 3), "#929eae"),
    ("frame", (327, 67.5), (83, 2), "#607e9b"),
    ("tray", (374, 69.5), (37, 1.5), "#d4bc7c"),
    ("OUT PCB", (375, 75), (35, 1.6), "#509278"),
]:
    x, y = sec(lo[0], lo[1] + sz[1])
    rect(x, y, sz[0] * 5.7, sz[1] * 4.2, col)
text(1115, 180, "PCB underside Z75", "small")
text(1115, 202, "Tray Z69.5–71", "small")
text(690, 215, "Web bottom Z63.5", "small")
text(1115, 310, "Cover top Z62", "small")
text(705, 570, "Foot top Z15; PE bottom Z16 → 1.0 mm nominal", "small")
text(705, 594, "Upright Y328–331; PE ends 327; filter starts 332", "small")
text(705, 618, "Proposed adverse stack ≤0.60 mm; verify capability/load.", "small")
text(705, 642, "Brackets step underneath PE; the PE route stays intact.", "small")
text(680, 690, "Route and restraint data", "label")
y = 720
for name, d in h["routes"].items():
    line(685, y - 6, 711, y - 6, colors[name], 4)
    text(722, y, f"{name}: {d['length_mm']:.1f} mm jacket path; centerline bends R32", "small")
    y += 28
for t in [
    "Wire: Alpha 392240, max OD 2.8956; specified bend 10×OD.",
    "Guide candidate: OD5 / ID3.3; kink and material tests remain.",
    "Four blocks: two M2×8 joining screws each, explicit floor holes.",
    "Solder tails, boots and axial grip force require termination coupons.",
    "Proper native19 rotation; final central/PRE identities pinned in receipts.",
]:
    text(685, y + 12, t, "small")
    y += 27
text(
    40,
    1016,
    "Source of truth: CAD adapters, native-pickoffs.json, support-patterns.json, harness-probe.json and matching hash receipts.",
    "small",
)
a.append("</svg>")
(OUT / "support-harness-installation.svg").write_text("\n".join(a) + "\n")
