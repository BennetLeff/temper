#!/usr/bin/env python3
"""Trace topological shortest routes on native copper, including plated vias.

The raster route is a connectivity/length witness, not an HF current
distribution. It uses KiCad-exported, hole-aware polygons and explicit
through-hole/via layer connectors; it never rotates a footprint itself.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import heapq
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
PATHS = {
    "A_bus_C38": ("C38.1", "Q2.2", "bus_p"),
    "A_bus_C39": ("C39.1", "Q2.2", "bus_p"),
    "A_switch": ("Q2.3", "Q3.2", "sw_a"),
    "A_source_shunt": ("Q3.3", "R5.1", "leg_ret"),
    "A_shunt_C38": ("R5.4", "C38.2", "hv_ret"),
    "A_shunt_C39": ("R5.4", "C39.2", "hv_ret"),
    "B_bus_C40": ("C40.1", "Q5.2", "bus_p"),
    "B_bus_C41": ("C41.1", "Q5.2", "bus_p"),
    "B_switch": ("Q5.3", "Q6.2", "sw_b"),
    "B_source_shunt": ("Q6.3", "R5.1", "leg_ret"),
    "B_shunt_C40": ("R5.4", "C40.2", "hv_ret"),
    "B_shunt_C41": ("R5.4", "C41.2", "hv_ret"),
    "Q2_return": ("Q2.3", "U1.14", "sw_a"),
    "Q3_return": ("Q3.3", "U1.9", "leg_ret"),
    "Q5_return": ("Q5.3", "U2.14", "sw_b"),
    "Q6_return": ("Q6.3", "U2.9", "leg_ret"),
    "A_bulk_bus": ("C6.1", "C39.1", "bus_p"),
    "A_bulk_return": ("C6.3", "C39.2", "hv_ret"),
    "B_bulk_bus": ("C5.1", "C41.1", "bus_p"),
    "B_bulk_return": ("C5.3", "C41.2", "hv_ret"),
    "A_bulk_alt_bus": ("C5.1", "C39.1", "bus_p"),
    "A_bulk_alt_return": ("C5.3", "C39.2", "hv_ret"),
    "B_bulk_alt_bus": ("C6.1", "C41.1", "bus_p"),
    "B_bulk_alt_return": ("C6.3", "C41.2", "hv_ret"),
}


def load(path: Path) -> dict[str, Any]:
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as handle:
        return json.load(handle)


def z_centres_mm(stack: dict[str, Any]) -> dict[str, float]:
    z = 0.0
    centres = {}
    for layer in stack["layers"]:
        thickness = layer["thickness_mm"]
        if layer["type"] == "copper":
            centres[layer["name"]] = z + thickness / 2
        z += thickness
    if set(centres) != set(LAYERS):
        raise ValueError("unexpected copper stackup")
    first = centres["F.Cu"]
    return {name: value - first for name, value in centres.items()}


def shape(item: dict[str, Any]):
    if item["kind"] in {"zone", "pad"}:
        polygon = Polygon(item["shell"], item.get("holes", []))
        return polygon if polygon.is_valid else polygon.buffer(0)
    if item["kind"] == "track":
        return LineString([item["start"], item["end"]]).buffer(item["width_mm"] / 2)
    if item["kind"] == "via":
        return Point(item["centre"]).buffer(item["diameter_mm"] / 2)
    raise ValueError(item["kind"])


def connected_shapes(primitives: list[dict[str, Any]], net: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    shapes = {layer: [] for layer in LAYERS}
    connectors = {}
    for item in primitives:
        if item["net"] != net:
            continue
        shapes[item["layer"]].append(shape(item))
        drill = item.get("drill_mm")
        diameter = max(drill) if isinstance(drill, list) else drill
        if item["kind"] == "via" or (item["kind"] == "pad" and diameter is not None and diameter > 0):
            key = (item.get("ref", "via"), tuple(item["centre"]))
            connectors[key] = {"ref": item.get("ref"), "centre": item["centre"],
                               "drill_mm": item["drill_mm"],
                               "radius_mm": (item.get("diameter_mm") or 1.6) / 2}
    return {layer: unary_union(shapes[layer]) for layer in LAYERS}, list(connectors.values())


def grid_for_route(geoms: dict[str, Any], connectors: list[dict[str, Any]],
                   a: list[float], b: list[float], pitch: float,
                   margin: float = 30.0) -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
    x0 = math.floor((min(a[0], b[0]) - margin) / pitch) * pitch
    x1 = math.ceil((max(a[0], b[0]) + margin) / pitch) * pitch
    y0 = math.floor((min(a[1], b[1]) - margin) / pitch) * pitch
    y1 = math.ceil((max(a[1], b[1]) + margin) / pitch) * pitch
    xx = np.arange(x0, x1 + pitch / 2, pitch)
    yy = np.arange(y0, y1 + pitch / 2, pitch)
    xgrid, ygrid = np.meshgrid(xx, yy)
    occupied = np.stack([shapely.intersects_xy(geoms[layer], xgrid, ygrid) for layer in LAYERS])
    vertical = np.zeros_like(occupied[0])
    for connector in connectors:
        x, y = connector["centre"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            drill = connector["drill_mm"]
            drill_diameter = max(drill) if isinstance(drill, list) else drill
            radius = max(drill_diameter / 2, pitch * 0.75)
            mask = (xgrid - x) ** 2 + (ygrid - y) ** 2 <= radius ** 2
            vertical |= mask
            occupied[:, mask] = True  # plated barrel connects all four layers
    return occupied, vertical, (x0, y0)


def nearest_start(occupied: np.ndarray, coord: list[float], origin: tuple[float, float],
                  pitch: float) -> tuple[int, int, int]:
    cx = round((coord[0] - origin[0]) / pitch)
    cy = round((coord[1] - origin[1]) / pitch)
    _, ny, nx = occupied.shape
    candidates = []
    for radius in range(0, math.ceil(2 / pitch) + 1):
        for row in range(max(0, cy - radius), min(ny, cy + radius + 1)):
            for col in range(max(0, cx - radius), min(nx, cx + radius + 1)):
                for layer in range(4):
                    if occupied[layer, row, col]:
                        d = math.hypot((col - cx) * pitch, (row - cy) * pitch)
                        candidates.append((d, layer, row, col))
        if candidates:
            _, layer, row, col = min(candidates)
            return layer, row, col
    raise ValueError(f"no copper within 2 mm of port {coord}")


def route(occupied: np.ndarray, vertical: np.ndarray, origin: tuple[float, float],
          pitch: float, z: dict[str, float], start: list[float], end: list[float]) -> dict[str, Any]:
    s = nearest_start(occupied, start, origin, pitch)
    t = nearest_start(occupied, end, origin, pitch)
    _, ny, nx = occupied.shape
    zvals = [z[layer] for layer in LAYERS]

    def heuristic(node: tuple[int, int, int]) -> float:
        layer, row, col = node
        return math.sqrt(((col - t[2]) * pitch) ** 2 + ((row - t[1]) * pitch) ** 2 +
                         (zvals[layer] - zvals[t[0]]) ** 2)

    heap = [(heuristic(s), 0.0, s)]
    best = {s: 0.0}
    parent = {}
    shifts = ((1, 0), (-1, 0), (0, 1), (0, -1),
              (1, 1), (1, -1), (-1, 1), (-1, -1))
    while heap:
        _, cost, node = heapq.heappop(heap)
        if cost > best[node] + 1e-12:
            continue
        if node == t:
            break
        layer, row, col = node
        for dr, dc in shifts:
            rr, cc = row + dr, col + dc
            if not (0 <= rr < ny and 0 <= cc < nx and occupied[layer, rr, cc]):
                continue
            if dr and dc and not (occupied[layer, row + dr, col] and occupied[layer, row, col + dc]):
                continue
            other = (layer, rr, cc)
            new_cost = cost + pitch * math.hypot(dr, dc)
            if new_cost + 1e-12 < best.get(other, math.inf):
                best[other] = new_cost
                parent[other] = node
                heapq.heappush(heap, (new_cost + heuristic(other), new_cost, other))
        if vertical[row, col]:
            for other_layer in (layer - 1, layer + 1):
                if 0 <= other_layer < 4 and occupied[other_layer, row, col]:
                    other = (other_layer, row, col)
                    new_cost = cost + abs(zvals[layer] - zvals[other_layer])
                    if new_cost + 1e-12 < best.get(other, math.inf):
                        best[other] = new_cost
                        parent[other] = node
                        heapq.heappush(heap, (new_cost + heuristic(other), new_cost, other))
    else:
        return {"status": "NO_CONNECTED_ROUTE", "start_grid": s, "end_grid": t,
                "visited_nodes": len(best)}
    nodes = [t]
    while nodes[-1] != s:
        nodes.append(parent[nodes[-1]])
    nodes.reverse()
    changes = [nodes[0]]
    for i in range(1, len(nodes) - 1):
        before = tuple(nodes[i][j] - nodes[i - 1][j] for j in range(3))
        after = tuple(nodes[i + 1][j] - nodes[i][j] for j in range(3))
        if before != after:
            changes.append(nodes[i])
    changes.append(nodes[-1])
    vertices = [{"layer": LAYERS[layer], "xy_mm": [round(origin[0] + col * pitch, 6),
                                                   round(origin[1] + row * pitch, 6)]}
                for layer, row, col in changes]
    transitions = [{"from_layer": LAYERS[a[0]], "to_layer": LAYERS[b[0]],
                    "xy_mm": [round(origin[0] + a[2] * pitch, 6), round(origin[1] + a[1] * pitch, 6)]}
                   for a, b in zip(nodes, nodes[1:]) if a[0] != b[0]]
    return {"status": "CONNECTED_RASTER_ROUTE", "pitch_mm": pitch,
            "length_mm": best[t], "nodes": len(nodes), "visited_nodes": len(best),
            "start_port_offset_mm": math.hypot(start[0] - vertices[0]["xy_mm"][0],
                                                start[1] - vertices[0]["xy_mm"][1]),
            "end_port_offset_mm": math.hypot(end[0] - vertices[-1]["xy_mm"][0],
                                              end[1] - vertices[-1]["xy_mm"][1]),
            "layer_transitions": transitions, "polyline": vertices}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pitch", type=float, default=0.5)
    args = parser.parse_args()
    board = args.unit / "native-15/section.kicad_pcb"
    detailed = load(args.inputs / "power_copper_with_holes.json.gz")
    probe = load(args.inputs / "vias-and-pads.json")
    board_sha = hashlib.sha256(board.read_bytes()).hexdigest()
    if len({board_sha, detailed["board_sha256"], probe["board_sha256"]}) != 1:
        raise ValueError("board/geometry hashes differ")
    pads = {p["ref"]: p for p in probe["pads"]}
    # The native-15 bulk-cap pads were not selected by the earlier task-01
    # probe. Read their centres from the same native KiCad-exported primitives.
    for item in detailed["primitives"]:
        if item["kind"] == "pad" and item.get("ref", "").startswith(("C5.", "C6.")):
            pads[item["ref"]] = {"ref": item["ref"], "net": item["net"],
                                  "centre_mm": item["centre"]}
    z = z_centres_mm(load(args.unit / "stackup.json"))
    cache = {}
    output = {"board_sha256": board_sha, "pitch_mm": args.pitch, "z_centres_mm": z,
              "method": "8-neighbour shortest raster path through hole-aware copper; plated-barrel vertical edges",
              "limitation": "geometry witness only, not physical 10 MHz current density or unique return-current route",
              "paths": {}}
    for name, (start_ref, end_ref, net) in PATHS.items():
        a, b = pads[start_ref], pads[end_ref]
        if a["net"] != net or b["net"] != net:
            raise ValueError(f"port net mismatch: {name}")
        if net not in cache:
            cache[net] = connected_shapes(detailed["primitives"], net)
        geoms, connectors = cache[net]
        occupied, vertical, origin = grid_for_route(geoms, connectors, a["centre_mm"], b["centre_mm"], args.pitch)
        result = route(occupied, vertical, origin, args.pitch, z, a["centre_mm"], b["centre_mm"])
        output["paths"][name] = {"net": net, "ports": [start_ref, end_ref],
                                 "port_centres_mm": [a["centre_mm"], b["centre_mm"]], **result}
        print(name, result["status"], round(result.get("length_mm", math.nan), 3), flush=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
