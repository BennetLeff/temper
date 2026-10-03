#!/usr/bin/env python3
"""Check whether the kit's raster graph crosses real native-13 copper gaps.

Every accepted neighbour pair in sheet_solver.Net should have a copper path
between its cell centres. This probe checks the segment midpoint, a necessary
condition. It also demonstrates the generic false connection with two strips.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[3] / "validation-plan/sim-kit/04-current/sheet_solver.py"
spec = importlib.util.spec_from_file_location("kit_sheet_solver", KIT)
solver = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(solver)


def generic_probe() -> dict:
    net = solver.Net(pitch_mm=0.25)
    net.add_layer("F.Cu", [[(0, 0), (0.4, 0), (0.4, 1), (0, 1)],
                           [(0.6, 0), (1, 0), (1, 1), (0.6, 1)]], 70)
    try:
        result = net.solve([("F.Cu", 0.375, 0.375, 1.0)], [("F.Cu", 0.625, 0.375)])
        return {"physical_gap_mm": 0.2, "pitch_mm": 0.25,
                "solver_accepted": True, "false_resistance_ohm": result["r_ohm"]}
    except ValueError as exc:
        return {"physical_gap_mm": 0.2, "pitch_mm": 0.25,
                "solver_accepted": False, "diagnostic": str(exc)}


def geometry(items: list[dict]):
    copper = []
    drill_voids = []
    for item in items:
        kind = item["kind"]
        if kind in ("zone", "pad"):
            copper.append(Polygon(item["shell"], item["holes"]))
            if kind == "pad" and item["drill_mm"][0] > 0:
                if abs(item["drill_mm"][0] - item["drill_mm"][1]) > 1e-9:
                    raise ValueError(f"slot drill requires explicit geometry: {item['ref']}")
                drill_voids.append(Point(item["centre"]).buffer(item["drill_mm"][0] / 2, resolution=32))
        elif kind == "track":
            copper.append(LineString([item["start"], item["end"]]).buffer(item["width_mm"] / 2, resolution=16))
        elif kind == "via":
            copper.append(Point(item["centre"]).buffer(item["diameter_mm"] / 2, resolution=32))
            drill_voids.append(Point(item["centre"]).buffer(item["drill_mm"] / 2, resolution=32))
        else:
            raise ValueError(f"unsupported copper kind: {kind}")
    return unary_union(copper).difference(unary_union(drill_voids)) if drill_voids else unary_union(copper)


def audit(geom, pitch: float) -> dict:
    x0, y0, x1, y1 = geom.bounds
    xs = np.arange(x0 + pitch / 2, x1, pitch)
    ys = np.arange(y0 + pitch / 2, y1, pitch)
    xx, yy = np.meshgrid(xs, ys, indexing="ij")
    inside = contains_xy(geom, xx, yy)
    # A midpoint outside copper proves the graph edge crosses a void. A
    # midpoint inside is not sufficient to prove an entire edge is copper.
    x_adj = inside[:-1, :] & inside[1:, :]
    x_mid = contains_xy(geom, xx[:-1, :] + pitch / 2, yy[:-1, :])
    x_bad = np.argwhere(x_adj & ~x_mid)
    y_adj = inside[:, :-1] & inside[:, 1:]
    y_mid = contains_xy(geom, xx[:, :-1], yy[:, :-1] + pitch / 2)
    y_bad = np.argwhere(y_adj & ~y_mid)
    components = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    examples = []
    physical_component_crossings = 0
    for axis, bad in (("x", x_bad), ("y", y_bad)):
        for i, j in bad:
            endpoints = ([[float(xs[i]), float(ys[j])], [float(xs[i + 1]), float(ys[j])]]
                         if axis == "x" else
                         [[float(xs[i]), float(ys[j])], [float(xs[i]), float(ys[j + 1])]])
            component_ids = [next((k for k, part in enumerate(components)
                                   if part.covers(Point(*xy))), None) for xy in endpoints]
            crosses_component = component_ids[0] != component_ids[1]
            physical_component_crossings += crosses_component
            if len(examples) < 6 or crosses_component:
                midpoint = [(a + b) / 2 for a, b in zip(*endpoints)]
                examples.append({"axis": axis, "endpoints_mm": endpoints,
                                 "midpoint_mm": midpoint,
                                 "physical_component_ids": component_ids})
    return {"grid_nodes": int(inside.sum()), "adjacent_pairs": int(x_adj.sum() + y_adj.sum()),
            "proven_void_crossing_edges": int(len(x_bad) + len(y_bad)),
            "physical_component_crossing_edges": int(physical_component_crossings),
            "examples": examples}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: audit_raster_topology.py <power_copper.json.gz> <out.json>")
    with gzip.open(sys.argv[1], "rt") as stream:
        evidence = json.load(stream)
    grouped = defaultdict(list)
    for item in evidence["primitives"]:
        grouped[(item["net"], item["layer"])].append(item)
    result = {"board_sha256": evidence["board_sha256"], "pitch_mm": 0.25,
              "generic_probe": generic_probe(), "native13": {},
              "drilled_contact_centres": []}
    for (net, layer), items in sorted(grouped.items()):
        geom = geometry(items)
        result["native13"][f"{net}/{layer}"] = audit(geom, 0.25)
        if layer == "F.Cu":
            for item in items:
                if ((item["kind"] == "pad" and item.get("ref") in
                     {"Q2.2", "Q5.2", "C38.1", "C39.1", "C40.1", "C41.1"})
                    or (item["kind"] == "via" and item["centre"] == [68.5, 54.8])):
                    result["drilled_contact_centres"].append({
                        "net": net, "layer": layer, "kind": item["kind"],
                        "ref": item.get("ref"), "centre_mm": item["centre"],
                        "centre_is_copper": bool(geom.covers(Point(item["centre"])))})
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"generic_probe": result["generic_probe"],
                      "native13_void_crossing_edges": {k: v["proven_void_crossing_edges"]
                                                       for k, v in result["native13"].items()},
                      "native13_component_crossing_edges": {k: v["physical_component_crossing_edges"]
                                                            for k, v in result["native13"].items()}}))


if __name__ == "__main__":
    main()
