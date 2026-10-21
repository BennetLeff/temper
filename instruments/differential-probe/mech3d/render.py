"""Off-screen VTK renders of the printed parts and of both probes docked on stage 53.

    mech3d/.venv/bin/python mech3d/render.py            # every part + the assembly
    mech3d/.venv/bin/python mech3d/render.py lead-bridge

Uses VTK (shipped with CadQuery's OCP) with a z-buffer; no matplotlib. Writes
mech3d/renders/*.png. Parts are read from mech3d/out/*.stl; the assembly view adds
the stage-53 board outline, the bodies over 3 mm (validation/leads/stage53-bodies.txt
via geometry.json), J5/J2/C22, the leads and the reference probe boxes.
"""
import sys

import cadquery as cq
import vtk

from geometry import G, HERE, OUT, box, tube

RENDERS = HERE / "renders"
COL = {
    "Flame Retardant": (0.62, 0.70, 0.80),
    "Tough 2000": (0.85, 0.72, 0.45),
    "board": (0.20, 0.45, 0.25),
    "body": (0.72, 0.72, 0.72),
    "metal": (0.80, 0.62, 0.25),
    "tip+": (0.80, 0.12, 0.12),
    "tip-": (0.12, 0.12, 0.12),
    "box": (0.55, 0.55, 0.58),
    "litz": (0.95, 0.55, 0.10),
}


def poly_from_shape(shape, tol=0.1):
    return shape.toVtkPolyData(tol, 0.3, normals=True)


def poly_from_stl(path):
    r = vtk.vtkSTLReader()
    r.SetFileName(str(path))
    r.Update()
    n = vtk.vtkPolyDataNormals()
    n.SetInputData(r.GetOutput())
    n.SetFeatureAngle(35)
    n.ConsistencyOn()
    n.AutoOrientNormalsOn()
    n.SplittingOn()
    n.Update()
    return n.GetOutput()


def actor(poly, color, opacity=1.0):
    m = vtk.vtkPolyDataMapper()
    m.SetInputData(poly)
    m.ScalarVisibilityOff()
    a = vtk.vtkActor()
    a.SetMapper(m)
    p = a.GetProperty()
    p.SetColor(*color)
    p.SetOpacity(opacity)
    p.SetAmbient(0.25)
    p.SetDiffuse(0.8)
    p.SetSpecular(0.15)
    p.SetSpecularPower(20)
    return a


def label(ren, text, pos, size=14):
    t = vtk.vtkBillboardTextActor3D()
    t.SetInput(text)
    t.SetPosition(*pos)
    t.GetTextProperty().SetFontSize(size)
    t.GetTextProperty().SetColor(0.05, 0.05, 0.05)
    t.GetTextProperty().SetBackgroundColor(1, 1, 1)
    t.GetTextProperty().SetBackgroundOpacity(0.75)
    ren.AddActor(t)


def show(actors, out, view=(1, -1.2, 0.9), up=(0, 0, 1), title=None, labels=(), size=(1600, 1100), zoom=1.0, focal=None):
    ren = vtk.vtkRenderer()
    ren.SetBackground(1, 1, 1)
    ren.SetTwoSidedLighting(True)
    for a in actors:
        ren.AddActor(a)
    for txt, pos in labels:
        label(ren, txt, pos)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.AddRenderer(ren)
    win.SetSize(*size)
    win.SetMultiSamples(8)
    ren.ResetCamera()
    cam = ren.GetActiveCamera()
    fp = focal or cam.GetFocalPoint()
    d = cam.GetDistance()
    n = sum(v * v for v in view) ** 0.5
    cam.SetFocalPoint(*fp)
    cam.SetPosition(fp[0] + view[0] / n * d, fp[1] + view[1] / n * d, fp[2] + view[2] / n * d)
    cam.SetViewUp(*up)
    ren.ResetCamera()
    if focal:
        cam.SetFocalPoint(*focal)
    cam.Zoom(zoom)
    kit = vtk.vtkLightKit()
    kit.SetKeyLightIntensity(1.0)
    kit.AddLightsToRenderer(ren)
    if title:
        t = vtk.vtkTextActor()
        t.SetInput(title)
        t.GetTextProperty().SetFontSize(22)
        t.GetTextProperty().SetColor(0, 0, 0)
        t.SetDisplayPosition(20, size[1] - 40)
        ren.AddViewProp(t)
    win.Render()
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.ReadFrontBufferOff()
    w2i.Update()
    wr = vtk.vtkPNGWriter()
    RENDERS.mkdir(exist_ok=True)
    wr.SetFileName(str(RENDERS / f"{out}.png"))
    wr.SetInputConnection(w2i.GetOutputPort())
    wr.Write()
    print(f"renders/{out}.png")


