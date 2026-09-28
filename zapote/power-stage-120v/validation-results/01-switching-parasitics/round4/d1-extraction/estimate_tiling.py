#!/usr/bin/env python3
"""Estimate aligned uniform-G tiles and topology error from native copper.

This is a feasibility study. It does not emit a FastHenry board deck or call a
raster a physical high-frequency current distribution.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict

import numpy as np
import shapely
from audit_geometry import BOARD_SHA, COPPER, HERE, UNIT, board_drill_voids, digest, primitive_shape
from scipy import ndimage
from shapely.geometry import box
from shapely.ops import unary_union

LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
ROIS = {"A": (124.0, 0.0, 166.0, 43.0), "B": (85.0, 0.0, 129.0, 43.0)}


def components(geometry) -> list:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    if hasattr(geometry, "geoms"):
        return [part for piece in geometry.geoms for part in components(piece)]
    return []


def runs_per_row(occupied: np.ndarray) -> tuple[int, int]:
    patches = 0
    stitch_pairs = 0
    previous = np.zeros(occupied.shape[1], dtype=bool)
    for row in occupied:
        transitions = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        patches += int(np.count_nonzero(transitions == 1))
        # A contiguous run of n shared cells has n+1 distinct seam nodes.
        shared = row & previous
        shared_starts = np.diff(np.pad(shared.astype(np.int8), (1, 1))) == 1
        stitch_pairs += int(np.count_nonzero(shared) + np.count_nonzero(shared_starts))
        previous = row
    return patches, stitch_pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pitch", type=float, choices=(0.5, 0.25, 0.125, 0.0625), required=True)
    args = parser.parse_args()
    pitch = args.pitch
    board = UNIT / "native-15/section.kicad_pcb"
    native = json.load(gzip.open(COPPER, "rt"))
    ports = json.loads((HERE / "port-map.json").read_text())
    if {digest(board), native["board_sha256"], ports["board_sha256"]} != {BOARD_SHA}:
        raise ValueError("frozen board/copper/ports mismatch")
    shapes = defaultdict(list)
    bores = board_drill_voids(native)
    relevant = {leg: {item["net"] for item in port_list} for leg, port_list in ports["legs"].items()}
    for item in native["primitives"]:
        if any(item["net"] in names for names in relevant.values()):
            shapes[item["net"], item["layer"]].append(primitive_shape(item))
    report = {"pitch_mm": pitch, "board_sha256": BOARD_SHA,
              "model_class": "unqualified raster tile feasibility; no field solve",
              "roi_crop_not_qualified": True, "legs": {}}
    for leg, roi in ROIS.items():
        x0, y0, x1, y1 = roi
        xcentres = np.arange(x0 + pitch / 2, x1, pitch)
        ycentres = np.arange(y0 + pitch / 2, y1, pitch)
        gridx, gridy = np.meshgrid(xcentres, ycentres)
        leg_rows = []
        for net in sorted(relevant[leg]):
            for layer in LAYERS:
                items = shapes.get((net, layer), [])
                if not items:
                    continue
                exact = unary_union(items).difference(bores[layer]).intersection(box(*roi))
                if exact.is_empty:
                    continue
                occupied = shapely.intersects_xy(exact, gridx, gridy)
                raster_nodes = int(np.count_nonzero(occupied))
                patch_count, seam_pairs = runs_per_row(occupied)
                labels, raster_components = ndimage.label(occupied,
                    structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.int8))
                exact_parts = components(exact)
                exact_components = len(exact_parts)
                raster_to_exact = defaultdict(set)
                missing_exact = 0
                split_exact = 0
                for part_index, part in enumerate(exact_parts):
                    bx0, by0, bx1, by1 = part.bounds
                    i0 = int(np.searchsorted(xcentres, bx0, side="left"))
                    i1 = int(np.searchsorted(xcentres, bx1, side="right"))
                    j0 = int(np.searchsorted(ycentres, by0, side="left"))
                    j1 = int(np.searchsorted(ycentres, by1, side="right"))
                    if i0 == i1 or j0 == j1:
                        missing_exact += 1
                        continue
                    part_nodes = shapely.intersects_xy(part, gridx[j0:j1, i0:i1], gridy[j0:j1, i0:i1])
                    seen = {int(label) for label in np.unique(labels[j0:j1, i0:i1][part_nodes]) if label > 0}
                    if not seen:
                        missing_exact += 1
                    if len(seen) > 1:
                        split_exact += 1
                    for label in seen:
                        raster_to_exact[label].add(part_index)
                false_join_raster = sum(len(part_ids) > 1 for part_ids in raster_to_exact.values())
                raster_area = raster_nodes * pitch**2
                leg_rows.append({"net": net, "layer": layer,
                                 "exact_area_mm2": exact.area,
                                 "raster_area_mm2": raster_area,
                                 "area_delta_percent": (raster_area / exact.area - 1) * 100,
                                 "exact_components": exact_components,
                                 "raster_components_4_connected": raster_components,
                                 "exact_components_missing_in_raster": missing_exact,
                                 "exact_components_split_in_raster": split_exact,
                                 "raster_components_falsely_joining_exact": false_join_raster,
                                 "raster_nodes": raster_nodes,
                                 "uniform_G_row_run_patches": patch_count,
                                 "minimum_aligned_seam_equiv_pairs": seam_pairs,
                                 "note": "cell-center classification; patch boundaries and seam nodes still require generated decks and independent topology proof"})
        report["legs"][leg] = {"roi_xy_mm": roi,
                               "roi_grid_nodes_per_layer": len(xcentres)*len(ycentres),
                               "sum_raster_nodes_across_net_layers": sum(row["raster_nodes"] for row in leg_rows),
                               "sum_G_patches": sum(row["uniform_G_row_run_patches"] for row in leg_rows),
                               "sum_aligned_seam_equiv_pairs_estimate": sum(row["minimum_aligned_seam_equiv_pairs"] for row in leg_rows),
                               "component_count_mismatches": sum(row["exact_components"] != row["raster_components_4_connected"] for row in leg_rows),
                               "topology_errors": sum(row["exact_components_missing_in_raster"] + row["exact_components_split_in_raster"] + row["raster_components_falsely_joining_exact"] for row in leg_rows),
                               "max_abs_area_delta_percent": max(abs(row["area_delta_percent"]) for row in leg_rows),
                               "net_layers": leg_rows}
    label = str(pitch).replace(".", "p")
    output = HERE / f"extraction/tile-estimate-{label}.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    for leg, row in report["legs"].items():
        print(leg, "grid", row["roi_grid_nodes_per_layer"], "filled", row["sum_raster_nodes_across_net_layers"],
              "patches", row["sum_G_patches"], "seams>=", row["sum_aligned_seam_equiv_pairs_estimate"],
              "component mismatches", row["component_count_mismatches"], "topology errors", row["topology_errors"],
              "max area delta %", round(row["max_abs_area_delta_percent"], 2))


if __name__ == "__main__":
    main()
