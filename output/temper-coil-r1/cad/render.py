"""VTK (PyVista, off-screen) renders of the former, the printed segments, the no-printer roof build and the winding jig.
Run after former.py / jig.py: .venv/bin/python cad/render.py  -> ../renders/*.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyvista as pv

import former as F
import geom as K
import jig as J
from geom import G

ROOT = Path(__file__).resolve().parent.parent
REN = ROOT / "renders"
pv.OFF_SCREEN = True
COL = dict(g11="#d8c48a", pla="#e8e8e8", bar="#3a3a3a", cu="#b87333", ply="#d9b98c", ptfe="#f4f4f4", fr4="#9fbf7f", spare="#c040c0")


def mesh(shape, tol=0.08):
    v, t = shape.tessellate(tol, 0.3)
    pts = np.array([[p.X, p.Y, p.Z] for p in v])
    faces = np.hstack([[3, *tri] for tri in t]).astype(np.int64)
    return pv.PolyData(pts, faces)


def winding_tubes(spare=True, z=K.Z_WIND, d=G.D_BUNDLE):
    sps = K.spirals(G.R1, 0.0)
    out = []
    for sp in sps:
        out.append(pv.Spline(np.array(K.spiral_pts(sp, z, 2.0)), 2000).tube(radius=d / 2, n_sides=10))
    a, b = K.P(sps[0][1], sps[0][3], z), K.P(sps[1][0], sps[1][2], z)
    out.append(pv.Line(a, b).tube(radius=d / 2, n_sides=10))
    # centre lead (R43 route, simplified): up over the inner section at -125 deg, along the gap ring to J5, down
    s0 = K.P(sps[0][0], sps[0][2], z)
    pts = [s0, K.P(27.6, -125.0, 10.3), K.P(87.9, -125.0, 10.3), K.P(87.9, -103.5, 8.0), (K.J5[0], K.J5[1], 3.0), (K.J5[0], K.J5[1], -30.0)]
    out.append(pv.Spline(np.array(pts), 200).tube(radius=d / 2, n_sides=10))
    e = K.P(sps[1][1], sps[1][3], z)
    out.append(pv.Spline(np.array([e, (K.J2[0], K.J2[1], z), (K.J2[0], K.J2[1], -30.0)]), 100).tube(radius=d / 2, n_sides=10))
    return out


def plotter(size=(1600, 1200)):
    p = pv.Plotter(off_screen=True, window_size=size)
    p.set_background("white")
    p.enable_anti_aliasing("ssaa")
    return p


def bars_mesh():
    return [mesh(K.radial_box(phi, *G.BAR_R, G.BAR_W, *K.Z_BAR)) for phi in G.bar_angles()]


def main():
    REN.mkdir(exist_ok=True)
    body, info = F.former()
    fm = mesh(body)
    bars = bars_mesh()
    tubes = winding_tubes()
    # 1. iso of the CNC former with bars and the R1 winding
    p = plotter()
    p.add_mesh(fm, color=COL["g11"], smooth_shading=False)
    for b in bars:
        p.add_mesh(b, color=COL["bar"])
    for t in tubes:
        p.add_mesh(t, color=COL["cu"], smooth_shading=True)
    p.add_text("coil-r1 former (G11 CNC) + 10 PC95 bars + R1 winding 14.47 + 6.46 turns\nspare outer notches empty; centre lead over the inner section to J5",
               font_size=11, color="black")
    p.camera_position = [(260, -330, 260), (0, 0, 0), (0, 0, 1)]
    p.screenshot(REN / "former_R1_iso.png")
    p.close()
    # 2. top view
    p = plotter((1400, 1400))
    p.add_mesh(fm, color=COL["g11"])
    for t in tubes[:3]:
        p.add_mesh(t, color=COL["cu"])
    p.view_xy()
    p.enable_parallel_projection()
    p.add_text("top view (glass side): inner 14.47 turns pitch 3.815, outer 6.46 turns pitch 3.311 + 1 spare-notch turn", font_size=11, color="black")
    p.screenshot(REN / "former_R1_top.png")
    p.close()
    # 3. underside: bars in their channels
    p = plotter()
    p.add_mesh(fm, color=COL["g11"])
    for b in bars:
        p.add_mesh(b, color=COL["bar"])
    p.camera_position = [(200, -260, -300), (0, 0, 0), (0, 0, 1)]
    p.add_text("underside: bars 90 x 15 x 5 bonded in channels 15.2 x 5.0 x 90.2; four M3 lugs at r127", font_size=11, color="black")
    p.screenshot(REN / "former_R1_underside.png")
    p.close()
    # 4. notch close-up at the outer section
    p = plotter()
    p.add_mesh(fm, color=COL["g11"])
    for t in tubes[:3]:
        p.add_mesh(t, color=COL["cu"])
    phi = G.bar_angles()[4]
    c = K.P(108.0, phi, 7.0)
    p.camera_position = [(c[0] + 70, c[1] - 75, c[2] + 70), c, (0, 0, 1)]
    p.add_text(f"comb at the {phi:.0f} deg spoke: outer notches 2.6 wide (bundle 2.4 + 0.2), teeth 0.71; spare notch beyond the last turn",
               font_size=11, color="black")
    p.screenshot(REN / "former_R1_notch_detail.png")
    p.close()
    # 5. printed segments, exploded
    pr, _ = F.former(clearance=0.3)
    segs, _ = F.segments(pr)
    p = plotter()
    cols = ["#e6e6e6", "#cfe3f7", "#f7dccf", "#d9f2d0", "#efe0f7"]
    for j, s in enumerate(segs):
        a = np.radians(F.SEG_BOUNDS[j] + 36.0)
        m = mesh(s).translate((18 * np.cos(a), 18 * np.sin(a), 0), inplace=False)
        p.add_mesh(m, color=cols[j])
    p.camera_position = [(260, -330, 300), (0, 0, 0), (0, 0, 1)]
    p.add_text("printed route: five 72 deg segments (<= 162 x 156 mm), half-lapped rim joints, Ø3.2 pin holes (G10/bamboo pins)",
               font_size=11, color="black")
    p.screenshot(REN / "former_R1_print_segments.png")
    p.close()
    # 6. no-printer route: FR4 roof sheet on the bars, winding laid on top along the template, spacer cord alongside
    p = plotter()
    import template as TP
    from build123d import Face, Solid, Vector, Wire
    prof = [Vector(x, y, K.Z_ROOF[0]) for x, y in TP.roof_profile()]
    roof = Solid.extrude(Face(Wire.make_polygon(prof, close=True)), Vector(0, 0, 1.0)) - K.zcyl(0, 0, -1, 10, K.HUB_R[0])
    p.add_mesh(mesh(roof), color=COL["fr4"], opacity=0.85)
    for b in bars:
        p.add_mesh(b, color=COL["bar"])
    for t in winding_tubes(z=K.Z_ROOF[1] + G.D_BUNDLE / 2)[:3]:
        p.add_mesh(t, color=COL["cu"])
    p.camera_position = [(260, -330, 260), (0, 0, 0), (0, 0, 1)]
    p.add_text("no-printer route: 1.0 mm FR4 roof sheet, bars bonded beneath on the 1:1 template, turns placed by pencil ticks\n"
               "+ spacer cord, bonded with silicone along the bar lines (no comb)", font_size=11, color="black")
    p.screenshot(REN / "former_R1_no_printer.png")
    p.close()
    # 7. the jig
    parts = J.parts()
    p = plotter((1600, 1300))
    colors = {"J11_PTFE_tube_4x6": COL["ptfe"], "J7_thrust_disc_UHMW": COL["ptfe"], "J8_axle_and_spool": "#8a8a8a"}
    for name, s in parts.items():
        p.add_mesh(mesh(s, 0.3), color=colors.get(name, COL["ply"]), show_edges=False)
    p.add_mesh(fm, color=COL["g11"])
    for b in bars:
        p.add_mesh(b, color=COL["bar"])
    for t in tubes[:3]:
        p.add_mesh(t, color=COL["cu"])
    p.camera_position = [(900, -900, 450), (0, 150, -150), (0, 0, 1)]
    p.add_text("winding jig: wooden turntable (no metal within ~150 mm of the coil), PTFE wire eye on a radial slide,\n"
               "felt-braked spool stand 0.6 m away, centring boss + lead mast, 10 deg ticks + pointer", font_size=11, color="black")
    p.screenshot(REN / "jig_assembly.png")
    p.close()
    print("renders:", sorted(x.name for x in REN.glob("*.png")))


if __name__ == "__main__":
    sys.exit(main())
