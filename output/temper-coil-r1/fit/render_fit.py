"""VTK renders for the fit study (PyVista off-screen; AGENTS/memory: CAD renders use VTK, not matplotlib 3D).

renders/fit_lug_J2_T1.png    the formed Panduit P14-8RHT6-C lugs on J2/J5 (7466004R terminals), screw stacks, the leads
                             dropping into the barrels, and CT T1's body, seen from the T1 side
renders/fit_crossing.png     the R1 winding, former and both lead exits round the J2/J5 drops, glass underside as a plane
Run: .venv/bin/python -B fit/render_fit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np  # noqa: E402
import pyvista as pv  # noqa: E402
import build123d as bd  # noqa: E402

import lug as LUG  # noqa: E402
import r1_parts as R  # noqa: E402

REN = HERE.parent / "renders"


def mesh(shape, tol=0.05):
    v, t = shape.tessellate(tol, 0.3)
    pts = np.array([(a.X, a.Y, a.Z) for a in v])
    f = np.hstack([np.full((len(t), 1), 3), np.array(t)]).ravel()
    return pv.PolyData(pts, f)


def lug_scene():
    board = list(bd.import_step(HERE / "inputs" / "board_c53int_near_J2J5.step").solids())
    p = pv.Plotter(off_screen=True, window_size=(1600, 1000))
    p.set_background("#f2f1ec")
    for s in board:
        b = s.bounding_box()
        if b.max.X < -25 or b.min.Y > 185:
            continue
        p.add_mesh(mesh(s, 0.1), color=(0.55, 0.62, 0.55), opacity=1.0)
    p.add_mesh(mesh(bd.Pos(-9, 143, 26) * bd.Box(40, 60, 1.6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))), color=(0.15, 0.35, 0.2))
    leads = R.lead_points("R1")
    for n in ("J2", "J5"):
        term = LUG.zcyl(*LUG.STUDS[n], LUG.BOARD_TOP_Z, LUG.TERMINAL["body_h"], LUG.TERMINAL["body_d"] / 2)
        p.add_mesh(mesh(term), color=(0.80, 0.78, 0.70))
        p.add_mesh(mesh(LUG.lug_solid(n)), color=(0.85, 0.30, 0.20), opacity=0.85)
        p.add_mesh(mesh(LUG.hardware_solid(n)), color=(0.65, 0.66, 0.68))
        s, _ = R.lead(leads[n], LUG.BEND_RULE_MM, n)
        clip = [x for x in s.solids() if x.bounding_box().min.Z < 75]
        p.add_mesh(mesh(bd.Compound(clip)), color=(0.93, 0.90, 0.80))
    p.camera_position = [(-75, 95, 75), (-9, 150, 38), (0, 0, 1)]
    p.add_text("J2 (front) / J5: Panduit P14-8RHT6-C formed 90 deg up, barrel outboard, PVDF shrink (red envelope); "
               "7466004R terminals; M4x8 + washers. Green: board parts (T1 is the large box). J2 shrink to T1: 1.9 mm",
               font_size=10, color="black")
    p.screenshot(REN / "fit_lug_J2_T1.png")
    p.close()


def crossing_scene():
    f, _ = R.former_world("cnc")
    w, _ = R.winding("R1")
    p = pv.Plotter(off_screen=True, window_size=(1600, 1000))
    p.set_background("#f2f1ec")
    p.add_mesh(mesh(f, 0.08), color=(0.25, 0.25, 0.27))
    p.add_mesh(mesh(w, 0.05), color=(0.80, 0.45, 0.20))
    for n, pts in R.lead_points("R1").items():
        s, _ = R.lead(pts, LUG.BEND_RULE_MM, n)
        p.add_mesh(mesh(bd.Compound([x for x in s.solids() if x.bounding_box().min.Z > 80])), color=(0.93, 0.90, 0.80))
    glass = pv.Plane(center=(-20, 190, R.Z_GLASS), direction=(0, 0, 1), i_size=120, j_size=140)
    p.add_mesh(glass, color=(0.6, 0.8, 0.9), opacity=0.25)
    p.camera_position = [(-120, 110, 160), (-25, 205, 99), (0, 0, 1)]
    p.add_text(f"R1 at bundle {R.BUNDLE} mm: centre lead (sleeved, OD {R.LEAD_OD:.2f}) over the inner turns on the -125 deg ray, "
               f"top Z{R.Z_CROSS + R.LEAD_OD / 2:.2f}, {R.Z_GLASS - R.Z_CROSS - R.LEAD_OD / 2:.2f} mm under the glass (plane)",
               font_size=10, color="black")
    p.screenshot(REN / "fit_crossing.png")
    p.close()


if __name__ == "__main__":
    REN.mkdir(exist_ok=True)
    lug_scene()
    crossing_scene()
    print("ok")
