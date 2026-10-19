"""3D sector mesh (gmsh OCC) for the discrete-bar cross-check of the axisymmetric model.

One 18 deg wedge = half of one 36 deg bar pitch: phi = 0 is a bar centre-plane, phi = 18 deg the mid-gap plane.
The winding is two annular sections with uniform azimuthal current (the same source as the 2D 'smeared' run, so the
3D/2D ratio isolates the bar homogenisation). Both cut planes are mirror planes of the geometry that the azimuthal
current crosses at right angles, so B . n = 0 there (n x A = 0: AV {e} = 0). Units: mm (ElmerGrid -scale 0.001).

Physical groups
  volumes : 1 air, 2 bar, 3 coil_inner, 4 coil_outer
  surfaces: 1 outer boundary, 2 cut plane phi=0, 3 cut plane phi=18, 4 pan surfaces (pan cases: the pan is a hole
            with a surface-impedance boundary)
Run: .venv/bin/python model/fem3d/build_mesh.py NAME [--pan] [--h SCALE]   -> model/fem3d/meshes/NAME.msh
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import gmsh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import coil_geometry as G  # noqa: E402

TH = math.radians(18.0)
R_OUT, Z_LO, Z_HI = 600.0, -400.0, 600.0
SIDE = G.D_BUNDLE * math.sqrt(math.pi) / 2
PAN_R, PAN_T = 120.0, 1.0


def build(name, pan=False, h=1.0, winding=G.R43):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add(name)
    occ = gmsh.model.occ
    dom = occ.addCylinder(0, 0, Z_LO, 0, 0, Z_HI - Z_LO, R_OUT, angle=TH)
    # half bar: x along the bar axis (phi = 0), y in [0, w/2]
    bar = occ.addBox(G.BAR_R[0], 0.0, G.Z_BAR[0], G.BAR_R[1] - G.BAR_R[0], G.BAR_W / 2, G.Z_BAR[1] - G.Z_BAR[0])
    zc = winding.z_c
    secs = []
    for s in winding.sections:
        o = occ.addCylinder(0, 0, zc - SIDE / 2, 0, 0, SIDE, s.r1, angle=TH)
        i = occ.addCylinder(0, 0, zc - SIDE / 2, 0, 0, SIDE, s.r0, angle=TH)
        ring, _ = occ.cut([(3, o)], [(3, i)])
        secs.append(ring[0][1])
    tools = [(3, bar)] + [(3, t) for t in secs]
    if pan:
        hole = occ.addCylinder(0, 0, G.PAN_Z0, 0, 0, PAN_T, PAN_R, angle=TH)
        cut, _ = occ.cut([(3, dom)], [(3, hole)])
        dom = cut[0][1]
    out, omap = occ.fragment([(3, dom)], tools)
    occ.synchronize()
    vols = [t for d, t in gmsh.model.getEntities(3)]

    def com(t):
        return occ.getCenterOfMass(3, t)
    cls = {"air": [], "bar": [], "coil_inner": [], "coil_outer": []}
    for t in vols:
        x, y, z = com(t)
        r = math.hypot(x, y)
        if G.Z_BAR[0] <= z <= G.Z_BAR[1] and y < G.BAR_W / 2 + 1e-6 and G.BAR_R[0] < r < G.BAR_R[1] + 5 and occ.getMass(3, t) < 1e4:
            cls["bar"].append(t)
        elif abs(z - zc) < SIDE and r < winding.sections[0].r1 + 1 and occ.getMass(3, t) < 2e4:
            cls["coil_inner"].append(t)
        elif abs(z - zc) < SIDE and r > winding.sections[1].r0 - 1 and occ.getMass(3, t) < 2e4:
            cls["coil_outer"].append(t)
        else:
            cls["air"].append(t)
    for i, k in enumerate(("air", "bar", "coil_inner", "coil_outer"), start=1):
        assert len(cls[k]) == 1, (k, cls[k])
        gmsh.model.addPhysicalGroup(3, cls[k], i, name=k)
    # boundary classification
    surf = {1: [], 2: [], 3: [], 4: []}
    for d, t in gmsh.model.getBoundary([(3, cls["air"][0])], oriented=False):
        x, y, z = occ.getCenterOfMass(2, t)
        r, ph = math.hypot(x, y), math.atan2(y, x)
        if abs(y) < 1e-6 and abs(occ.getCenterOfMass(2, t)[1]) < 1e-6 and _planar(t, 0.0):
            surf[2].append(t)
        elif _planar(t, TH):
            surf[3].append(t)
        elif abs(r - R_OUT) < 1e-3 or abs(z - Z_LO) < 1e-3 or abs(z - Z_HI) < 1e-3:
            surf[1].append(t)
        elif pan and G.PAN_Z0 - 1e-6 <= z <= G.PAN_Z0 + PAN_T + 1e-6 and r <= PAN_R + 1e-6:
            surf[4].append(t)
    # cut-plane faces of the bar and coil bodies too (they also touch the symmetry planes)
    for k in ("bar", "coil_inner", "coil_outer"):
        for d, t in gmsh.model.getBoundary([(3, cls[k][0])], oriented=False):
            if _planar(t, 0.0) and t not in surf[2]:
                surf[2].append(t)
            elif _planar(t, TH) and t not in surf[3]:
                surf[3].append(t)
    for k, v in surf.items():
        if v:
            gmsh.model.addPhysicalGroup(2, sorted(set(v)), k)
    # sizes
    f = gmsh.model.mesh.field
    boxes = [
        (0, 130, -5, 50, 88, 116, 2.4 * h),            # near zone
        (25, 122, -2, 30, 98.6, 101.8, 0.9 * h),       # winding layer
        (28, 121, -1, 9, 92.6, 98.4, 1.0 * h),         # bar
        (0, 130, -5, 50, 108.5, 112.5, 1.6 * h),       # pan face
    ]
    ids = []
    for x0, x1, y0, y1, z0, z1, v in boxes:
        b = f.add("Box")
        f.setNumber(b, "XMin", x0); f.setNumber(b, "XMax", x1)
        f.setNumber(b, "YMin", y0); f.setNumber(b, "YMax", y1)
        f.setNumber(b, "ZMin", z0); f.setNumber(b, "ZMax", z1)
        f.setNumber(b, "VIn", v); f.setNumber(b, "VOut", 60.0)
        f.setNumber(b, "Thickness", 120.0)
        ids.append(b)
    mn = f.add("Min")
    f.setNumbers(mn, "FieldsList", ids)
    f.setAsBackgroundMesh(mn)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)       # HXT
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.model.mesh.generate(3)
    gmsh.model.mesh.optimize("Netgen")
    (HERE / "meshes").mkdir(exist_ok=True)
    path = HERE / "meshes" / f"{name}.msh"
    gmsh.write(str(path))
    ntet = sum(len(t) for t in gmsh.model.mesh.getElements(3)[1])
    gmsh.finalize()
    meta = dict(name=name, pan=pan, h=h, tets=int(ntet), sector_deg=18.0, R_out_mm=R_OUT, z_mm=[Z_LO, Z_HI],
                sections=[dict(r0=s.r0, r1=s.r1, turns=s.turns) for s in winding.sections], z_c=winding.z_c, side=SIDE,
                pan_r=PAN_R if pan else None, pan_t=PAN_T if pan else None)
    (HERE / "meshes" / f"{name}.json").write_text(json.dumps(meta, indent=1))
    return meta


def winding_for(layout):
    if not layout or layout == "R43_21.93":
        return G.R43
    c = json.loads((HERE.parent / "results" / "free_air.json").read_text())["candidates"][layout]
    return G.Winding(sections=tuple(G.Section(s["r0"], s["r1"], s["turns"]) for s in c["sections"]), name=layout)


def _planar(tag, phi):
    """Is surface `tag` flat in the meridian plane at angle phi (all its bounding points on it)?"""
    xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(2, tag)
    nx, ny = -math.sin(phi), math.cos(phi)
    pts = [(x, y) for x in (xmin, xmax) for y in (ymin, ymax)]
    # bounding box test is not exact for an inclined plane: sample the surface instead
    import numpy as np
    us = gmsh.model.getParametrizationBounds(2, tag)
    uu = np.linspace(us[0][0], us[1][0], 5)
    vv = np.linspace(us[0][1], us[1][1], 5)
    P = np.array([[u, v] for u in uu for v in vv]).ravel()
    xyz = np.array(gmsh.model.getValue(2, tag, P)).reshape(-1, 3)
    d = xyz[:, 0] * nx + xyz[:, 1] * ny
    return bool(np.max(np.abs(d)) < 1e-6 * max(1.0, float(np.max(np.abs(xyz)))))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--pan", action="store_true")
    ap.add_argument("--h", type=float, default=1.0)
    ap.add_argument("--layout", default=None, help="a candidate key in results/free_air.json (default R43)")
    a = ap.parse_args()
    print(json.dumps(build(a.name, pan=a.pan, h=a.h, winding=winding_for(a.layout))))
