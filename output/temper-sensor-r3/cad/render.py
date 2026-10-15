"""Off-screen VTK (PyVista) renders of the C1 cartridge in its R43 context. Not matplotlib: VTK has a z-buffer.

Writes render.png (half section at rest with glass, carrier and coil) and render-flush.png (half section with the
disc pushed flush, travel 0.60, a pan's working position). Run: python render.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyvista as pv
from build123d import Box, Pos

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import cartridge_r3 as C  # noqa: E402
import interfaces as IF  # noqa: E402


def mesh(shape, tol=0.02):
    verts, tris = shape.tessellate(tol, 0.3)
    pts = np.array([(v.X, v.Y, v.Z) for v in verts])
    faces = np.hstack([np.full((len(tris), 1), 3), np.array(tris)]).ravel()
    return pv.PolyData(pts, faces)


def cut(shape, x_keep_max=0.0, span=60.0):
    """Keep x <= 0 within a local box round the sensor axis."""
    keep = Pos(C.SX - span / 2, C.SY, 92) * Box(span, 2 * span, 70)
    return shape & keep


def scene(travel, title, out):
    ctx = IF.context()
    p = pv.Plotter(off_screen=True, window_size=(1700, 1250))
    p.set_background("#f2f1ec")
    for name, shape, color, opacity in [("glass", ctx["glass"], (0.10, 0.12, 0.13), 0.55),
                                        ("carrier", ctx["carrier"], (0.72, 0.77, 0.68), 1.0),
                                        ("former", ctx["former"], (0.45, 0.47, 0.42), 1.0),
                                        ("winding", ctx["winding"], (0.73, 0.44, 0.20), 1.0),
                                        ("ferrite", ctx["ferrite"], (0.25, 0.25, 0.27), 1.0)]:
        s = cut(shape)
        if s is not None and s.solids():
            p.add_mesh(mesh(s, 0.05), color=color, opacity=opacity, smooth_shading=False)
    for part in C.half_section(C.r3_cartridge(travel)):
        p.add_mesh(mesh(part["shape"]), color=part["color"][:3], smooth_shading=False,
                   show_edges=False)
    p.camera.position = (120, 150, 135)
    p.camera.focal_point = (0, 261, 96)
    p.camera.up = (0, 0, 1)
    p.camera.view_angle = 22
    p.add_text(title, position="upper_left", font_size=12, color="#28352f")
    p.screenshot(str(out))
    p.close()


def main():
    scene(0.0, "sensor-r3 C1 cartridge, half section at rest (disc 0.60 proud). Glass translucent; carrier, coil former, Litz, ferrite.",
          HERE / "render.png")
    scene(C.DIM["proud"], "C1 at travel 0.60 (pan holds the disc flush): Si3N4 disc, Vespel post/body, FFKM wiper, PEEK cup/washer, A-286 spring",
          HERE / "render-flush.png")


if __name__ == "__main__":
    main()
