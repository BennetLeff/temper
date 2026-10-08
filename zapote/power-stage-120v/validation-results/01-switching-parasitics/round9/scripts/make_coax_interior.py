#!/usr/bin/env python3
"""Coax fixture with an interior port sheet, built like Palace's rings example.

The inner rod, outer tube and end short are one perfect-conductor solid
removed from a larger air cylinder; the port is an annular sheet across the
open end, *inside* the air (air on both sides). That is how the board ports
in D1-FEM sit: sheets across component pads, surrounded by air.

Physical groups: 1 air (volume); 2 pec (conductor surfaces); 3 farfield
(outer air surfaces, also PEC in the solver); 4 port (interior sheet).

    PYTHONPATH=/opt/homebrew/lib python3 make_coax_interior.py OUT.msh \
        --a 0.5 --b 2.0 --length 50 --h-near 0.1 --h-far 3
Lengths in mm.
"""
from __future__ import annotations

import argparse
import math

import gmsh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--a", type=float, required=True, help="inner conductor radius")
    ap.add_argument("--b", type=float, required=True, help="outer conductor inner radius")
    ap.add_argument("--wall", type=float, default=0.3, help="tube and short thickness")
    ap.add_argument("--length", type=float, default=50.0)
    ap.add_argument("--air-margin", type=float, default=6.0, help="air beyond the tube, radially and axially")
    ap.add_argument("--h-near", type=float, required=True, help="element size in the gap and at the port")
    ap.add_argument("--h-far", type=float, default=3.0)
    a = ap.parse_args()
    ro = a.b + a.wall
    R = ro + a.air_margin
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    occ = gmsh.model.occ
    air = occ.addCylinder(0, 0, -a.air_margin, 0, 0, a.length + a.wall + 2 * a.air_margin, R)
    rod = occ.addCylinder(0, 0, 0, 0, 0, a.length, a.a)
    tube_out = occ.addCylinder(0, 0, 0, 0, 0, a.length, ro)
    tube_in = occ.addCylinder(0, 0, 0, 0, 0, a.length, a.b)
    tube, _ = occ.cut([(3, tube_out)], [(3, tube_in)])
    short = occ.addCylinder(0, 0, a.length, 0, 0, a.wall, ro)
    cond, _ = occ.fuse([(3, rod)], tube + [(3, short)])
    fluid, _ = occ.cut([(3, air)], cond)
    d_out = occ.addDisk(0, 0, 0, a.b, a.b)
    d_in = occ.addDisk(0, 0, 0, a.a, a.a)
    port, _ = occ.cut([(2, d_out)], [(2, d_in)])
    out, out_map = occ.fragment(fluid, port)
    occ.synchronize()
    # The port sheet seals the coax's inner space off from the outer air, so
    # the air is two volumes sharing the port; both are material 1.
    vols = [t for d, t in out if d == 3]
    port_tags = [t for d, t in out_map[len(fluid)]]
    bnd = [t for d, t in gmsh.model.getBoundary([(3, v) for v in vols], combined=True, oriented=False)]
    far, pec = [], []
    for s in bnd:
        x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(2, s)
        on_far = (max(abs(x0), abs(x1), abs(y0), abs(y1)) > R - 1e-6
                  or z0 < -a.air_margin + 1e-6 or z1 > a.length + a.wall + a.air_margin - 1e-6)
        (far if on_far else pec).append(s)
    assert port_tags and not set(port_tags) & set(bnd), "port must be interior"
    gmsh.model.addPhysicalGroup(3, vols, 1, "air")
    gmsh.model.addPhysicalGroup(2, pec, 2, "pec")
    gmsh.model.addPhysicalGroup(2, far, 3, "farfield")
    gmsh.model.addPhysicalGroup(2, port_tags, 4, "port")
    f = gmsh.model.mesh.field
    dist = f.add("Distance")
    f.setNumbers(dist, "SurfacesList", pec + port_tags)
    f.setNumber(dist, "Sampling", 200)
    th = f.add("Threshold")
    f.setNumber(th, "InField", dist)
    f.setNumber(th, "SizeMin", a.h_near)
    f.setNumber(th, "SizeMax", a.h_far)
    f.setNumber(th, "DistMin", max(a.b - a.a, 0.5))
    f.setNumber(th, "DistMax", max(a.b - a.a, 0.5) + 4 * a.h_far)
    f.setAsBackgroundMesh(th)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.model.mesh.generate(3)
    gmsh.model.mesh.optimize("Netgen")
    gmsh.write(a.out)
    n = len(gmsh.model.mesh.getElementsByType(4)[0])
    gmsh.finalize()
    exact = 2e-7 * math.log(a.b / a.a) * a.length * 1e-3
    print(f"tets {n}  analytic_coax_nH {exact * 1e9:.6f}")


if __name__ == "__main__":
    main()
