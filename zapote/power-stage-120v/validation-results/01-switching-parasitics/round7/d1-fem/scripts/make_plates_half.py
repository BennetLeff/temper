"""Mesh the upper z-half of the plate fixture for a symmetry cross-check.

The full fixture is mirror-symmetric about z=0.25 mm. The midplane has
normal magnetic flux zero, represented by the same AV tangential condition
as other PEC/magnetic-insulation boundaries. This must agree with a matched
full-domain solve before its refined results can be trusted.
"""

import argparse
import json
from pathlib import Path

import gmsh


def upper_surfaces(occ) -> tuple[int, int, int]:
    xyz = [(-5, 0, .5), (5, 0, .5), (5, 50, .5), (-5, 50, .5),
           (-5, 0, .25), (5, 0, .25), (5, 50, .25), (-5, 50, .25)]
    points = [occ.addPoint(*item) for item in xyz]
    segments = [(0, 1), (1, 2), (2, 3), (3, 0),
                (4, 5), (5, 6), (6, 7), (7, 4),
                (0, 4), (1, 5), (2, 6), (3, 7)]
    edges = [occ.addLine(points[i], points[j]) for i, j in segments]
    loops = [edges[:4], [edges[0], edges[9], -edges[4], -edges[8]],
             [-edges[2], edges[10], edges[6], -edges[11]]]
    return tuple(occ.addPlaneSurface([occ.addCurveLoop(row)]) for row in loops)


def build(mesh_path: Path, gap_size: float, air_margin: float,
          far_size: float, padding: float, transition: float,
          natural_symmetry: bool) -> dict:
    if not (0 < gap_size < far_size and air_margin > 0 and
            padding > 0 and transition > 0):
        raise ValueError("all sizes must be positive; gap size below far size")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("parallel_plates_upper_half")
        occ = gmsh.model.occ
        upper, short, port = upper_surfaces(occ)
        air = occ.addBox(-5-air_margin, -air_margin, .25,
                         10+2*air_margin, 50+2*air_margin,
                         .25+air_margin)
        _, maps = occ.fragment([(3, air)], [(2, upper), (2, short), (2, port)])
        occ.synchronize()
        volumes = [tag for dim, tag in maps[0] if dim == 3]
        upper_sheets = [tag for dim, tag in maps[1] if dim == 2]
        short_sheets = [tag for dim, tag in maps[2] if dim == 2]
        port_sheets = [tag for dim, tag in maps[3] if dim == 2]
        if not (volumes and upper_sheets and short_sheets and port_sheets):
            raise ValueError(f"unexpected fragment mapping: {maps}")
        boundaries = [tag for dim, tag in gmsh.model.getBoundary(
            [(3, tag) for tag in volumes], combined=True, oriented=False) if dim == 2]
        symmetry = []
        for tag in boundaries:
            box = gmsh.model.getBoundingBox(2, tag)
            if abs(box[2] - .25) < 1e-5 and abs(box[5] - .25) < 1e-5:
                symmetry.append(tag)
        if len(symmetry) != 1:
            raise ValueError(f"expected one midplane surface, got {symmetry}")
        pec = sorted((set(boundaries) - set(port_sheets)) |
                     set(upper_sheets) | set(short_sheets))
        if natural_symmetry:
            pec = sorted(set(pec) - set(symmetry))
        gmsh.model.addPhysicalGroup(3, volumes, 1, "air")
        gmsh.model.addPhysicalGroup(2, pec, 2,
                                    "pec_and_symmetry")
        gmsh.model.addPhysicalGroup(2, port_sheets, 3, "port")
        if natural_symmetry:
            gmsh.model.addPhysicalGroup(2, symmetry, 4, "symmetry_natural")
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
        gmsh.model.mesh.field.setNumber(1, "ZMin", .25-padding)
        gmsh.model.mesh.field.setNumber(1, "ZMax", .5+padding)
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
                "groups": {"air": 1, "pec_and_symmetry": 2, "port": 3},
                "upper_sheets": upper_sheets, "short_sheets": short_sheets,
                "port_sheets": port_sheets, "volumes": volumes,
                "symmetry_plane_z_mm": .25,
                "symmetry_surfaces": symmetry,
                "natural_symmetry": natural_symmetry}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--gap-size", type=float, required=True)
    parser.add_argument("--air-margin", type=float, default=20)
    parser.add_argument("--far-size", type=float, default=12)
    parser.add_argument("--padding", type=float, default=.2)
    parser.add_argument("--transition", type=float, default=.5)
    parser.add_argument("--natural-symmetry", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.mesh, args.gap_size, args.air_margin,
                           args.far_size, args.padding, args.transition,
                           args.natural_symmetry),
                     indent=2))
