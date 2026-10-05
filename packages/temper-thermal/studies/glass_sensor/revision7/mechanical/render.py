"""Presentation only: tessellate the issued STEP into labeled coupon cutaways."""

from pathlib import Path

import cadquery as cq
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parent
fig = plt.figure(figsize=(15, 6), layout="constrained")
for slot, variant in enumerate(["M222_control_010", "M222_thin_0075", "IST308_thin_0075"], 1):
    ax = fig.add_subplot(1, 3, slot, projection="3d")
    # Clip away positive-x half; retain centerline sensor section and rear joins.
    clip = cq.Workplane("XY").box(5, 10, 4).translate((-2.5, 0, -1.3)).val()
    shape = cq.importers.importStep(str(ROOT / f"R7-{variant}-rest.step")).val()
    for solid in shape.Solids():
        bounds = solid.BoundingBox()
        if bounds.zmax < -3.3 or bounds.xlen > 13 or bounds.ylen > 13:
            continue
        section = solid.intersect(clip)
        if section.Volume() < 1e-8:
            continue
        vertices, faces = section.tessellate(0.04, 0.12)
        points = [(v.x, v.y, v.z) for v in vertices]
        triangles = [[points[i] for i in face] for face in faces]
        color = "#c0804c" if bounds.zmax > 0.59 else "#b3bcc5"
        if bounds.zlen < 1.21 and bounds.xlen < 3.5 and bounds.ylen < 3.5:
            color = "#326b7a"
        ax.add_collection3d(
            Poly3DCollection(triangles, facecolor=color, edgecolor="none", alpha=0.95)
        )
    ax.set(xlim=(-4.5, 0.5), ylim=(-4.5, 4.5), zlim=(-3.3, 0.7))
    ax.set_box_aspect((0.6, 1, 0.55))
    ax.view_init(elev=18, azim=35)
    ax.set_axis_off()
    title = {
        "M222_control_010": "M222 · 0.100 mm bond",
        "M222_thin_0075": "M222 · 0.075 mm bond",
        "IST308_thin_0075": "IST308 · 0.075 mm bond",
    }[variant]
    ax.set_title(title, fontsize=14)
fig.suptitle("R7 experimental D6 coupons — cutaway from exported STEP", fontsize=18)
fig.supxlabel(
    "Face roof 0.15 mm · full cartridge STEP includes four 60 mm routes · nominal geometry only\nTrimmed native leads; pad pitch, film orientation, bond process and forming remain unqualified",
    fontsize=11,
)
fig.savefig(ROOT / "coupon-cutaways.png", dpi=170)
plt.close(fig)
