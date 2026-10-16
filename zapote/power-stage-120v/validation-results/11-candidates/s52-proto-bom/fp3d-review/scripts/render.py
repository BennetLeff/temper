"""VTK (PyVista off-screen) renders of the s52 bank column and the L1 / C3 / C4 inlet area from the chain's board.step.
Solids are tessellated with OCP, moved to board-local (x right, y down -> rendered as y up via -y, z up), attributed to a
part by the smallest courtyard containing the solid's XY centre (as body_collisions.py).
usage: python render.py BOARD.step COURTYARDS.json FPDUMP.json FITMARK.json OUTDIR"""
import json, sys
import numpy as np
import pyvista as pv
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopoDS import TopoDS

step, crtp, fpp, fmp, outd = sys.argv[1:6]
crt = json.load(open(crtp)); fpd = json.load(open(fpp)); fm = json.load(open(fmp))
rd = STEPControl_Reader(); assert rd.ReadFile(step) == 1; rd.TransferRoots(); shape = rd.OneShape()

REG = {"bank": (150, 24, 264, 128), "inlet": (150, 24, 264, 128)}
ROI = (148, 18, 272, 130)

def owner(cx, cy):
    best = None
    for r, c in crt.items():
        if c[0] <= cx <= c[2] and c[1] <= cy <= c[3]:
            a = (c[2] - c[0]) * (c[3] - c[1])
            if best is None or a < best[1]:
                best = (r, a)
    return best[0] if best else None

def mesh_solid(s):
    BRepMesh_IncrementalMesh(s, 0.15, False, 0.3, True)
    pts, faces, off = [], [], 0
    ex = TopExp_Explorer(s, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face_s(ex.Current()); loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is not None:
            tr = loc.Transformation()
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(tr); pts.append((p.X(), -p.Y(), p.Z()))
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get(); faces += [3, a - 1 + off, b - 1 + off, c - 1 + off]
            off += tri.NbNodes()
        ex.Next()
    return pv.PolyData(np.array(pts), np.array(faces)) if pts else None

parts = []
ex = TopExp_Explorer(shape, TopAbs_SOLID)
while ex.More():
    s = ex.Current(); bb = Bnd_Box(); BRepBndLib.Add_s(s, bb)
    lo, hi = bb.CornerMin(), bb.CornerMax()
    x0, x1, y0, y1 = lo.X(), hi.X(), -hi.Y(), -lo.Y()
    big = (x1 - x0) * (y1 - y0) > 30000 and hi.Z() - lo.Z() < 2
    if not big and x1 > ROI[0] and x0 < ROI[2] and y1 > ROI[1] and y0 < ROI[3]:
        m = mesh_solid(s)
        if m is not None:
            parts.append((owner((x0 + x1) / 2, (y0 + y1) / 2), m))
    ex.Next()
print("solids in ROI:", len(parts))

COL = {"bank": "#3b6fd8", "L1": "#e08a1e", "C3": "#d23c3c", "C4": "#d23c3c"}
BANK = {"C21", "C22", "C23", "C151", "C152"}
def colour(r):
    if r in BANK: return COL["bank"]
    return COL.get(r, "#9a9a9a")

def scene(region, view, out):
    x0, y0, x1, y1 = region
    p = pv.Plotter(off_screen=True, window_size=(1600, 1200)); p.set_background("white")
    T = 1.653
    p.add_mesh(pv.Box(bounds=(x0, x1, -y1, -y0, 0, T)), color="#2f6b3a", opacity=1.0)
    for r, m in parts:
        mm_ = m.copy(); mm_.points[:, 1] *= -1  # board-local y down -> render y up
        grey = colour(r) == "#9a9a9a"
        p.add_mesh(mm_, color=colour(r), smooth_shading=False, show_edges=False,
                   opacity=(0.55 if r in BANK else 1.0) if view == "top" else (0.22 if grey else 1.0))
    # pads: fitted holes gold, the unused 27.5 mm holes magenta
    for ref, d in fpd.items():
        for pd in d["pads"]:
            unused = ref in BANK and abs(pd["x"] - (d["x"] + 27.5)) < 0.01
            cyl = pv.Cylinder(center=(pd["x"], -pd["y"], T + 0.05), direction=(0, 0, 1), radius=pd["size"][0] / 2, height=0.12)
            p.add_mesh(cyl, color="#ff00ff" if unused else "#d4af37")
    # fit mark outline (F.SilkS block bbox)
    u = fm["mark_union_bbox"]
    p.add_mesh(pv.Box(bounds=(u[0], u[2], -u[3], -u[1], T, T + 0.05)), color="white")
    for it in fm["items"]:
        b = it["bbox"]
        p.add_mesh(pv.Box(bounds=(b[0], b[2], -b[3], -b[1], T + 0.05, T + 0.1)), color="#bbbbbb", style="wireframe", line_width=1)
    labels, lp = [], []
    for ref, d in fpd.items():
        cx = d["x"] + (11.25 if ref in BANK else 0)
        if ref == "L1": cx, cy, cz = 237.0, 43.5, 45
        elif ref in ("C3", "C4"): cx, cy, cz = 220.0, d["y"], 17
        else: cy, cz = d["y"], 33
        lp.append((cx, -cy, cz)); labels.append(ref + " " + d["value"])
    p.add_point_labels(np.array(lp), labels, font_size=14, point_size=1, shape_opacity=0.6, always_visible=True)
    cx, cy = (x0 + x1) / 2, -(y0 + y1) / 2
    if view == "top":
        p.camera_position = [(cx, cy, 400), (cx, cy, 0), (0, 1, 0)]; p.enable_parallel_projection()
        p.camera.parallel_scale = max(x1 - x0, y1 - y0) * 0.55
    else:
        p.camera_position = [(cx + 150, cy - 120, 150), (cx, cy, 10), (0, 0, 1)]
    p.add_text(out.split("/")[-1], font_size=10, color="black")
    p.screenshot(out); p.close()

scene(REG["bank"], "top", f"{outd}/bank.png")
scene(REG["inlet"], "oblique", f"{outd}/inlet.png")
