"""CAD preview of the TE STRATO-THERM 50840-class ring lug on the coil Litz and an M4 stud. A MOCK-UP, not a vendor model.

Dimensions
  from TE's datasheet (50840-1, the #10 sibling; read 2026-10-19): tongue thickness 0.79, overall length 21.8,
    compatible wire-insulation diameter 2.03-3.81, barrel type closed, partially insulated (PTFE).
  from RS's listing of the white 50840 (not TE): ring outer diameter 8.71.
  ASSUMED (not published in what was read; marked A): ring hole 4.3, conductor barrel OD 3.4 and length 6.0,
    PTFE sleeve OD 4.6 and length 6.0; overall length taken from the ring's outer edge. Replace with TE's drawing before anyone relies on a fit.
Litz: 2.55 OD served bundle (RM Cybernetics 1000 x 0.05), stripped 12 mm, strands 2.0 dia in the barrel.
Writes cad/out/lug_50840_mock.step and renders/lug_50840_mock.png.   Run: python cad/lug_mock.py
"""
from pathlib import Path
import numpy as np
import pyvista as pv
from build123d import Align, Axis, Box, Circle, Cylinder, Location, Pos, Rot, extrude, Plane, Sketch, export_step, Compound, Rectangle, make_face, Polyline

HERE = Path(__file__).resolve().parent
T = 0.79                       # tongue thickness (TE)
L_ALL = 21.8                   # overall length (TE)
RING_OD, RING_ID = 8.71, 4.3   # OD (RS), hole (A)
BAR_OD, BAR_L = 3.4, 6.0       # conductor barrel (A)
SLV_OD, SLV_L = 4.6, 6.0       # PTFE insulation support (A)
LITZ_OD, STRIP = 2.55, 12.0

x0 = -RING_OD / 2              # ring outer edge
x_end = x0 + L_ALL             # rear end of the sleeve
z_c = T / 2                    # axis height of the barrel (rolled from the tongue)

# ring + neck, flat in XY
ring = Cylinder(RING_OD / 2, T, align=(Align.CENTER, Align.CENTER, Align.MIN))
neck_len = x_end - SLV_L - BAR_L
neck = Pos(0, 0, 0) * Box(neck_len + RING_OD / 2 + 1.0, 3.4, T, align=(Align.MIN, Align.CENTER, Align.MIN))
lug = ring + neck
lug = lug - Cylinder(RING_ID / 2, T * 3, align=(Align.CENTER, Align.CENTER, Align.CENTER))
# conductor barrel (nickel) and PTFE sleeve, tube along +X
x_bar0 = x_end - SLV_L - BAR_L
barrel = Pos(x_bar0, 0, z_c) * Rot(0, 90, 0) * (Cylinder(BAR_OD / 2, BAR_L, align=(Align.CENTER, Align.CENTER, Align.MIN)))
barrel = barrel - Pos(x_bar0, 0, z_c) * Rot(0, 90, 0) * Cylinder(LITZ_OD * 0.78 / 2, BAR_L + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
sleeve = Pos(x_end - SLV_L, 0, z_c) * Rot(0, 90, 0) * Cylinder(SLV_OD / 2, SLV_L, align=(Align.CENTER, Align.CENTER, Align.MIN))
sleeve = sleeve - Pos(x_end - SLV_L, 0, z_c) * Rot(0, 90, 0) * Cylinder(LITZ_OD / 2, SLV_L + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
# Litz: stripped strands through the barrel, served bundle in the sleeve and beyond
strands = Pos(x_end - SLV_L - BAR_L - 1.0, 0, z_c) * Rot(0, 90, 0) * Cylinder(LITZ_OD * 0.78 / 2, STRIP + 1.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
bundle = Pos(x_end - SLV_L - BAR_L - 1.0 + STRIP, 0, z_c) * Rot(0, 90, 0) * Cylinder(LITZ_OD / 2, 22, align=(Align.CENTER, Align.CENTER, Align.MIN))
# M4 stud, washer-free, 12 mm
stud = Pos(0, 0, -6.0) * Cylinder(2.0, 14, align=(Align.CENTER, Align.CENTER, Align.MIN))
parts = [("lug_nickel", lug + barrel, (0.62, 0.64, 0.66)), ("ptfe_sleeve", sleeve, (0.93, 0.93, 0.90)),
         ("litz_strands", strands, (0.75, 0.42, 0.18)), ("litz_served", bundle, (0.20, 0.25, 0.40)), ("m4_stud", stud, (0.35, 0.35, 0.37))]
export_step(Compound([p[1] for p in parts]), str(HERE / "out" / "lug_50840_mock.step"))


def mesh(shape, tol=0.01):
    v, t = shape.tessellate(tol, 0.2)
    pts = np.array([(a.X, a.Y, a.Z) for a in v])
    f = np.hstack([np.full((len(t), 1), 3), np.array(t)]).ravel()
    return pv.PolyData(pts, f)


def shot(out, view, title, clip=False):
    p = pv.Plotter(off_screen=True, window_size=(1500, 900))
    p.set_background("#f2f1ec")
    for name, s, col in parts:
        if clip:
            s = s & (Pos(0, -50, 0) * Box(200, 100, 200, align=(Align.CENTER, Align.CENTER, Align.CENTER)) )
            # keep y <= z-axis plane through the barrel axis
        m = mesh(s)
        p.add_mesh(m, color=col, smooth_shading=False)
    p.camera_position = view
    p.add_text(title, font_size=10, position="upper_left", color="black")
    p.screenshot(out)


R = HERE.parent / "renders"
R.mkdir(exist_ok=True)
shot(str(R / "lug_50840_mock.png"), [(30, -30, 22), (6, 0, 1), (0, 0, 1)],
     "TE STRATO-THERM 50840-class ring lug on 2.55 mm Litz, M4 stud. Mock-up: TE length/thickness, RS ring OD; barrel, sleeve, hole ASSUMED")
shot(str(R / "lug_50840_mock_section.png"), [(4, -40, 6), (6, 0, 1), (0, 0, 1)],
     "Half section: stripped strands in the barrel, served bundle in the PTFE sleeve", clip=True)
print("ok", x0, x_end)
