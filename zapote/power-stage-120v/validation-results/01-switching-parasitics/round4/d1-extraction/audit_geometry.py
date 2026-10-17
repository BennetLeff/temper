#!/usr/bin/env python3
"""Audit exact native-15 copper and define directed D1 conductive ports."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from shapely.affinity import scale
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
BOARD_SHA = "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155"
COPPER = HERE / "extraction/native15-flashed-copper.json.gz"
PORTS = UNIT / "validation-results/01-switching-parasitics/round3/a2-inductance/outputs/annotated_ports.json"
LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")

# A port's positive current runs from its first pad to its second.  The
# external capacitors, resistor chips, driver and MOSFET junctions are NOT
# shorted in this copper-only topology.
BRANCHES = {
    "A": (
        ("P_BUS_C38", "C38.1", "Q2.2", "bus_p"),
        ("P_BUS_C39", "C39.1", "Q2.2", "bus_p"),
        ("P_SW", "Q2.3", "Q3.2", "sw_a"),
        ("P_SOURCE", "Q3.3", "R5.1", "leg_ret"),
        ("P_RETURN_C38", "R5.4", "C38.2", "hv_ret"),
        ("P_RETURN_C39", "R5.4", "C39.2", "hv_ret"),
        ("GH_OUT", "U1.15", "R10.1", "leg_a-out_h"),
        ("GH_GATE", "R10.2", "Q2.1", "leg_a-gate_h"),
        ("GH_RETURN", "Q2.3", "U1.14", "sw_a"),
        ("GL_OUT", "U1.10", "R12.1", "leg_a-out_l"),
        ("GL_GATE", "R12.2", "Q3.1", "leg_a-gate_l"),
        ("GL_RETURN", "Q3.3", "U1.9", "leg_ret"),
    ),
    "B": (
        ("P_BUS_C40", "C40.1", "Q5.2", "bus_p"),
        ("P_BUS_C41", "C41.1", "Q5.2", "bus_p"),
        ("P_SW", "Q5.3", "Q6.2", "sw_b"),
        ("P_SOURCE", "Q6.3", "R5.1", "leg_ret"),
        ("P_RETURN_C40", "R5.4", "C40.2", "hv_ret"),
        ("P_RETURN_C41", "R5.4", "C41.2", "hv_ret"),
        ("GH_OUT", "U2.15", "R18.1", "leg_b-out_h"),
        ("GH_GATE", "R18.2", "Q5.1", "leg_b-gate_h"),
        ("GH_RETURN", "Q5.3", "U2.14", "sw_b"),
        ("GL_OUT", "U2.10", "R20.1", "leg_b-out_l"),
        ("GL_GATE", "R20.2", "Q6.1", "leg_b-gate_l"),
        ("GL_RETURN", "Q6.3", "U2.9", "leg_ret"),
    ),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drilled_void(item: dict):
    drill = item.get("drill_mm", 0.0)
    dx, dy = (drill if isinstance(drill, list) else (drill, drill))
    if dx <= 0 or dy <= 0:
        return None
    # Exported native pad polygons contain the copper outer shape but not the
    # drill.  A plated barrel/lead needs a separate 3-D conductor, not a solid
    # planar disc through the open bore.
    disk = Point(item["centre"]).buffer(1.0, resolution=64)
    return scale(disk, xfact=dx / 2, yfact=dy / 2, origin=tuple(item["centre"]))


def board_drill_voids(dataset: dict) -> dict:
    """Physical bores remove copper from final zone/track/pad unions too."""
    by_layer = defaultdict(list)
    for barrel in dataset["barrels"]:
        void = drilled_void(barrel)
        if void is None:
            continue
        start, end = (LAYERS.index(layer) for layer in barrel["physical_span_layers"])
        for layer in LAYERS[min(start,end):max(start,end)+1]:
            by_layer[layer].append(void)
    return {layer: unary_union(shapes) for layer, shapes in by_layer.items()}


def primitive_shape(item: dict):
    if item["kind"] in ("zone", "pad"):
        polygon = Polygon(item["shell"], item.get("holes", []))
        if not polygon.is_valid:
            raise ValueError(f"invalid KiCad polygon after Unfracture: {item['kind']} {item.get('ref')} {item['net']} {item['layer']}")
        shape = polygon
        void = drilled_void(item)
        return shape.difference(void) if void is not None else shape
    if item["kind"] == "track":
        return LineString((item["start"], item["end"])).buffer(item["width_mm"] / 2)
    if item["kind"] == "via":
        disk = Point(item["centre"]).buffer(item["diameter_mm"] / 2)
        void = drilled_void(item)
        return disk.difference(void) if void is not None else disk
    raise ValueError(item["kind"])


def main() -> None:
    board = UNIT / "native-15/section.kicad_pcb"
    dataset = json.load(gzip.open(COPPER, "rt"))
    port_data = json.loads(PORTS.read_text())
    if {digest(board), dataset["board_sha256"], port_data["board_sha256"]} != {BOARD_SHA}:
        raise ValueError("board/native KiCad copper/port hashes disagree")
    primitives = dataset["primitives"]
    pad_refs = defaultdict(list)
    barrel_by_ref = {}
    for barrel in dataset["barrels"]:
        if barrel["kind"] == "pad":
            barrel_by_ref[barrel["ref"]] = barrel
    for item in primitives:
        if item["kind"] == "pad":
            pad_refs[item["ref"]].append(item)
    port_map = {"board_sha256": BOARD_SHA,
                "copper_export_sha256": digest(COPPER),
                "port_source_sha256": digest(PORTS),
                "direction": "positive current from first_ref to second_ref",
                "external_components_not_shortened": True,
                "legs": {}}
    relevant_nets = set()
    for leg, branches in BRANCHES.items():
        rows = []
        for name, first, second, net in branches:
            a, b = port_data["ports"][first], port_data["ports"][second]
            if a["net"] != net or b["net"] != net:
                raise ValueError(f"{leg}/{name}: port net mismatch")
            if not any(p["net"] == net for p in pad_refs[first]) or not any(p["net"] == net for p in pad_refs[second]):
                raise ValueError(f"{leg}/{name}: native KiCad pad absent")
            relevant_nets.add(net)
            from_layers = [layer for layer in LAYERS if any(p["net"] == net and p["layer"] == layer for p in pad_refs[first])]
            to_layers = [layer for layer in LAYERS if any(p["net"] == net and p["layer"] == layer for p in pad_refs[second])]
            from_terminal_layer = barrel_by_ref[first]["component_side"] if first in barrel_by_ref else from_layers[0]
            to_terminal_layer = barrel_by_ref[second]["component_side"] if second in barrel_by_ref else to_layers[0]
            rows.append({"name": name, "from_ref": first, "to_ref": second, "net": net,
                         "from_xy_mm": a["centre_mm"], "to_xy_mm": b["centre_mm"],
                         "from_layers": from_layers, "to_layers": to_layers,
                         "from_terminal_layer": from_terminal_layer,
                         "to_terminal_layer": to_terminal_layer})
        port_map["legs"][leg] = rows
    grouped = defaultdict(list)
    bores = board_drill_voids(dataset)
    counts = Counter()
    zone_vertices = 0
    hole_vertices = 0
    for item in primitives:
        if item["net"] in relevant_nets:
            grouped[item["net"], item["layer"]].append(primitive_shape(item))
            counts[item["kind"]] += 1
            if item["kind"] == "zone":
                zone_vertices += len(item["shell"])
                hole_vertices += sum(len(h) for h in item.get("holes", []))
    rows = []
    for (net, layer), shapes in sorted(grouped.items()):
        merged = unary_union(shapes).difference(bores.get(layer, Polygon()))
        polygons = [merged] if merged.geom_type == "Polygon" else list(merged.geoms) if merged.geom_type == "MultiPolygon" else []
        rows.append({"net": net, "layer": layer, "primitive_count": len(shapes),
                     "planar_copper_area_mm2_after_drills": merged.area, "polygon_components": len(polygons),
                     "exact_polygon_interiors": sum(len(p.interiors) for p in polygons),
                     "bounds_mm": list(merged.bounds) if not merged.is_empty else None})
    feasibility = {"board_sha256": BOARD_SHA, "source_export": str(COPPER.relative_to(UNIT)),
                   "source_export_sha256": digest(COPPER),
                   "kicad_version": dataset["kicad_version"],
                   "relevant_net_count": len(relevant_nets),
                   "relevant_primitive_count_by_kind": dict(counts),
                   "zone_shell_vertices": zone_vertices,
                   "raw_zone_hole_vertices": hole_vertices,
                   "note": "KiCad Unfracture restored explicit hole rings; only pad/via annuli with FlashLayer true are present.",
                   "net_layers": rows,
                   "fast_henry_geometry_gap": "Uniform G supports rectangular/circular/point holes, but actual filled copper has irregular shell and pad contours. Nonuniform G contact refinement cannot use the hole utility (pinned source nonuniform plane manual, page 1). No qualified mesh or interlayer barrel connectors have been generated.",
                   "round3_raster_evidence": {},
                   "uniform_G_local_roi_node_estimate": {}}
    for _pitch, name in ((0.5, "0p5"), (0.25, "0p25")):
        data = json.loads((UNIT / f"validation-results/01-switching-parasitics/round3/a2-inductance/outputs/connected_routes_{name}.json").read_text())
        feasibility["round3_raster_evidence"][f"Q3_source_return_{name}_mm"] = data["paths"]["Q3_return"]["status"]
    # These are allocation estimates, NOT a qualified field-domain cut.
    rois = {"A": (124, 0, 166, 43), "B": (85, 0, 129, 43)}
    paths = json.loads((UNIT / "validation-results/01-switching-parasitics/round3/a2-inductance/outputs/connected_routes_0p25.json").read_text())["paths"]
    for leg, (x0, y0, x1, y1) in rois.items():
        used_names = {"A": ("A_bus_C38", "A_bus_C39", "A_switch", "A_source_shunt", "A_shunt_C38", "A_shunt_C39", "Q2_return", "Q3_return"),
                      "B": ("B_bus_C40", "B_bus_C41", "B_switch", "B_source_shunt", "B_shunt_C40", "B_shunt_C41", "Q5_return", "Q6_return")}[leg]
        used = [paths[name] for name in used_names]
        for value in used:
            for vertex in value.get("polyline", []):
                x, y = vertex["xy_mm"]
                if not (x0 <= x <= x1 and y0 <= y <= y1):
                    raise ValueError(f"{leg} local ROI excludes a saved connected route vertex")
        feasibility["uniform_G_local_roi_node_estimate"][leg] = {
            "roi_xy_mm": [x0, y0, x1, y1],
            "qualification": "UNQUALIFIED_CROP: contains saved shortest routes but excludes possible current spreading and coupling outside it",
            "nodes_per_layer_by_pitch_mm": {
                str(p): (math.ceil((x1-x0)/p)+1)*(math.ceil((y1-y0)/p)+1)
                for p in (0.5, 0.25, 0.125, 0.0625)
            },
        }
    (HERE / "port-map.json").write_text(json.dumps(port_map, indent=2) + "\n")
    (HERE / "geometry-feasibility.json").write_text(json.dumps(feasibility, indent=2) + "\n")
    print(f"PORTS PASS: {sum(map(len, port_map['legs'].values()))} directed pad/net-checked ports, {len(relevant_nets)} nets")
    print(f"GEOMETRY AUDIT: {sum(counts.values())} relevant primitives, {zone_vertices} zone shell vertices")


if __name__ == "__main__":
    main()
