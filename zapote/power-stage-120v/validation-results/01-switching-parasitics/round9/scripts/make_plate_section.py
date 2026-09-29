#!/usr/bin/env python3
"""Exact thin-gap magnetostatic fixture: a parallel-plate section with magnetic side walls.

The air box between two perfect-conductor plates (gap d, width w, length l),
shorted at x = l, driven by the flat rectangular port at x = 0 (current in
+Z across the gap). The side walls y = 0 and y = w get the natural boundary
condition (tangential H = 0), so the field crosses them normally, which is
the field of infinitely wide plates. There is no fringing, and
L = mu0 * d * l / w exactly.

The port is flat with a constant direction, the source Palace's lumped
surface current handles consistently (the radial coax port and a curved band
didn't). The 0.5 mm gap matches the board's plane pairs.

Physical groups: 1 air; 2 pec (both plates and the short); 3 sides
(natural, left unlabelled in the solver); 4 port.

    PYTHONPATH=/opt/homebrew/lib python3 make_plate_section.py OUT.msh --h 0.25
"""
from __future__ import annotations

import argparse
import math

import gmsh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--gap", type=float, default=0.5)
    ap.add_argument("--width", type=float, default=10.0)
    ap.add_argument("--length", type=float, default=50.0)
    ap.add_argument("--h", type=float, required=True)
    ap.add_argument("--behind", type=float, default=0.0,
                    help="extend the plates this far behind the port, making the port an interior sheet")
    a = ap.parse_args()
    d, w, l = a.gap, a.width, a.length
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    e = a.behind
    box = gmsh.model.occ.addBox(-e, 0, 0, l + e, w, d)
    vols = [box]
    interior_port = []
    if e > 0:
        rect = gmsh.model.occ.addRectangle(0, 0, 0, d, w)   # rotates to z 0..d, y 0..w
        gmsh.model.occ.rotate([(2, rect)], 0, 0, 0, 0, 1, 0, -math.pi / 2)   # y-z plane at x = 0
        out, omap = gmsh.model.occ.fragment([(3, box)], [(2, rect)])
        vols = [t for dd, t in out if dd == 3]
        interior_port = [t for dd, t in omap[1]]
    gmsh.model.occ.synchronize()
    groups = {"pec": [], "sides": [], "port": list(interior_port)}
    for _, s in gmsh.model.getBoundary([(3, v) for v in vols], combined=True, oriented=False):
        cx, cy, cz = gmsh.model.occ.getCenterOfMass(2, abs(s))
        if abs(cx) < 1e-6 and e == 0:
            groups["port"].append(abs(s))                                 # x = 0
        elif e > 0 and abs(cx + e) < 1e-6:
            groups["sides"].append(abs(s))                                # far end behind the port: natural
        elif abs(cx - l) < 1e-6 or abs(cz) < 1e-6 or abs(cz - d) < 1e-6:
            groups["pec"].append(abs(s))                                  # short, plates
        else:
            groups["sides"].append(abs(s))                                # y = 0, y = w
    assert len(groups["port"]) == 1 and len(groups["pec"]) >= 3, groups
    gmsh.model.addPhysicalGroup(3, vols, 1, "air")
    gmsh.model.addPhysicalGroup(2, groups["pec"], 2, "pec")
    gmsh.model.addPhysicalGroup(2, groups["sides"], 3, "sides")
    gmsh.model.addPhysicalGroup(2, groups["port"], 4, "port")
    gmsh.option.setNumber("Mesh.MeshSizeMin", a.h)
    gmsh.option.setNumber("Mesh.MeshSizeMax", a.h)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.model.mesh.generate(3)
    gmsh.write(a.out)
    n = len(gmsh.model.mesh.getElementsByType(4)[0])
    gmsh.finalize()
    exact = 4e-7 * math.pi * d * l / w * 1e-3
    print(f"tets {n}  exact_nH {exact * 1e9:.6f}")


if __name__ == "__main__":
    main()
