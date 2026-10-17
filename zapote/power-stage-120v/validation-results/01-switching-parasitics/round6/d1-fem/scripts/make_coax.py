"""Generate the closed-coax magnetostatic fixture for the pinned Palace source.

The air annulus is bounded by PEC inner/outer conductors and an end short.
The other end is a surface-current port directed radially outwards. Lengths
are mm. The analytic external L is μ0*l*ln(b/a)/(2π) = 13.8629436 nH.
"""

import argparse
import json
from pathlib import Path

import gmsh


def build(mesh_path: Path, size: float, boundary_mode: str = "palace") -> dict:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("closed_coax")
        outer = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, 50, 2.0)
        inner = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, 50, 0.5)
        cut, _ = gmsh.model.occ.cut([(3, outer)], [(3, inner)], removeObject=True, removeTool=True)
        if len(cut) != 1 or cut[0][0] != 3:
            raise ValueError(f"expected one annular air domain, got {cut}")
        air = cut[0][1]
        gmsh.model.occ.synchronize()
        surfaces = [tag for dim, tag in gmsh.model.getBoundary([(3, air)]) if dim == 2]
        port = []
        pec = []
        for tag in surfaces:
            xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(2, tag)
            if abs(zmin - 50) < 1e-5 and abs(zmax - 50) < 1e-5:
                port.append(tag)
            else:
                pec.append(tag)
        if len(port) != 1 or len(pec) < 3:
            raise ValueError(f"unexpected coax boundaries: port={port}, pec={pec}")
        gmsh.model.addPhysicalGroup(3, [air], 1, "air")
        if boundary_mode == "elmer":
            inner, outer, caps = [], [], []
            for tag in surfaces:
                xmin, _, zmin, xmax, _, zmax = gmsh.model.getBoundingBox(2, tag)
                if zmax - zmin < 1e-5:
                    caps.append(tag)
                elif max(abs(xmin), abs(xmax)) < 0.6:
                    inner.append(tag)
                else:
                    outer.append(tag)
            if len(inner) != 1 or len(outer) != 1 or len(caps) != 2:
                raise ValueError(f"unexpected Elmer boundaries: {inner=}, {outer=}, {caps=}")
            gmsh.model.addPhysicalGroup(2, inner, 2, "inner_current_surface")
            gmsh.model.addPhysicalGroup(2, outer, 3, "outer_return_surface")
            gmsh.model.addPhysicalGroup(2, caps, 4, "end_caps")
            groups = {"air": 1, "inner_current_surface": 2, "outer_return_surface": 3, "end_caps": 4}
        else:
            gmsh.model.addPhysicalGroup(2, pec, 2, "pec")
            gmsh.model.addPhysicalGroup(2, port, 3, "port")
            groups = {"air": 1, "pec": 2, "port": 3}
        gmsh.option.setNumber("Mesh.MeshSizeMin", size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.model.mesh.generate(3)
        element_types, element_tags, _ = gmsh.model.mesh.getElements(3)
        if any(element_type != 4 for element_type in element_types):
            raise ValueError(f"unexpected 3-D elements: {element_types}")
        count = sum(len(tags) for tags in element_tags)
        if count == 0:
            raise ValueError("empty 3-D mesh")
        determinants = gmsh.model.mesh.getElementQualities(element_tags[0], "minDetJac")
        minimum_jacobian = min(determinants)
        if minimum_jacobian <= 0:
            raise ValueError(f"nonpositive tetrahedron Jacobian: {minimum_jacobian}")
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.Binary", 1)
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(mesh_path))
        return {"mesh": str(mesh_path), "mesh_size_mm": size, "tetrahedra": count, "min_jacobian_mm3": minimum_jacobian,
                "groups": groups, "surfaces": len(surfaces)}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--size", type=float, default=0.5)
    parser.add_argument("--boundary-mode", choices=("palace", "elmer"), default="palace")
    args = parser.parse_args()
    print(json.dumps(build(args.mesh, args.size, args.boundary_mode), indent=2))
