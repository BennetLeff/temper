#!/usr/bin/env python3
"""Body-envelope packing study, not copper, clearance or insulation approval."""

import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
# x, y, width, depth in mm. Capacitor/choke bodies follow PARTS.md;
# resistor groups are explicit planning allowances, not package dimensions.
BODIES = {
    "20 A choke": (7, 7, 45, 25.5),
    "2.2 µF X2": (7, 42, 26.5, 14.5),
    "4.7 µF X2": (62, 5, 31.5, 21),
    "4.7 µF damping X2": (62, 31, 31.5, 21),
    "Y 4.7 nF L": (38, 42, 13, 5),
    "Y 4.7 nF N": (38, 51, 13, 5),
    "Y 2.2 nF L": (62, 61, 13, 4),
    "Y 2.2 nF N": (80, 61, 13, 4),
    "damper allowance": (7, 64, 20, 10),
    "bleed pair allowance": (32, 64, 25, 10),
}


def main():
    for x, y, w, h in BODIES.values():
        assert 0 <= x and x + w <= 110 and 0 <= y and y + h <= 80
    items = list(BODIES.items())
    for i, (name, (x, y, w, h)) in enumerate(items):
        for other, (u, v, a, b) in items[i + 1 :]:
            overlap = max(0, min(x + w, u + a) - max(x, u)) * max(0, min(y + h, v + b) - max(y, v))
            assert overlap == 0, (name, other)
    report = {
        "module_mm": [110, 80, 50],
        "local_body_boxes_xywh_mm": BODIES,
        "body_overlap_area_mm2": 0,
        "maximum_part_height_mm": 41,
        "height_allocation_mm": {
            "choke": 41,
            "carrier": 1.6,
            "underside_standoff_and_pins": 3,
            "cover_and_clearance_allowance": 4.4,
        },
        "qualification": "packing reservation only; terminals, wiring, creepage, clearance, PE geometry and mounting still require final assembly design",
    }
    (HERE / "module-plan.json").write_text(json.dumps(report, indent=2) + "\n")
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.add_patch(Rectangle((0, 0), 110, 80, fill=False, edgecolor="#234", linewidth=2))
    for name, (x, y, w, h) in BODIES.items():
        color = "#387a78" if "allowance" not in name else "#9a774d"
        ax.add_patch(Rectangle((x, y), w, h, facecolor=color, alpha=0.2, edgecolor=color))
        label = name.replace(" damping", "\ndamping").replace(" allowance", "\nallowance")
        ax.text(
            x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=7 if "Y " in name else 8
        )
    ax.text(101, 40, "terminal /\nwiring\nspace", rotation=90, ha="center", va="center", fontsize=8)
    ax.set(
        xlim=(-3, 113),
        ylim=(83, -3),
        xlabel="Module x (mm)",
        ylabel="Module y (mm)",
        title="D-22 body packing — 110 × 80 mm, 50 mm overall height\nReservation only; electrical and mechanical layout unqualified",
    )
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(HERE / "module-plan.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
