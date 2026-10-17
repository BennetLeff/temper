"""Render an x=-35 mm YZ section from saved R4 STEP parts (millimetres)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cadquery as cq
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import baseline_engine as b  # noqa: E402 -- local CAD module needs the path above.


def main() -> None:
    catalog = {p["name"]: p for p in json.loads((ROOT / "catalog.json").read_text())}
    palette = [
        ("covered_PCB_tray_allocation", "PCB chamber walls", "#8198a5"),
        ("PCB_chamber_lid_allocation", "Shallow folded chamber roof", "#287f9b"),
        ("three_bend_front_top_rear_cover", "Formed front sheet", "#b8b5ad"),
        ("front_carrier_and_closed_sidewalls", "Hidden control carrier", "#c7853c"),
        ("front_rear_lid", "Removable control lid", "#a45b34"),
    ]
    shapes = []
    for name, label, color in palette:
        shape = cq.importers.importStep(str(ROOT / catalog[name]["file"])).val()
        shapes.append((shape, label, color))
    pcb = cq.importers.importStep(str(ROOT / "inputs/current-pcb.step")).val()
    shapes.insert(2, (b.historical_pcb_world(pcb.Solids()[-1]), "Historical PCB substrate", "#3a7450"))

    fig, ax = plt.subplots(figsize=(14, 8))
    for shape, _label, color in shapes:
        section = cq.Workplane("YZ", origin=(-35, 0, 0)).add(shape).section().val()
        for face in section.Faces():
            outside = [(v.Y, v.Z) for v in face.outerWire().Vertices()]
            if len(outside) < 3:
                continue
            ax.add_patch(Polygon(outside, closed=True, facecolor=color, edgecolor="#202d30", linewidth=1.1))
            for inside in face.innerWires():
                hole = [(v.Y, v.Z) for v in inside.Vertices()]
                if len(hole) >= 3:
                    ax.add_patch(Polygon(hole, closed=True, facecolor="white", edgecolor="#202d30", linewidth=.8))
    ax.set_xlim(15, 130)
    ax.set_ylim(15, 108)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Cooker Y (mm), front → cooking surface")
    ax.set_ylabel("Height Z (mm)")
    ax.set_title("R4 front/chamber cut at X = −35 mm — saved nominal STEP")
    ax.grid(color="#d4dedc", linewidth=.5)
    ax.legend(handles=[Patch(facecolor=color, edgecolor="#202d30", label=label) for _, label, color in [
        *palette[:2], ("", "Historical PCB substrate", "#3a7450"), *palette[2:]
    ]], loc="upper right", framealpha=.95, fontsize=9)
    fig.text(.12, .03, "The imported PCB is historical. The current native-18 full bridge and cooling duct are not represented.", fontsize=10)
    target = ROOT / "renders/r4-chamber-section.png"
    fig.savefig(target, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(target)


if __name__ == "__main__":
    main()
