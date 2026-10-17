"""Draw bounding allocations for review; STEP is the solid-intersection authority."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "output/temper-prototype-closure/cooling"


def main() -> None:
    report = json.loads((OUT / "checks.json").read_text())
    board = report["part_bounds_mm"]["native18_BARE_BOARD"]
    board_width, board_depth = board[3] - board[0], board[4] - board[1]
    board_x, board_y = report["board_transform"]["origin_xy"]
    board_top_z = report["board_transform"]["top_z"]
    figure, (top, section) = plt.subplots(
        1, 2, figsize=(14, 7), gridspec_kw={"width_ratios": [1, 1.35]}
    )
    top.add_patch(Rectangle((-185, 0), 370, 440, fill=False, lw=2, color="#333333"))
    for name, bounds in report["part_bounds_mm"].items():
        x, y, z, xx, yy, zz = bounds
        if name.startswith("native18_"):
            color, alpha = ("#287c5d", 0.12) if name.endswith("BARE_BOARD") else ("#246c61", 0.3)
        elif "SINK" in name:
            color, alpha = "#d77923", 0.2
        elif "EMI" in name:
            color, alpha = "#62539b", 0.4
        else:
            color, alpha = "#5898cb", 0.25
        top.add_patch(Rectangle((x, y), xx - x, yy - y, color=color, alpha=alpha, lw=0.3))
        if x <= -12.5 <= xx and (
            name.startswith("CUSTOM_")
            or name.startswith("native18_Q5")
            or name.endswith("BARE_BOARD")
        ):
            section.add_patch(Rectangle((y, z), yy - y, zz - z, color=color, alpha=0.5, lw=0.4))
    top.scatter(
        [-157, 157, -157, 157], [190, 190, 330, 330], color="#333333", s=40, label="R4 support legs"
    )
    top.add_patch(
        Rectangle(
            (-19, 242), 38, 38, fill=False, edgecolor="#aa3344", lw=2, label="Sensor overhead"
        )
    )
    top.annotate("200 mm custom sink", (0, 125), ha="center", fontsize=9)
    top.annotate(
        f"native18: {board_width:g} x {board_depth:g}\norigin ({board_x:g}, {board_y:g})",
        (8, 270),
        ha="center",
        fontsize=10,
    )
    top.annotate(
        "D22 body allocation\nupstream hardware absent", (-85, 373), ha="center", fontsize=8
    )
    top.annotate(
        "Right-to-left flow\nrear duct not solved",
        (125, 105),
        xytext=(155, 55),
        ha="center",
        fontsize=8,
        arrowprops={"arrowstyle": "->"},
    )
    top.set(
        xlim=(-195, 195),
        ylim=(445, -5),
        xlabel="R4 X / mm",
        ylabel="R4 Y / mm",
        title="Top view; component boxes are projected bounds",
    )
    top.set_aspect("equal")
    top.legend(loc="lower center", fontsize=8)
    section.add_patch(
        Rectangle((160.5, 28), 2.015, 6, facecolor="white", edgecolor="#999999", lw=0.5)
    )
    section.axhline(board_top_z, color="#287c5d", ls="--", lw=0.7)
    section.annotate(f"PCB top Z{board_top_z:g}", (190, board_top_z), xytext=(190, 23), fontsize=9)
    section.annotate(
        "1 mm ceramic at modeled rear face\nnot verified manufacturer metallization",
        (163, 46),
        xytext=(178, 70),
        fontsize=9,
        arrowprops={"arrowstyle": "->"},
    )
    section.annotate(
        "Board-height base relief",
        (161.5, 31),
        xytext=(95, 3),
        fontsize=9,
        arrowprops={"arrowstyle": "->"},
    )
    section.set(
        xlim=(88, 230),
        ylim=(0, 88),
        xlabel="R4 Y / mm",
        ylabel="R4 Z / mm",
        title="Q5 section: fin / base / ceramic / device / board",
    )
    section.set_aspect("equal")
    section.grid(alpha=0.15)
    figure.suptitle(
        "COLD CONTACT STUDY — thermal, duct, clamp and insulation qualification OPEN", fontsize=13
    )
    figure.tight_layout()
    figure.savefig(OUT / "contact-study.png", dpi=140)
    figure.savefig(OUT / "contact-study.svg")


if __name__ == "__main__":
    main()
