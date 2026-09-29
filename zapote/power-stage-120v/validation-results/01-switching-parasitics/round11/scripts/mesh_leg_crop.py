#!/usr/bin/env python3
"""Mesh the air around one leg's copper (D1-FEM section 3), without solving.

Round 11 is a sizing run: it answers how many tetrahedra a board leg needs
at a given resolution near the copper, which sets the machine for the
direct solve (round 10: peak memory ~ N^1.27). Ports and arches are not
added; they add little to the count.

Steps: load KiCad's copper STEP (board X; STEP Y = -board Y; mm), heal
(no sewing: OCCSewFaces destroyed volumes in the round-5 probe), crop the
copper to the leg's pad box plus a margin, cut it out of a larger air box,
and mesh the air with fine elements near the copper grading to coarse.

    PYTHONPATH=/opt/homebrew/lib python3 mesh_leg_crop.py copper.step OUT.msh \
        --leg A --h-near 0.5 [--margin 10] [--air 10]
"""
from __future__ import annotations

import argparse
import json
import time

import gmsh

# Leg pad bounding boxes in board coordinates (mm, Y down), from native-17
# (D1-FEM section 2): caps, MOSFETs, gate resistors, driver pins, R5.
LEGS = {"A": (125.865, 4.215, 164.6, 41.125), "B": (88.4, 4.215, 127.135, 41.125)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step")
    ap.add_argument("out")
    ap.add_argument("--leg", choices=LEGS, default="A")
    ap.add_argument("--h-near", type=float, required=True)
    ap.add_argument("--h-far", type=float, default=5.0)
    ap.add_argument("--margin", type=float, default=10.0, help="copper crop beyond the pad box")
    ap.add_argument("--air", type=float, default=10.0, help="air beyond the copper crop")
    ap.add_argument("--no-mesh", action="store_true")
    ap.add_argument("--algo2d", type=int, default=6, help="gmsh 2-D algorithm (6 Frontal-Delaunay, 5 Delaunay, 1 MeshAdapt)")
    ap.add_argument("--algo3d", type=int, default=1, help="gmsh 3-D algorithm (1 Delaunay, 10 HXT)")
    ap.add_argument("--tol", type=float, default=1e-4, help="OCC geometry tolerance (mm)")
    a = ap.parse_args()
    x0, by0, x1, by1 = LEGS[a.leg]
    m = a.margin
    # Board edge is at board y = 0 (STEP y = 0); copper lies at STEP y <= 0.
    cx0, cx1 = x0 - m, x1 + m
    cy0, cy1 = -(by1 + m), min(-(by0 - m), 0.5)
    t0 = time.time()
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.option.setNumber("General.NumThreads", 8)
    gmsh.option.setNumber("Geometry.OCCImportLabels", 0)
    for k in ("OCCFixDegenerated", "OCCFixSmallEdges", "OCCFixSmallFaces"):
        gmsh.option.setNumber(f"Geometry.{k}", 1)
    gmsh.option.setNumber("Geometry.Tolerance", a.tol)
    occ = gmsh.model.occ
    copper = occ.importShapes(a.step)
    crop = occ.addBox(cx0, cy0, -0.2, cx1 - cx0, cy1 - cy0, 2.0)
    cu, _ = occ.intersect(copper, [(3, crop)])
    occ.synchronize()
    n_cu = len([t for d, t in cu if d == 3])
    air = occ.addBox(cx0 - a.air, cy0 - a.air, -0.07 - a.air,
                     cx1 - cx0 + 2 * a.air, cy1 - cy0 + 2 * a.air, 1.633 + 2 * a.air)
    fluid, _ = occ.cut([(3, air)], cu)
    occ.synchronize()
    vols = [t for d, t in fluid if d == 3]
    outer = {t for d, t in gmsh.model.getBoundary([(3, air)] if False else [(3, v) for v in vols],
                                                 combined=True, oriented=False)}
    bnd = sorted(outer)
    far, cond = [], []
    for s in bnd:
        b = gmsh.model.getBoundingBox(2, s)
        on_box = (abs(b[0] - (cx0 - a.air)) < 1e-3 or abs(b[3] - (cx1 + a.air)) < 1e-3
                  or abs(b[1] - (cy0 - a.air)) < 1e-3 or abs(b[4] - (cy1 + a.air)) < 1e-3
                  or abs(b[2] - (-0.07 - a.air)) < 1e-3 or abs(b[5] - (1.563 + a.air)) < 1e-3)
        (far if on_box else cond).append(s)
    gmsh.model.addPhysicalGroup(3, vols, 1, "air")
    gmsh.model.addPhysicalGroup(2, cond, 2, "copper")
    gmsh.model.addPhysicalGroup(2, far, 3, "farfield")
    f = gmsh.model.mesh.field
    dist = f.add("Distance")
    f.setNumbers(dist, "SurfacesList", cond)
    f.setNumber(dist, "Sampling", 20)
    th = f.add("Threshold")
    f.setNumber(th, "InField", dist)
    f.setNumber(th, "SizeMin", a.h_near)
    f.setNumber(th, "SizeMax", a.h_far)
    f.setNumber(th, "DistMin", 0.5)
    f.setNumber(th, "DistMax", 8.0)
    f.setAsBackgroundMesh(th)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.MeshSizeMin", a.h_near / 4)
    gmsh.option.setNumber("Mesh.Algorithm", a.algo2d)
    gmsh.option.setNumber("Mesh.Algorithm3D", a.algo3d)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    info = {"leg": a.leg, "h_near_mm": a.h_near, "h_far_mm": a.h_far, "margin_mm": m, "air_mm": a.air,
            "copper_crop_box_step_mm": [cx0, cy0, cx1, cy1], "copper_volumes": n_cu,
            "air_volumes": len(vols), "copper_surfaces": len(cond), "farfield_surfaces": len(far),
            "geometry_s": round(time.time() - t0, 1)}
    if not a.no_mesh:
        t1 = time.time()
        info["algo2d"] = a.algo2d
        info["algo3d"] = a.algo3d
        info["tol_mm"] = a.tol
        try:
            gmsh.model.mesh.generate(3)
        except Exception as exc:
            import re
            info["error"] = str(exc)
            for tag in sorted({int(t) for t in re.findall(r"surface (\d+)", str(exc))}):
                b = gmsh.model.getBoundingBox(2, tag)
                info.setdefault("failed_surfaces", []).append(
                    {"tag": tag, "bbox_step_mm": [round(v, 4) for v in b],
                     "area_mm2": gmsh.model.occ.getMass(2, tag)})
            print("RESULT " + json.dumps(info))
            gmsh.finalize()
            raise SystemExit(1)
        info["tets"] = len(gmsh.model.mesh.getElementsByType(4)[0])
        info["triangles"] = len(gmsh.model.mesh.getElementsByType(2)[0])
        info["mesh_s"] = round(time.time() - t1, 1)
        gmsh.write(a.out)
    gmsh.finalize()
    print("RESULT " + json.dumps(info))


if __name__ == "__main__":
    main()
