"""Report actual plate surface edge lengths and gap tetrahedron counts."""

import argparse
import json
from pathlib import Path

import gmsh
import numpy as np


def audit(mesh: Path) -> dict:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh))
        node_tags, coordinates, _ = gmsh.model.mesh.getNodes()
        points = np.asarray(coordinates).reshape(-1, 3)
        nodes = {int(tag): points[index] for index, tag in enumerate(node_tags)}
        surfaces = {}
        for surface in (1, 2):
            types, _, connected = gmsh.model.mesh.getElements(2, surface)
            if list(types) != [2]:
                raise ValueError(f"surface {surface} has types {types}")
            triangles = np.asarray(connected[0]).reshape(-1, 3)
            vertices = np.array([[nodes[int(tag)] for tag in triangle]
                                 for triangle in triangles])
            edges = np.concatenate([
                np.linalg.norm(vertices[:, 1] - vertices[:, 0], axis=1),
                np.linalg.norm(vertices[:, 2] - vertices[:, 1], axis=1),
                np.linalg.norm(vertices[:, 0] - vertices[:, 2], axis=1),
            ])
            area = np.sum(np.linalg.norm(np.cross(vertices[:, 1]-vertices[:, 0],
                                                   vertices[:, 2]-vertices[:, 0]),
                                            axis=1) / 2)
            surfaces[str(surface)] = {
                "triangles": len(triangles), "area_mm2": float(area),
                "edge_mm_quantiles": {str(q): float(np.quantile(edges, q))
                                      for q in (0, .5, .9, .99, 1)},
            }
        types, tags, connected = gmsh.model.mesh.getElements(3)
        if list(types) != [4]:
            raise ValueError(f"volume has types {types}")
        tetrahedra = np.asarray(connected[0]).reshape(-1, 4)
        # Centroid inclusion is a diagnostic of actual gap resolution.
        vertices = np.array([[nodes[int(tag)] for tag in tetrahedron]
                             for tetrahedron in tetrahedra])
        centers = vertices.mean(axis=1)
        gap = ((centers[:, 0] >= -5) & (centers[:, 0] <= 5) &
               (centers[:, 1] >= 0) & (centers[:, 1] <= 50) &
               (centers[:, 2] >= 0) & (centers[:, 2] <= .5))
        return {"mesh": str(mesh), "nodes": len(nodes),
                "tetrahedra": len(tetrahedra), "gap_centroid_tetrahedra": int(gap.sum()),
                "plates": surfaces}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.mesh), indent=2))
