"""Mesh the same R6 coax fixture with fine source triangles and coarser air.

The source in Elmer is nodally interpolated on the port, so its current-cut
spread can improve without making the whole direct solve too large for RAM.
"""

import argparse
import json
from pathlib import Path

import gmsh


def build(mesh_path: Path, port_size: float, volume_size: float) -> dict:
    if not (0 < port_size < volume_size):
        raise ValueError("require 0 < port_size < volume_size")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("closed_coax_port_refined")
        occ = gmsh.model.occ
        outer = occ.addCylinder(0, 0, 0, 0, 0, 50, 2.0)
        inner = occ.addCylinder(0, 0, 0, 0, 0, 50, 0.5)
        cut, _ = occ.cut([(3, outer)], [(3, inner)],
                         removeObject=True, removeTool=True)
        if len(cut) != 1 or cut[0][0] != 3:
            raise ValueError(f"expected one annular air volume, got {cut}")
        air = cut[0][1]
        occ.synchronize()
        surfaces = [tag for dim, tag in gmsh.model.getBoundary([(3, air)]) if dim == 2]
        port = []
        pec = []
        for tag in surfaces:
            _, _, zmin, _, _, zmax = gmsh.model.getBoundingBox(2, tag)
            if abs(zmin - 50) < 1e-5 and abs(zmax - 50) < 1e-5:
                port.append(tag)
            else:
                pec.append(tag)
        if len(port) != 1 or len(pec) != 3:
            raise ValueError(f"unexpected coax boundaries: {port=}, {pec=}")
        gmsh.model.addPhysicalGroup(3, [air], 1, "air")
        gmsh.model.addPhysicalGroup(2, pec, 2, "pec")
        gmsh.model.addPhysicalGroup(2, port, 3, "port")

        gmsh.option.setNumber("Mesh.MeshSizeMin", port_size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", volume_size)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.model.mesh.field.add("Distance", 1)
        gmsh.model.mesh.field.setNumbers(1, "SurfacesList", port)
        gmsh.model.mesh.field.setNumber(1, "Sampling", 80)
        gmsh.model.mesh.field.add("Threshold", 2)
        gmsh.model.mesh.field.setNumber(2, "InField", 1)
        gmsh.model.mesh.field.setNumber(2, "SizeMin", port_size)
        gmsh.model.mesh.field.setNumber(2, "SizeMax", volume_size)
        gmsh.model.mesh.field.setNumber(2, "DistMin", 0)
        gmsh.model.mesh.field.setNumber(2, "DistMax", 0.6)
        gmsh.model.mesh.field.setAsBackgroundMesh(2)

        gmsh.model.mesh.generate(3)
        types, tag_groups, _ = gmsh.model.mesh.getElements(3)
        if len(types) != 1 or int(types[0]) != 4:
            raise ValueError(f"unexpected volume element types: {types}")
        tags = tag_groups[0]
        minimum_jacobian = min(gmsh.model.mesh.getElementQualities(tags, "minDetJac"))
        if minimum_jacobian <= 0:
            raise ValueError(f"nonpositive tetrahedral Jacobian: {minimum_jacobian}")
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.Binary", 1)
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(mesh_path))
        return {"mesh": str(mesh_path), "port_size_mm": port_size,
                "volume_size_mm": volume_size, "tetrahedra": len(tags),
                "min_jacobian_mm3": minimum_jacobian,
                "groups": {"air": 1, "pec": 2, "port": 3}}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--port-size", type=float, default=0.10)
    parser.add_argument("--volume-size", type=float, default=0.30)
    args = parser.parse_args()
    print(json.dumps(build(args.mesh, args.port_size, args.volume_size), indent=2))
