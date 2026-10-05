"""Plot the JSON envelope studies; 2D projection is not a collision test."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Patch, Rectangle

HERE = Path(__file__).resolve().parent


def main() -> None:
    data = json.loads((HERE / "envelopes.json").read_text())
    checks = json.loads((HERE / "checks.json").read_text())
    counts = {c["id"]: len(c["hits_against_included_r4_parts"]) for c in checks["cases"]}
    colors = {"board": "#31886b", "sink": "#da8730", "fan": "#b14d4d", "EMI": "#786eb0"}
    fig, axes = plt.subplots(1, 4, figsize=(16, 6.7), sharex=True, sharey=True)
    titles = ["Rear bay: foot collisions", "Rear edge: sensor conflict",
              "Rear bay shifted: SPACE ONLY", "Front edge: control conflicts"]
    for ax, case, title in zip(axes, data["cases"], titles, strict=True):
        ax.add_patch(Rectangle((-185, 0), 370, 440, fill=False, lw=2, edgecolor="#354451"))
        ax.add_patch(Rectangle((-123, 61.5), 265, 177, fill=False, ls="--", edgecolor="#6a7680"))
        ax.add_patch(Circle((0, 261), 100, fill=False, ls=":", edgecolor="#767676"))
        ax.add_patch(Circle((0, 261), 19, color="#354451", alpha=.7))
        for x in (-157, 157):
            for y in (190, 330):
                ax.add_patch(Circle((x, y), 6, color="#354451"))
        for x in (-145, 145):
            ax.plot(x, 404, "+", color="#354451", markersize=8)
        for entry in case["boxes"]:
            name = entry["name"]
            kind = "board" if "OUTLINE" in name else "EMI" if "D22" in name else "fan" if "FAN" in name else "sink"
            x, y, _ = entry["min"]
            w, d, _ = entry["size"]
            ax.add_patch(Rectangle((x, y), w, d, facecolor=colors[kind], edgecolor=colors[kind], alpha=.55))
        ax.set_title(title + "\n" + str(counts[case["id"]]) + " 3D intersections", fontsize=10, pad=12)
        ax.set_aspect("equal")
        ax.set_xlim(-200, 200)
        ax.set_ylim(-10, 450)
        ax.set_xlabel("X / mm")
        ax.grid(alpha=.15)
    axes[0].set_ylabel("Y / mm  (front at 0, rear at 440)")
    fig.suptitle("Temper R4 + native-18: packaging probes, NOT an integrated design", fontsize=16, y=.99)
    fig.legend(handles=[Patch(facecolor=color, label=kind) for kind, color in colors.items()], loc="lower center", ncol=4, bbox_to_anchor=(.5, .12))
    fig.text(.5, .07, "Gray: retained chamber, sensor, support legs and foot bolts. Dotted circle: elevated coil. Projection overlap is not a solid collision.", ha="center", fontsize=9)
    fig.text(.5, .035, "Rear candidate has NO heat path to the board. Bare PCB only; guards, brackets, duct turns, fan supply and harness are absent.", ha="center", fontsize=10, weight="bold")
    fig.subplots_adjust(top=.88, bottom=.24, left=.055, right=.99, wspace=.18)
    fig.savefig(HERE / "packaging-probes.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
