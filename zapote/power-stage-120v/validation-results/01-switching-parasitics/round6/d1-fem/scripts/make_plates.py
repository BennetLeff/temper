"""Generate the finite parallel-plate loop as PEC sheets embedded in air.

This follows the surface treatment of Palace's pinned rings example. Two
10 x 50 mm plates are 0.5 mm apart and shorted at y=0. A surface-current
sheet at y=50 drives the loop. Copper is PEC, so thickness is immaterial to
this fixture; fringing in the exterior air remains in the solve.
"""

import argparse
import json
from pathlib import Path

import gmsh


def plate_surfaces(occ) -> tuple[int, int, int, int]:
    """Build four touching sheets using shared curves, as Palace rings does."""
    xyz = [(-5, 0, 0), (5, 0, 0), (5, 50, 0), (-5, 50, 0),
           (-5, 0, 0.5), (5, 0, 0.5), (5, 50, 0.5), (-5, 50, 0.5)]
    p = [occ.addPoint(*item) for item in xyz]
    segments = [(0, 1), (1, 2), (2, 3), (3, 0),
                (4, 5), (5, 6), (6, 7), (7, 4),
                (0, 4), (1, 5), (2, 6), (3, 7)]
    e = [occ.addLine(p[i], p[j]) for i, j in segments]
    loops = [e[:4], e[4:8], [e[0], e[9], -e[4], -e[8]],
             [-e[2], e[10], e[6], -e[11]]]
    return tuple(occ.addPlaneSurface([occ.addCurveLoop(row)]) for row in loops)


def build(mesh_path: Path, near_size: float, air_margin: float) -> dict:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("parallel_plates")
        occ = gmsh.model.occ
        lower, upper, short, port = plate_surfaces(occ)
        air = occ.addBox(-5-air_margin, -air_margin, -air_margin,
                         10+2*air_margin, 50+2*air_margin, 0.5+2*air_margin)
        occ.synchronize()
        farfield = [tag for dim, tag in gmsh.model.getBoundary([(3, air)]) if dim == 2]
        if len(farfield) != 6:
            raise ValueError(f"unexpected air-box boundary: {farfield}")
        gmsh.model.addPhysicalGroup(3, [air], 1, "air")
        gmsh.model.addPhysicalGroup(2, farfield + [lower, upper, short], 2, "pec")
        gmsh.model.addPhysicalGroup(2, [port], 3, "port")
        gmsh.model.mesh.embed(2, [lower, upper, short, port], 3, air)
        gmsh.option.setNumber("Mesh.MeshSizeMin", near_size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2.0)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.model.mesh.field.add("Distance", 1)
        gmsh.model.mesh.field.setNumbers(1, "SurfacesList", [lower, upper, short, port])
        gmsh.model.mesh.field.setNumber(1, "Sampling", 50)
        gmsh.model.mesh.field.add("Threshold", 2)
        gmsh.model.mesh.field.setNumber(2, "InField", 1)
        gmsh.model.mesh.field.setNumber(2, "SizeMin", near_size)
        gmsh.model.mesh.field.setNumber(2, "SizeMax", 2.0)
        gmsh.model.mesh.field.setNumber(2, "DistMin", 0.25)
        gmsh.model.mesh.field.setNumber(2, "DistMax", 5.0)
        gmsh.model.mesh.field.setAsBackgroundMesh(2)
        gmsh.model.mesh.generate(3)
        types, tags, _ = gmsh.model.mesh.getElements(3)
        if any(item != 4 for item in types):
            raise ValueError(f"unexpected element type {types}")
        count = sum(len(item) for item in tags)
        if count == 0:
            raise ValueError("empty plate mesh")
        determinants = gmsh.model.mesh.getElementQualities(tags[0], "minDetJac")
        minimum_jacobian = min(determinants)
        if minimum_jacobian <= 0:
            raise ValueError(f"nonpositive tetrahedron Jacobian: {minimum_jacobian}")
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.Binary", 1)
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(mesh_path))
        return {"mesh": str(mesh_path), "near_size_mm": near_size,
                "air_margin_mm": air_margin, "tetrahedra": count,
                "min_jacobian_mm3": minimum_jacobian,
                "groups": {"air": 1, "pec": 2, "port": 3},
                "pec_sheets": [lower, upper, short], "port_sheet": port}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--near-size", type=float, default=0.15)
    parser.add_argument("--air-margin", type=float, default=20)
    args = parser.parse_args()
    print(json.dumps(build(args.mesh, args.near_size, args.air_margin), indent=2))
