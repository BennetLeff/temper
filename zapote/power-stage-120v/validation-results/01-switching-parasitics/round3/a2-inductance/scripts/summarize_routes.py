#!/usr/bin/env python3
"""Turn connected copper routes into explicit exploratory L scenarios.

This is a documented ROUND-3 fallback after two failed FastHenry builds.
Scenarios use approximate straight-pair formulae on topological shortest
routes; they are neither field-solver values nor guaranteed bounds.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

from scipy.spatial import cKDTree

MU0 = 4 * math.pi * 1e-7
PAIRING = {
    "A_bus_C38": "A_shunt_C38", "A_bus_C39": "A_shunt_C39",
    "A_switch": "A_source_shunt", "A_source_shunt": "A_switch",
    "A_shunt_C38": "A_bus_C38", "A_shunt_C39": "A_bus_C39",
    "B_bus_C40": "B_shunt_C40", "B_bus_C41": "B_shunt_C41",
    "B_switch": "B_source_shunt", "B_source_shunt": "B_switch",
    "B_shunt_C40": "B_bus_C40", "B_shunt_C41": "B_bus_C41",
    "A_bulk_bus": "A_bulk_return", "A_bulk_return": "A_bulk_bus",
    "B_bulk_bus": "B_bulk_return", "B_bulk_return": "B_bulk_bus",
    "A_bulk_alt_bus": "A_bulk_alt_return", "A_bulk_alt_return": "A_bulk_alt_bus",
    "B_bulk_alt_bus": "B_bulk_alt_return", "B_bulk_alt_return": "B_bulk_alt_bus",
}
GATE_NETS = {
    "Q2": ("leg_a-out_h", "leg_a-gate_h", "Q2_return"),
    "Q3": ("leg_a-out_l", "leg_a-gate_l", "Q3_return"),
    "Q5": ("leg_b-out_h", "leg_b-gate_h", "Q5_return"),
    "Q6": ("leg_b-out_l", "leg_b-gate_l", "Q6_return"),
}


def load(path: Path) -> dict[str, Any]:
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as handle:
        return json.load(handle)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def points(route: dict[str, Any], z: dict[str, float], spacing: float = 0.25) -> list[tuple[float, float, float]]:
    vertices = route["polyline"]
    coords = [(v["xy_mm"][0], v["xy_mm"][1], z[v["layer"]]) for v in vertices]
    result = [coords[0]]
    for a, b in zip(coords, coords[1:]):
        length = math.dist(a, b)
        for i in range(1, max(1, math.ceil(length / spacing)) + 1):
            t = i / max(1, math.ceil(length / spacing))
            result.append(tuple(a[j] + t * (b[j] - a[j]) for j in range(3)))
    return result


def gap_to_adjacent(z: dict[str, float], layer: str) -> float:
    return min(abs(value - z[layer]) for other, value in z.items() if other != layer)


def width_proxy(net: str, copper: dict[str, Any]) -> float:
    widths = [item["width"] for item in copper["items"]
              if item["kind"] == "track" and item["net"] == net]
    return statistics.median(widths) if widths else 0.8


def via_l_nh(height_mm: float, drill_mm: float) -> float:
    return MU0 * 1e6 * height_mm / (2 * math.pi) * (math.log(4 * height_mm / drill_mm) + 1)


def connector_for(transition: dict[str, Any], net: str, detailed: dict[str, Any]) -> dict[str, Any] | None:
    target = transition["xy_mm"]
    candidates = {}
    for item in detailed["primitives"]:
        drill = item.get("drill_mm")
        diameter = max(drill) if isinstance(drill, list) else drill
        if item["net"] != net or item["kind"] not in ("pad", "via") or diameter is None or diameter <= 0:
            continue
        dist = math.dist(target, item["centre"])
        if dist < 1.0:
            key = (item.get("ref", "via"), tuple(item["centre"]))
            candidates[key] = (dist, item)
    if not candidates:
        return None
    _, item = min(candidates.values(), key=lambda pair: pair[0])
    drill = item["drill_mm"]
    return {"ref": item.get("ref", "via"), "centre_mm": item["centre"],
            "drill_mm": max(drill) if isinstance(drill, list) else drill}


def path_scenarios(name: str, route: dict[str, Any], partner: dict[str, Any],
                   z: dict[str, float], copper: dict[str, Any], detailed: dict[str, Any]) -> dict[str, Any]:
    if route["status"] != "CONNECTED_RASTER_ROUTE" or partner["status"] != "CONNECTED_RASTER_ROUTE":
        return {"status": "MISSING_CONNECTED_ROUTE"}
    net = route["net"]
    width = width_proxy(net, copper)
    partner_tree = cKDTree(points(partner, z))
    reference_plane = separated_pair = horizontal = 0.0
    separations = []
    for a, b in zip(route["polyline"], route["polyline"][1:]):
        if a["layer"] != b["layer"]:
            continue
        length = math.dist(a["xy_mm"], b["xy_mm"])
        if length == 0:
            continue
        horizontal += length
        gap = gap_to_adjacent(z, a["layer"])
        reference_plane += MU0 * 1e6 * gap * length / (width + 2 * gap)
        mid = ((a["xy_mm"][0] + b["xy_mm"][0]) / 2,
               (a["xy_mm"][1] + b["xy_mm"][1]) / 2, z[a["layer"]])
        d, _ = partner_tree.query(mid)
        d = max(d, width)  # round-wire pair formula needs conductor separation
        separations.append(d)
        separated_pair += MU0 * 1e6 * length / math.pi * math.log(2 * d / width)
    via_terms = []
    for transition in route["layer_transitions"]:
        connector = connector_for(transition, net, detailed)
        if connector is None:
            return {"status": "UNRESOLVED_VERTICAL_CONNECTOR", "transition": transition}
        h = abs(z[transition["from_layer"]] - z[transition["to_layer"]])
        value = via_l_nh(h, connector["drill_mm"])
        via_terms.append({**transition, **connector, "height_mm": h, "heuristic_nH": value})
    via_total = sum(item["heuristic_nH"] for item in via_terms)
    a, b = reference_plane + via_total, separated_pair + via_total
    return {
        "status": "COMPLETE_CONNECTED_ROUTE_HEURISTIC_SCENARIOS",
        "route_length_mm": route["length_mm"], "horizontal_length_mm": horizontal,
        "width_proxy_mm": width,
        "paired_route": PAIRING[name],
        "paired_route_separation_mm": [min(separations), statistics.median(separations), max(separations)] if separations else None,
        "vertical_connectors": via_terms,
        "reference_plane_case_nH": a,
        "separated_pair_case_nH": b,
        "scenario_min_nH": min(a, b), "scenario_max_nH": max(a, b),
        "ordering_reversed": a > b,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--outputs", required=True, type=Path)
    args = parser.parse_args()
    coarse = load(args.outputs / "connected_routes_0p5.json")
    fine = load(args.outputs / "connected_routes_0p25.json")
    copper = load(args.inputs / "copper.json.gz")
    detailed = load(args.inputs / "power_copper_with_holes.json.gz")
    probe = load(args.inputs / "vias-and-pads.json")
    gate_vias = load(args.inputs / "gate_vias.json")
    stack_path = args.unit / "stackup.json"
    board_path = args.unit / "native-15/section.kicad_pcb"
    board_sha = sha(board_path)
    if len({board_sha, coarse["board_sha256"], fine["board_sha256"], copper["board_sha256"], detailed["board_sha256"], gate_vias["board_sha256"]}) != 1:
        raise ValueError("source identity mismatch")
    z = fine["z_centres_mm"]
    routes = {}
    for name, path in fine["paths"].items():
        rough = coarse["paths"][name]
        change = (abs(rough["length_mm"] - path["length_mm"]) / path["length_mm"]
                  if rough["status"] == path["status"] == "CONNECTED_RASTER_ROUTE" else None)
        routes[name] = {"net": path["net"], "ports": path["ports"],
                        "coarse_length_mm": rough.get("length_mm"), "fine_length_mm": path.get("length_mm"),
                        "path_change_fraction": change,
                        "path_converged_within_5_percent": change is not None and change < 0.05,
                        "field_mesh_convergence": None,
                        "layer_transitions": path.get("layer_transitions", [])}
    selected_ports = {ref for path in fine["paths"].values() for ref in path["ports"]}
    for ref in ("U1.15", "R10.1", "R10.2", "Q2.1", "U1.10", "R12.1", "R12.2", "Q3.1",
                "U2.15", "R18.1", "R18.2", "Q5.1", "U2.10", "R20.1", "R20.2", "Q6.1"):
        selected_ports.add(ref)
    port_map = {}
    for pad in probe["pads"]:
        if pad["ref"] in selected_ports:
            port_map[pad["ref"]] = {"net": pad["net"], "centre_mm": pad["centre_mm"]}
    for item in detailed["primitives"]:
        if item["kind"] == "pad" and item.get("ref") in selected_ports:
            entry = port_map.setdefault(item["ref"], {"net": item["net"], "centre_mm": item["centre"]})
            entry.setdefault("copper_layers", []).append(item["layer"])
            entry["drill_mm"] = item.get("drill_mm")
    for item in copper["items"]:
        if item["kind"] == "pad" and item.get("ref") in selected_ports:
            entry = port_map[item["ref"]]
            entry["copper_layers"] = sorted(set(entry.get("copper_layers", [])) | set(item["layers"]))
    if set(port_map) != selected_ports:
        raise ValueError(f"missing native port annotations: {selected_ports - set(port_map)}")
    (args.outputs / "annotated_ports.json").write_text(json.dumps({"board_sha256": board_sha,
        "ports": dict(sorted(port_map.items()))}, indent=2) + "\n")
    sections = {name: path_scenarios(name, fine["paths"][name], fine["paths"][partner],
                                     z, copper, detailed) for name, partner in PAIRING.items()}
    gates = {}
    for device, (output_net, gate_net, return_key) in GATE_NETS.items():
        tracks = [item for item in copper["items"] if item["kind"] == "track"
                  and item["net"] in (output_net, gate_net)]
        forward_length = sum(math.dist(item["start"], item["end"]) for item in tracks)
        return_route = fine["paths"][return_key]
        if return_route["status"] != "CONNECTED_RASTER_ROUTE":
            gates[device] = {"status": "MISSING_RETURN_ROUTE"}
            continue
        return_horizontal = sum(math.dist(a["xy_mm"], b["xy_mm"])
                                for a, b in zip(return_route["polyline"], return_route["polyline"][1:])
                                if a["layer"] == b["layer"])
        effective_length = max(forward_length, return_horizontal)
        width = statistics.median(item["width"] for item in tracks)
        # Paired-loop scale for the longer member; its unmatched tail and
        # component/body transitions remain a topology uncertainty.
        gap = min(gap_to_adjacent(z, item["layers"][0]) for item in tracks)
        forward_points = []
        for track in tracks:
            a, b = track["start"], track["end"]
            layer_z = z[track["layers"][0]]
            n = max(1, math.ceil(math.dist(a, b) / 0.25))
            forward_points.extend((a[0] + (b[0] - a[0]) * i / n,
                                   a[1] + (b[1] - a[1]) * i / n, layer_z) for i in range(n + 1))
        return_tree = cKDTree(points(return_route, z))
        distances, _ = return_tree.query(forward_points)
        separation = max(statistics.median(distances), width)
        plane_case = MU0 * 1e6 * gap * effective_length / (width + 2 * gap)
        pair_case = MU0 * 1e6 * effective_length / math.pi * math.log(2 * separation / width)
        # The return route's vertical connectors contribute to the loop.
        via_sum = 0.0
        via_terms = []
        for transition in return_route["layer_transitions"]:
            connector = connector_for(transition, return_route["net"], detailed)
            if connector is None:
                raise ValueError(f"unresolved gate return connector: {device}")
            h = abs(z[transition["from_layer"]] - z[transition["to_layer"]])
            term = via_l_nh(h, connector["drill_mm"])
            via_sum += term
            via_terms.append({**transition, **connector, "heuristic_nH": term})
        forward_via_terms = []
        for via in gate_vias["vias"]:
            if via["net"] not in (output_net, gate_net):
                continue
            if not via["through"]:
                raise ValueError(f"unsupported blind gate via: {device}")
            # The authored output track for this net uses F.Cu and In1.Cu;
            # each via supplies that adjacent-layer transition once.
            h = abs(z["F.Cu"] - z["In1.Cu"])
            value = via_l_nh(h, via["drill_mm"])
            via_sum += value
            forward_via_terms.append({**via, "active_transition": "F.Cu-In1.Cu", "heuristic_nH": value})
        gates[device] = {
            "status": "COMPLETE_CONNECTED_RETURN_GEOMETRY_HEURISTIC_SCENARIOS",
            "driver_output_net": output_net, "series_resistor_to_gate_net": gate_net,
            "return_route": return_key,
            "forward_track_length_mm": forward_length,
            "return_connected_length_mm": return_route["length_mm"],
            "effective_pair_length_mm": effective_length,
            "median_route_separation_mm": separation,
            "return_vertical_connectors": via_terms,
            "forward_vertical_connectors": forward_via_terms,
            "reference_plane_case_nH": plane_case + via_sum,
            "separated_pair_case_nH": pair_case + via_sum,
            "scenario_min_nH": min(plane_case, pair_case) + via_sum,
            "scenario_max_nH": max(plane_case, pair_case) + via_sum,
            "ordering_reversed": plane_case > pair_case,
        }
    deck: dict[str, Any] = {}
    loop_totals: dict[str, Any] = {}
    for leg, caps in (("A", ("C38", "C39")), ("B", ("C40", "C41"))):
        for case in ("min", "max"):
            field = f"scenario_{case}_nH"
            branches = [(cap, sections[f"{leg}_bus_{cap}"][field],
                         sections[f"{leg}_shunt_{cap}"][field]) for cap in caps]
            cap, bus, ret = (min(branches, key=lambda row: row[1] + row[2]) if case == "min"
                             else max(branches, key=lambda row: row[1] + row[2]))
            sw = sections[f"{leg}_switch"][field]
            source = sections[f"{leg}_source_shunt"][field]
            # For bulk, use the shorter complete route pair at each corner;
            # internal bulk-cap ESL is still absent and called out below.
            bulk_pairs = [(sections[f"{leg}_bulk_bus"][field] + sections[f"{leg}_bulk_return"][field]),
                          (sections[f"{leg}_bulk_alt_bus"][field] + sections[f"{leg}_bulk_alt_return"][field])]
            bulk_copper = min(bulk_pairs)
            deck.setdefault(leg, {})[case] = {
                "selected_local_capacitor": cap,
                "LD_HS": bus, "LS_HS": sw / 2, "LD_LS": sw / 2,
                "LCS": source, "LS_LS": ret, "LCAP": 5.0 if case == "min" else 20.0,
                "LBULK_copper_only": bulk_copper,
                "LBULK": bulk_copper,
                "LBULK_omits_internal_capacitor_ESL": True,
                "LG_high_side": gates["Q2" if leg == "A" else "Q5"][field],
                "LG_low_side": gates["Q3" if leg == "A" else "Q6"][field],
            }
            deck[leg][case]["LG_single_knob_sweep_nH"] = sorted(
                [deck[leg][case]["LG_high_side"], deck[leg][case]["LG_low_side"]])
            loop_totals.setdefault(leg, {})[case] = bus + sw + source + ret
    result = {
        "schema": "temper.power-stage-120v.a2-inductance-fallback.v2",
        "status": "COMPLETE_CONNECTED_GEOMETRY_HEURISTIC_SCENARIOS_NOT_FIELD_SOLVED",
        "board_sha256": board_sha,
        "source_revision": "44417ae1489fd00e2d652fd3b2c1582b76d17630",
        "inputs_sha256": {name: sha(args.inputs / name) for name in
                          ("copper.json.gz", "vias-and-pads.json", "power_copper_with_holes.json.gz", "gate_vias.json")},
        "stackup_sha256": sha(stack_path),
        "route_tool": "trace_connected_copper.py, hole-aware native KiCad copper, 0.5/0.25 mm raster",
        "frequency_Hz": 10_000_000,
        "frequency_limitation": "Magnetostatic external geometric approximations; conductor internal L, 10 MHz skin/proximity and mutual current division not solved.",
        "fasthenry": {"upstream_url": "https://github.com/ediloren/FastHenry2", "commit": "363e43ed57ad3b9affa11cba5a86624fad0edaa9", "git_tree": "86c4f4c441dcf600fb5f4a19e16dea8f3b764fc8", "induct_c_sha256": "94eb918fd62c4c6e5db022608282ac32ba495952744a8f12c1888d1a967f75e6", "build_attempts": 2, "solver_result": None, "field_mesh_convergence": None},
        "analytic_fixtures": "outputs/analytic-fixtures.json",
        "routes": routes,
        "annotated_ports": "outputs/annotated_ports.json",
        "power_sections": sections,
        "gate_loops": gates,
        "loop_board_copper_scenario_nH": loop_totals,
        "deck_parameters_heuristic_scenario_nH": deck,
        "qualified_deck_parameters_nH": {key: None for key in ("LD_HS", "LS_HS", "LD_LS", "LS_LS", "LCS", "LCAP", "LBULK", "LG")},
        "component_assumptions": {"C38-C41_ESL_nH": [5, 20], "class": "ASSUMED per ROUND-3 A2; exact TDK part model absent", "bulk_cap_internal_ESL_nH": None},
        "deck_mapping": "LS_HS and LD_LS each get half of the same connected switch-node route as bookkeeping, not separate field terms. LCS is source-to-R5.1, LS_LS is R5.4-to-cap return. BUS_P and HV_RET use the same selected local capacitor branch in each scenario. LBULK_copper_only is shorter C5/C6 route pair; internal bulk-cap ESL is unresolved. Each gate has its own LG; sweep both per-device values with the starter deck's one LG knob.",
        "sanity_flags": {"scenario_loop_over_100_nH": [leg for leg, cases in loop_totals.items() if cases["max"] > 100],
                         "meaning": "The runbook says to recheck >100 nH. Separated-pair terms on successive sections can double-count their shared return; these are stress scenarios, not a measured upper limit."},
        "use_for_B1": "Exploratory complete-path sensitivity only; no guaranteed low/high physical bounds or board stress acceptance. LBULK is the routed copper-only proxy with bulk-capacitor internal ESL omitted; declare this omission in every B1 result.",
    }
    (args.outputs / "loop_inductance_fallback_heuristic.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
