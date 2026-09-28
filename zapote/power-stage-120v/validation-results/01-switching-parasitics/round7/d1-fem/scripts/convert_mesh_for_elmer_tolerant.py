"""Convert MSH2 binary to ASCII with a geometry-safe node remap check.

Round 6's coordinate-key check can reject a harmless last-bit ASCII change
when a coordinate straddles a 1e-9 mm rounding boundary. This converter
matches coordinates by unique nearest neighbor, then checks *oriented*
element connectivity and every physical group before allowing ElmerGrid.
"""

import argparse
import json
import sys
from pathlib import Path

import gmsh
import numpy as np
from scipy.spatial import cKDTree

R6_SCRIPTS = Path(__file__).resolve().parents[3] / "round6/d1-fem/scripts"
sys.path.insert(0, str(R6_SCRIPTS))
from convert_mesh_for_elmer import snapshot  # noqa: E402


def convert(source: Path, output: Path) -> dict:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(source))
        before = snapshot()
        tetrahedra = len(before[3].get((3, 4), ([], []))[0])
        if tetrahedra == 0 or any(dim == 3 and kind != 4 for dim, kind in before[3]):
            raise ValueError("expected first-order tetrahedral volume mesh")
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.Binary", 0)
        output.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(output))
        gmsh.clear()
        gmsh.open(str(output))
        after = snapshot()
        if before[0] != after[0]:
            raise ValueError("physical groups changed in ASCII roundtrip")
        if len(before[1]) != len(after[1]):
            raise ValueError("node count changed in ASCII roundtrip")
        distances, indices = cKDTree(before[2]).query(after[2], k=2)
        nearest = distances[:, 0]
        if nearest.max() > 1e-9 or distances[:, 1].min() <= 1e-9:
            raise ValueError("ambiguous or changed node geometry in ASCII roundtrip")
        mapped_tags = before[1][indices[:, 0]]
        if len(set(map(int, mapped_tags))) != len(before[1]):
            raise ValueError("node mapping is not one-to-one")
        output_to_input = dict(zip(map(int, after[1]), map(int, mapped_tags), strict=True))
        if before[3].keys() != after[3].keys():
            raise ValueError("element families changed in ASCII roundtrip")
        for key in before[3]:
            if not np.array_equal(before[3][key][0], after[3][key][0]):
                raise ValueError(f"element IDs changed for {key}")
            output_nodes = after[3][key][1]
            remapped = np.fromiter((output_to_input[int(node)] for node in output_nodes.flat),
                                   dtype=np.int64, count=output_nodes.size).reshape(output_nodes.shape)
            if not np.array_equal(before[3][key][1], remapped):
                raise ValueError(f"oriented element connectivity changed for {key}")
        return {"source": str(source), "output": str(output),
                "tetrahedra": tetrahedra, "physical_groups": before[0],
                "roundtrip_max_coordinate_delta_mm": float(nearest.max()),
                "minimum_second_nearest_distance_mm": float(distances[:, 1].min()),
                "roundtrip_oriented_connectivity_equal_after_node_mapping": True}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(convert(args.source, args.output), indent=2))