PART_VIEWS = {
    "lead-bridge": ((0.6, -1.0, 1.4), "Lead bridge (box frame), Flame Retardant"),
    "wall-insert": ((-1.2, -0.9, 0.6), "Tip-end wall insert, reference (outside face), Flame Retardant"),
    "spine-coil": ((0.5, -1.2, 0.8), "Spine, probe 2 (coil): converging half twist, Flame Retardant"),
    "spine-bank": ((1.0, 0.6, 0.8), "Spine, probe 1 (bank), Flame Retardant"),
    "dock-coil": ((-0.9, -1.2, 1.0), "Dock, probe 2 (coil) with the J5/J2 ring guard, Flame Retardant"),
    "dock-bank": ((1.0, -1.1, 0.9), "Dock, probe 1 (bank): guide plate, risers, riser clips, TIP- clamp, Flame Retardant"),
    "trim-guide-ct": ((1, -1, 0.6), "Trimmer tool guide, CT1/CT2, Tough 2000"),
    "trim-guide-rv": ((1, -1, 0.6), "Trimmer tool guide, RV1/RV2, Tough 2000"),
    "trim-handle": ((1, -1, 0.4), "Trimmer tool handle for a Vessel CA-18 zirconia blade, Tough 2000"),
    "cal-cm-jig": ((0.9, -1.1, 1.2), "Common-mode calibration jig (stage-53 replica, contacts bused), Tough 2000"),
    "cal-dc-jig": ((0.9, -1.1, 1.2), "DC ratio jig (stage-53 replica, HI / LO split), Tough 2000"),
}


def render_part(name):
    import json

    rec = json.loads((OUT / f"{name}.json").read_text())
    view, title = PART_VIEWS[name]
    a = actor(poly_from_stl(OUT / f"{name}.stl"), COL.get(rec["resin"], COL["Flame Retardant"]))
    show([a], name, view=view, title=f"{title}  ({rec['volume_cm3']} cm3)")


def assembly():
    s53 = G["stage53"]
    W, H = s53["board"]
    actors = []
    board = box([0, -H, -s53["board_t"]], [W, 0, 0])
    actors.append(actor(poly_from_shape(board.val()), COL["board"]))
    for b in s53["bodies_over_3mm"]:
        actors.append(actor(poly_from_shape(box(b["box"]["lo"], b["box"]["hi"]).val()), COL["body"], 0.55))
    rc = s53["redcube"]
    for key in ("J5", "J2"):
        x, y, _ = s53[key]
        stud = cq.Workplane("XY").center(x, y).circle(rc["d"] / 2).extrude(s53["stack_top"])
        actors.append(actor(poly_from_shape(stud.val()), COL["metal"]))
    x, y, _ = s53["C22_hole"]
    actors.append(actor(poly_from_shape(cq.Workplane("XY").center(x, y).circle(1.5).extrude(1.0).val()), COL["metal"]))
    for k in s53["litz_keepouts"]:  # (drawn 60 mm tall; the keep-out runs to the coil)
        hi = k["box"]["hi"][:2] + [60.0]
        actors.append(actor(poly_from_shape(box(k["box"]["lo"], hi).val()), COL["litz"], 0.25))
    for h in s53["holes"]:
        x, y, _ = h["at"]
        actors.append(actor(poly_from_shape(cq.Workplane("XY").center(x, y).circle(1.6).extrude(0.3).val()), (0.1, 0.1, 0.1)))
    for l in G["leads"]:
        col = COL["tip+"] if l["name"] == "TIP+" else COL["tip-"]
        actors.append(actor(poly_from_shape(tube(l["pts"], G["wire"]["od_nom"] / 2)), col))
    for pb in G["probe_boxes"]:
        for sl in pb["extrusion_slabs"]:
            actors.append(actor(poly_from_shape(box(sl["lo"], sl["hi"]).val()), COL["box"], 0.35))
    import json

    for name in ("spine-coil", "spine-bank", "dock-coil", "dock-bank"):
        rec = json.loads((OUT / f"{name}.json").read_text())
        actors.append(actor(poly_from_stl(OUT / f"{name}.stl"), COL[rec["resin"]]))
    labels = [
        ("J5 (RES_A): both TIP+ rings", (s53["J5"][0] - 30, s53["J5"][1] + 30, 30)),
        ("J2 (COIL_FEED): probe-2 TIP-", (s53["J2"][0] - 20, s53["J2"][1] - 25, 25)),
        ("C22 free hole (SW_B): probe-1 TIP- soldered", (s53["C22_hole"][0] + 5, s53["C22_hole"][1] - 30, 12)),
        ("probe 1 (bank)", (174, 30, 95)),
        ("probe 2 (coil)", (-60, -78, 95)),
    ]
    show(actors, "assembly-docked", view=(0.55, -1.0, 0.85), title="Both probes docked on stage 53 (bench, out of the appliance); Hammond reference boxes",
         labels=labels, size=(2000, 1300), zoom=1.5)
    # Close-up of the stud and C22 region.
    show(actors, "assembly-closeup", view=(0.3, -1.0, 0.9), title="Close-up: J5/J2 ring guard, probe-1 risers either side of C22, C22 strain relief",
         labels=labels[:3], size=(2000, 1300), zoom=3.2, focal=(160, -75, 20))
    # Plan view.
    show(actors, "assembly-plan", view=(0, 0, 1), up=(0, 1, 0), title="Plan view (stage-53 frame, y up = KiCad -y)", labels=labels, size=(2000, 1400), zoom=1.1)


if __name__ == "__main__":
    names = sys.argv[1:] or list(PART_VIEWS) + ["assembly"]
    for n in names:
        if n == "assembly":
            assembly()
        elif (OUT / f"{n}.stl").exists():
            render_part(n)
