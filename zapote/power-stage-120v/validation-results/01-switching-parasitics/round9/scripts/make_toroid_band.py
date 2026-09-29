#!/usr/bin/env python3
"""Exact magnetostatic fixture with a Cartesian source: a shorted toroidal cavity.

A coaxial cavity (inner rod radius a, outer wall radius b, length h) shorted
at both ends, fully enclosed by perfect conductor. The inner rod has a gap of
height g at mid-length; the drive is the cylindrical band r = a across that
gap, an interior sheet (air inside and outside) carrying current in +Z.
A constant +Z on a cylinder has zero surface divergence and the band's edges
end on the rod's conductor, so the source is exactly consistent with the
magnetostatic null space (unlike Palace's radial "+R" coaxial element, which
diverged in rounds 8 and 9). By Ampere's law the field is zero inside the
rod gap, so L = (mu0 h / 2 pi) ln(b / a) exactly.

Physical groups: 1 air (both volumes); 2 pec (all outer surfaces); 4 port.

    PYTHONPATH=/opt/homebrew/lib python3 make_toroid_band.py OUT.msh --a 0.5 --b 2.0 --h-near 0.3
"""
from __future__ import annotations

import argparse
import math

import gmsh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--a", type=float, required=True)
    ap.add_argument("--b", type=float, required=True)
    ap.add_argument("--length", type=float, default=50.0)
    ap.add_argument("--gap", type=float, default=1.0)
    ap.add_argument("--h-near", type=float, required=True, help="size in the annular gap")
    ap.add_argument("--h-port", type=float, default=None, help="size at the band (default h-near/2)")
    a = ap.parse_args()
    h_port = a.h_port or a.h_near / 2
    L, g = a.length, a.gap
    z0 = L / 2 - g / 2
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    occ = gmsh.model.occ
    cavity = occ.addCylinder(0, 0, 0, 0, 0, L, a.b)
    rod1 = occ.addCylinder(0, 0, 0, 0, 0, z0, a.a)
    rod2 = occ.addCylinder(0, 0, z0 + g, 0, 0, L - z0 - g, a.a)
    air, _ = occ.cut([(3, cavity)], [(3, rod1), (3, rod2)])
    band = occ.addCylinder(0, 0, z0, 0, 0, g, a.a)
    out, _ = occ.fragment(air, [(3, band)])
    occ.synchronize()
    vols = [t for d, t in out if d == 3]
    assert len(vols) == 2, out
    outer = {t for d, t in gmsh.model.getBoundary([(3, v) for v in vols], combined=True, oriented=False)}
    port = []
    for d, s in gmsh.model.getEntities(2):
        if s in outer:
            continue
        x0, y0, z0b, x1, y1, z1 = gmsh.model.getBoundingBox(2, s)
        if abs(z1 - z0b - g) < 1e-6 and abs(x1 - x0 - 2 * a.a) < 1e-3:
            port.append(s)
    assert len(port) == 1, port
    gmsh.model.addPhysicalGroup(3, vols, 1, "air")
    gmsh.model.addPhysicalGroup(2, sorted(outer), 2, "pec")
    gmsh.model.addPhysicalGroup(2, port, 4, "port")
    f = gmsh.model.mesh.field
    dist = f.add("Distance")
    f.setNumbers(dist, "SurfacesList", port)
    f.setNumber(dist, "Sampling", 200)
    th = f.add("Threshold")
    f.setNumber(th, "InField", dist)
    f.setNumber(th, "SizeMin", h_port)
    f.setNumber(th, "SizeMax", a.h_near)
    f.setNumber(th, "DistMin", g)
    f.setNumber(th, "DistMax", 4 * g)
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
    exact = 2e-7 * math.log(a.b / a.a) * L * 1e-3
    print(f"tets {n}  exact_nH {exact * 1e9:.6f}")


if __name__ == "__main__":
    main()
