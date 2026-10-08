#!/usr/bin/env python3
"""Measure native-copper ROI and mesh scale before attempting a field deck."""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from shapely.affinity import scale
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
RAW = HERE / "extraction/native17-power-and-gates.json.gz"
LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bore(item: dict):
    drill = item.get("drill_mm", 0)
    dx, dy = (drill if isinstance(drill, list) else (drill, drill))
    if dx <= 0 or dy <= 0:
        return None
    cx, cy = item["centre"]
    return scale(Point(cx, cy).buffer(1, resolution=64), xfact=dx / 2, yfact=dy / 2,
                 origin=(cx, cy))


def shape(item: dict):
    kind = item["kind"]
    if kind in ("zone", "pad"):
        result = Polygon(item["shell"], item.get("holes", []))
        if not result.is_valid:
            raise ValueError(f"invalid {kind} polygon {item.get('ref', '')}")
        return result
    if kind == "track":
        return LineString((item["start"], item["end"])).buffer(item["width_mm"] / 2)
    if kind == "via":
        return Point(item["centre"]).buffer(item["diameter_mm"] / 2)
    raise ValueError(kind)


def main() -> None:
    raw = json.load(gzip.open(RAW, "rt"))
    port_map_path = HERE / "port-map.json"
    port_map = json.loads(port_map_path.read_text())
    if raw["board_sha256"] != port_map["board_sha256"] or sha(RAW) != port_map["copper_export_sha256"]:
        raise ValueError("native export/port map mismatch")
    by_nl = defaultdict(list)
    for item in raw["primitives"]:
        if item["layer"] in LAYERS:
            by_nl[item["net"], item["layer"]].append(shape(item))
    bores = defaultdict(list)
    for item in raw["barrels"]:
        hole = bore(item)
        if hole is None:
            continue
        a, b = (LAYERS.index(layer) for layer in item["physical_span_layers"])
        for layer in LAYERS[min(a, b):max(a, b) + 1]:
            bores[layer].append(hole)
    bore_geom = {layer: unary_union(items) for layer, items in bores.items()}
    geoms = {key: unary_union(items).difference(bore_geom.get(key[1], Polygon()))
             for key, items in by_nl.items()}
    result = {"board_sha256": raw["board_sha256"], "export_sha256": sha(RAW),
              "port_map_sha256": sha(port_map_path), "mesh_counts_are": "area/pitch^2 estimates, not emitted solver nodes",
              "legs": {}}
    for leg, ports in port_map["legs"].items():
        nets = {p["net"] for p in ports}
        xy = [p[key] for p in ports for key in ("from_xy_mm", "to_xy_mm")]
        x0 = min(p[0] for p in xy)
        x1 = max(p[0] for p in xy)
        y0 = min(p[1] for p in xy)
        y1 = max(p[1] for p in xy)
        rows = {}
        for margin in (5, 10, 20, 40):
            roi = (x0 - margin, y0 - margin, x1 + margin, y1 + margin)
            region = box(*roi)
            xmin, ymin, xmax, ymax = roi
            sides = {
                "left": LineString(((xmin, ymin), (xmin, ymax))),
                "right": LineString(((xmax, ymin), (xmax, ymax))),
                "top": LineString(((xmin, ymin), (xmax, ymin))),
                "bottom": LineString(((xmin, ymax), (xmax, ymax))),
            }
            occupied_area = 0.0
            cuts = []
            for (net, layer), geom in geoms.items():
                if net not in nets:
                    continue
                occupied_area += geom.intersection(region).area
                for side, line in sides.items():
                    length = geom.intersection(line).length
                    if length > 1e-6:
                        cuts.append({"net": net, "layer": layer, "side": side,
                                     "cross_section_length_mm": length})
            rows[str(margin)] = {
                "roi_xy_mm": roi, "roi_size_mm": [xmax - xmin, ymax - ymin],
                "occupied_area_all_net_layers_mm2": occupied_area,
                "estimated_occupied_grid_nodes": {str(p): round(occupied_area / p**2)
                                                  for p in (0.125, 0.0625)},
                "full_roi_grid_nodes_per_layer": {str(p): (round((xmax - xmin) / p) + 1)
                                                  * (round((ymax - ymin) / p) + 1)
                                                  for p in (0.125, 0.0625)},
                "cut_copper_net_layers": cuts,
            }
        result["legs"][leg] = {"pad_bbox_xy_mm": [x0, y0, x1, y1],
                               "native_branch_count": len(ports),
                               "relevant_net_count": len(nets), "margins_mm": rows}
    (HERE / "geometry-characterization.json").write_text(json.dumps(result, indent=2) + "\n")
    for leg, row in result["legs"].items():
        print(leg, "pad bbox", row["pad_bbox_xy_mm"])
        for margin, values in row["margins_mm"].items():
            print("  M", margin, "area", round(values["occupied_area_all_net_layers_mm2"]),
                  "nodes", values["estimated_occupied_grid_nodes"],
                  "cut net/layers", len({(c["net"], c["layer"]) for c in values["cut_copper_net_layers"]}))


if __name__ == "__main__":
    main()
