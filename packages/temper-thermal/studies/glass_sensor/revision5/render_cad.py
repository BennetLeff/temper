"""Render head geometry directly from exported STEP; glass and large housing hidden."""

from __future__ import annotations

from pathlib import Path

import cadquery as cq
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parent


def main() -> None:
    fig = plt.figure(figsize=(11, 5.5), layout="constrained")
    clip = cq.Workplane("XY").box(12, 12, 5.3).translate((0, 0, -1.75)).val()
    for slot, variant in enumerate(["D8", "D6"], 1):
        ax = fig.add_subplot(1, 2, slot, projection="3d")
        shape = cq.importers.importStep(str(ROOT / "mechanical" / f"R5-{variant}-rest.step")).val()
        for solid in shape.Solids():
            bounds = solid.BoundingBox()
            if bounds.zmax < -4.4 or bounds.xlen > 13 or bounds.ylen > 13:
                continue
            section = solid.intersect(clip)
            if section.Volume() < 1e-9:
                continue
            vertices, faces = section.tessellate(0.065, 0.14)
            points = [(v.x, v.y, v.z) for v in vertices]
            triangles = [[points[i] for i in face] for face in faces]
            color = "#b97748" if bounds.zmax > 0.59 else "#bbc5c3"
            if bounds.xlen < 2 and bounds.zlen < 2:
                color = "#567f85"
            collection = Poly3DCollection(triangles, facecolor=color, edgecolor="none", alpha=0.94)
            ax.add_collection3d(collection)
        ax.set(xlim=(-4.8, 4.8), ylim=(-4.8, 4.8), zlim=(-4.4, 0.9))
        ax.set_box_aspect((1, 1, 0.57))
        ax.view_init(elev=24, azim=-55)
        ax.set_axis_off()
        ax.set_title(f"{variant[1:]} mm face · exported STEP", fontsize=14)
    fig.suptitle("R5 cartridge head comparison", fontsize=18)
    fig.supxlabel(
        "Geometry only · glass and large housing hidden · view cropped below −4.4 mm", fontsize=11
    )
    fig.savefig(ROOT / "cad-heads.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
