"""Convert a Gmsh 2.2 binary mesh to 2.2 ASCII for pinned ElmerGrid.

The ElmerGrid fallback used here rejects Gmsh 2.2 binary input.  Conversion
changes serialization only; physical groups and element counts are checked.
"""

import argparse
import json
from pathlib import Path

import gmsh
import numpy as np


def snapshot() -> tuple[list, np.ndarray, np.ndarray, dict]:
    groups = sorted((dim, tag, gmsh.model.getPhysicalName(dim, tag),
                     tuple(sorted(int(item) for item in gmsh.model.getEntitiesForPhysicalGroup(dim, tag))))
                    for dim, tag in gmsh.model.getPhysicalGroups())
    node_tags, coordinates, _ = gmsh.model.mesh.getNodes()
    node_order = np.argsort(node_tags)
    sorted_node_tags = node_tags[node_order].copy()
    sorted_coordinates = coordinates.reshape(-1, 3)[node_order].copy()
    elements = {}
    for dimension in range(4):
        types, tags_by_type, nodes_by_type = gmsh.model.mesh.getElements(dimension)
        for element_type, tags, nodes in zip(types, tags_by_type, nodes_by_type, strict=True):
            nodes_per_element = len(nodes) // len(tags)
            order = np.argsort(tags)
            elements[(dimension, int(element_type))] = (
                tags[order].copy(), nodes.reshape(-1, nodes_per_element)[order].copy())
    return groups, sorted_node_tags, sorted_coordinates, elements


def convert(source: Path, output: Path) -> dict:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(source))
        before = snapshot()
        tetrahedra = len(before[3].get((3, 4), ([], []))[0])
        if tetrahedra == 0 or any(dim == 3 and kind != 4 for dim, kind in before[3]):
            raise ValueError("expected nonempty first-order tetrahedral volume mesh")
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.Binary", 0)
        output.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(output))
        gmsh.clear()
        gmsh.open(str(output))
        after = snapshot()
        if before[0] != after[0]:
            raise ValueError("physical groups changed in ASCII roundtrip")
        # Gmsh may renumber node IDs during binary-to-ASCII serialization.
        # Match unique coordinates, then compare oriented connectivity after
        # mapping output IDs back to input IDs.
        def coordinate_key(coordinates: np.ndarray) -> tuple:
            return tuple(float(value) for value in np.round(coordinates, 9))

        input_by_coordinate = {coordinate_key(coords): int(tag)
                               for tag, coords in zip(before[1], before[2], strict=True)}
        if len(input_by_coordinate) != len(before[1]) or len(after[1]) != len(before[1]):
            raise ValueError("ambiguous or changed node coordinates in ASCII roundtrip")
        output_to_input = {}
        coordinate_delta = 0.0
        for output_tag, output_coords in zip(after[1], after[2], strict=True):
            input_tag = input_by_coordinate.get(coordinate_key(output_coords))
            if input_tag is None:
                raise ValueError("output node has no input coordinate match")
            input_index = int(np.searchsorted(before[1], input_tag))
            coordinate_delta = max(coordinate_delta,
                                   float(np.max(np.abs(before[2][input_index] - output_coords))))
            output_to_input[int(output_tag)] = input_tag
        if len(set(output_to_input.values())) != len(before[1]) or coordinate_delta > 1e-9:
            raise ValueError(f"node coordinate matching failed; max delta {coordinate_delta} mm")
        if before[3].keys() != after[3].keys():
            raise ValueError("element families changed in ASCII roundtrip")
        for key in before[3]:
            if not np.array_equal(before[3][key][0], after[3][key][0]):
                raise ValueError(f"element IDs changed for {key}")
            output_nodes = after[3][key][1]
            remapped = np.fromiter((output_to_input[int(node)] for node in output_nodes.flat),
                                   dtype=np.int64, count=output_nodes.size).reshape(output_nodes.shape)
            if not np.array_equal(before[3][key][1], remapped):
                raise ValueError(f"element connectivity changed for {key}")
        return {"source": str(source), "output": str(output),
                "tetrahedra": tetrahedra, "physical_groups": before[0],
                "roundtrip_max_coordinate_delta_mm": coordinate_delta,
                "roundtrip_oriented_connectivity_equal_after_node_mapping": True}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(convert(args.source, args.output), indent=2))
