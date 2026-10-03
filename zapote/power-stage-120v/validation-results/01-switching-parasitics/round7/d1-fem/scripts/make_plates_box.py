"""Mesh the plate fixture with a continuous sizing region over both plates.

The earlier sampled-distance field left most plate triangles much larger than
the requested near size. This version directly sizes the full gap and both
plate surfaces; the output still needs an actual-element audit before use.
"""

import argparse
import json
from pathlib import Path

import gmsh
from make_plates_localized import plate_surfaces


def build(mesh_path: Path, gap_size: float, air_margin: float,
          far_size: float, padding: float, transition: float) -> dict:
    if not (0 < gap_size < far_size and air_margin > 0 and
            padding > 0 and transition > 0):
        raise ValueError("all sizes must be positive; gap size below far size")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("parallel_plates_box")
        occ = gmsh.model.occ
        lower, upper, short, port = plate_surfaces(occ)
        air = occ.addBox(-5-air_margin, -air_margin, -air_margin,
                         10+2*air_margin, 50+2*air_margin,
                         0.5+2*air_margin)
        occ.synchronize()
        farfield = [tag for dim, tag in gmsh.model.getBoundary([(3, air)])
                    if dim == 2]
        if len(farfield) != 6:
            raise ValueError(f"unexpected air-box boundary: {farfield}")
        gmsh.model.addPhysicalGroup(3, [air], 1, "air")
        gmsh.model.addPhysicalGroup(2, farfield + [lower, upper, short], 2,
                                    "pec")
        gmsh.model.addPhysicalGroup(2, [port], 3, "port")
        gmsh.model.mesh.embed(2, [lower, upper, short, port], 3, air)
        gmsh.option.setNumber("Mesh.MeshSizeMin", gap_size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", far_size)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.model.mesh.field.add("Box", 1)
        gmsh.model.mesh.field.setNumber(1, "VIn", gap_size)
        gmsh.model.mesh.field.setNumber(1, "VOut", far_size)
        gmsh.model.mesh.field.setNumber(1, "XMin", -5-padding)
        gmsh.model.mesh.field.setNumber(1, "XMax", 5+padding)
        gmsh.model.mesh.field.setNumber(1, "YMin", -padding)
        gmsh.model.mesh.field.setNumber(1, "YMax", 50+padding)
        gmsh.model.mesh.field.setNumber(1, "ZMin", -padding)
        gmsh.model.mesh.field.setNumber(1, "ZMax", 0.5+padding)
        gmsh.model.mesh.field.setNumber(1, "Thickness", transition)
        gmsh.model.mesh.field.setAsBackgroundMesh(1)
        gmsh.model.mesh.generate(3)
        types, tags, _ = gmsh.model.mesh.getElements(3)
        if any(item != 4 for item in types):
            raise ValueError(f"unexpected element types {types}")
        count = sum(len(item) for item in tags)
        if count == 0:
            raise ValueError("empty mesh")
        jacobians = gmsh.model.mesh.getElementQualities(tags[0], "minDetJac")
        minimum = min(jacobians)
        if minimum <= 0:
            raise ValueError(f"nonpositive tetrahedron Jacobian: {minimum}")
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.Binary", 1)
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(mesh_path))
        return {"mesh": str(mesh_path), "gap_size_mm": gap_size,
                "far_size_mm": far_size, "padding_mm": padding,
                "transition_mm": transition, "air_margin_mm": air_margin,
                "tetrahedra": count, "min_jacobian_mm3": minimum,
                "groups": {"air": 1, "pec": 2, "port": 3}}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--gap-size", type=float, required=True)
    parser.add_argument("--air-margin", type=float, default=20)
    parser.add_argument("--far-size", type=float, default=4)
    parser.add_argument("--padding", type=float, default=0.25)
    parser.add_argument("--transition", type=float, default=1.5)
    args = parser.parse_args()
    print(json.dumps(build(args.mesh, args.gap_size, args.air_margin,
                           args.far_size, args.padding, args.transition),
                     indent=2))
