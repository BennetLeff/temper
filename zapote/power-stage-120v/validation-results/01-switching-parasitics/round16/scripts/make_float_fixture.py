#!/usr/bin/env python3
"""Round 16: thick-plates fixture plus optional floating PEC blocks.

The board model has PEC bodies that touch no port (e.g. copper not on the
driven loop). Round 16 found the direct (tree-gauge) and Hypre AMS solves
disagreeing on the board (18 vs 30 nH) while agreeing exactly on every
single-conductor fixture. --float adds such bodies here: both solvers solve
the same discrete problem, so they must agree with or without them.

Round-9 description:
Plate-pair fixture built the way D1-FEM models the board.

Two copper plates of real thickness (not zero-thickness sheets) and the end
short are one solid cut out of an air box, so the conductor surfaces are
outer boundaries of the air, as the board's copper will be. The port is a
flat interior sheet across the open end, current in +Z, air on both sides.
Plates: x -5..5, y 0..50, gap 0.5 mm (z 0..0.5), thickness t.

Physical groups: 1 air; 2 pec (conductor surfaces and the air box); 4 port.
"""
from __future__ import annotations

import argparse

import gmsh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--t", type=float, default=0.07)
    ap.add_argument("--margin", type=float, default=40.0)
    ap.add_argument("--h-near", type=float, default=0.25)
    ap.add_argument("--h-far", type=float, default=12.0)
    ap.add_argument("--pad", type=float, default=2.0, help="fine region beyond the plates")
    ap.add_argument("--float", type=int, default=0, help="number of floating PEC blocks beside the plates (0-2)")
    ap.add_argument("--exterior-port", action="store_true",
                    help="end the air box at y = 0 so the port lies on its outer boundary (diagnostic)")
    a = ap.parse_args()
    t, m = a.t, a.margin
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    occ = gmsh.model.occ
    y0 = 0.0 if a.exterior_port else -m
    air = occ.addBox(-5 - m, y0, -t - m, 10 + 2 * m, 50 + t + m - y0, 0.5 + 2 * t + 2 * m)
    low = occ.addBox(-5, 0, -t, 10, 50, t)
    up = occ.addBox(-5, 0, 0.5, 10, 50, t)
    short = occ.addBox(-5, 50, -t, 10, t, 0.5 + 2 * t)
    cond, _ = occ.fuse([(3, low)], [(3, up), (3, short)])
    # floating blocks: 1 mm beside the plates (x = 6..8) and above them (z = 1.5..2)
    blocks = [occ.addBox(6, 5, -t, 2, 40, 0.5 + 2 * t), occ.addBox(-5, 5, 1.5, 10, 40, 0.5)][:a.float]
    fluid, _ = occ.cut([(3, air)], cond + [(3, b) for b in blocks])
    port = occ.addRectangle(-5, 0, 0, 10, 0.5)
    occ.rotate([(2, port)], -5, 0, 0, 1, 0, 0, 3.141592653589793 / 2)   # into the x-z plane at y = 0
    out, omap = occ.fragment(fluid, [(2, port)])
    occ.synchronize()
    vols = [tg for d, tg in out if d == 3]
    port_tags = [tg for d, tg in omap[len(fluid)]]
    outer = [tg for d, tg in gmsh.model.getBoundary([(3, v) for v in vols], combined=True, oriented=False)]
    if a.exterior_port:
        assert port_tags and set(port_tags) <= set(outer)
        outer = [tg for tg in outer if tg not in port_tags]
    else:
        assert port_tags and not set(port_tags) & set(outer)
    for s in port_tags:
        x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(2, s)
        assert abs(y1 - y0) < 1e-5 and z1 - z0 > 0.49, (x0, y0, z0, x1, y1, z1)
    gmsh.model.addPhysicalGroup(3, vols, 1, "air")
    gmsh.model.addPhysicalGroup(2, outer, 2, "pec")
    gmsh.model.addPhysicalGroup(2, port_tags, 4, "port")
    f = gmsh.model.mesh.field
    box = f.add("Box")
    for k, v in (("VIn", a.h_near), ("VOut", a.h_far), ("XMin", -5 - a.pad), ("XMax", 5 + a.pad),
                 ("YMin", -a.pad), ("YMax", 50 + a.pad), ("ZMin", -t - a.pad), ("ZMax", 0.5 + t + a.pad),
                 ("Thickness", 4.0)):
        f.setNumber(box, k, v)
    f.setAsBackgroundMesh(box)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.model.mesh.generate(3)
    gmsh.write(a.out)
    print("tets", len(gmsh.model.mesh.getElementsByType(4)[0]))
    gmsh.finalize()


if __name__ == "__main__":
    main()
