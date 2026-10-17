#!/usr/bin/env python3
"""Extract supported layout terms without assigning missing circuit inductances.

Usage: Miniforge Python loop_inductance.py <copper.json[.gz]> <vias-and-pads.json>
       <stackup.json> <output.json>

The plane-pair formula is used only where both filled zones overlap along a
sampled path. The output reports uncovered intervals, so a partial estimate
cannot be mistaken for the entire commutation-loop inductance.
"""

import hashlib
import gzip
import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

MU0 = 4 * math.pi * 1e-7
POWER_PATHS = {
    "A_C38_bus_to_Q2": ("C38.1", "Q2.2", "bus_p", "hv_ret"),
    "A_C39_bus_to_Q2": ("C39.1", "Q2.2", "bus_p", "hv_ret"),
    "A_Q3_source_to_R5": ("Q3.3", "R5.1", "leg_ret", "bus_p"),
    "A_R5_to_C38_return": ("R5.4", "C38.2", "hv_ret", "bus_p"),
    "A_R5_to_C39_return": ("R5.4", "C39.2", "hv_ret", "bus_p"),
    "B_C40_bus_to_Q5": ("C40.1", "Q5.2", "bus_p", "hv_ret"),
    "B_C41_bus_to_Q5": ("C41.1", "Q5.2", "bus_p", "hv_ret"),
    "B_Q6_source_to_R5": ("Q6.3", "R5.1", "leg_ret", "bus_p"),
    "B_R5_to_C40_return": ("R5.4", "C40.2", "hv_ret", "bus_p"),
    "B_R5_to_C41_return": ("R5.4", "C41.2", "hv_ret", "bus_p"),
}
GATES = {
    "Q2": ("U1.15", "R10.1", "R10.2", "Q2.1", "U1.14", "Q2.3", "leg_a-out_h", "leg_a-gate_h"),
    "Q3": ("U1.10", "R12.1", "R12.2", "Q3.1", "U1.9", "Q3.3", "leg_a-out_l", "leg_a-gate_l"),
    "Q5": ("U2.15", "R18.1", "R18.2", "Q5.1", "U2.14", "Q5.3", "leg_b-out_h", "leg_b-gate_h"),
    "Q6": ("U2.10", "R20.1", "R20.2", "Q6.1", "U2.9", "Q6.3", "leg_b-out_l", "leg_b-gate_l"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as stream:
            return json.load(stream)
    return json.loads(path.read_text())


def plane_width(poly, p, normal):
    if not poly.covers(Point(p)):
        return 0.0
    line = LineString([(p[0] - 100 * normal[0], p[1] - 100 * normal[1]),
                       (p[0] + 100 * normal[0], p[1] + 100 * normal[1])])
    cut = poly.intersection(line)
    # Only the connected cross-section that contains the path point counts.
    parts = [cut] if cut.geom_type == "LineString" else list(getattr(cut, "geoms", []))
    return max((part.length for part in parts if part.distance(Point(p)) < 1e-6), default=0.0)


def section(start, end, overlap, dielectric_mm):
    length = math.dist(start, end)
    unit = ((end[0] - start[0]) / length, (end[1] - start[1]) / length)
    normal = (-unit[1], unit[0])
    count = math.ceil(length / 0.5)
    step = length / count
    widths = []
    for i in range(count):
        p = (start[0] + (i + 0.5) * step * unit[0],
             start[1] + (i + 0.5) * step * unit[1])
        widths.append(plane_width(overlap, p, normal))
    covered = [w for w in widths if w > 0]
    # nH: mu0 * (d_mm * 1e-3) * (step_mm * 1e-3) / (w_mm * 1e-3) * 1e9
    known_nh = sum(MU0 * 1e6 * dielectric_mm * step / w for w in covered)
    return {"pad_centre_distance_mm": length, "sample_step_mm": step,
            "covered_length_mm": len(covered) * step,
            "uncovered_length_mm": (count - len(covered)) * step,
            "minimum_covered_width_mm": min(covered) if covered else None,
            "covered_inductance_nH": known_nh if covered else None,
            "total_inductance_nH": known_nh if len(covered) == count else None,
            "source": "native-13 filled zones and stackup.json; L=mu0*d*length/overlap_width",
            "limitation": "Centreline approximation; filled polygon holes are not subtracted. Uncovered length is unmodelled, not zero inductance."}


def main():
    copper_path, probe_path, stackup_path, output_path = map(Path, sys.argv[1:5])
    copper, probe, stack = [load_json(p) for p in (copper_path, probe_path, stackup_path)]
    assert copper["board_sha256"] == probe["board_sha256"]
    pads = {p["ref"]: p["centre_mm"] for p in probe["pads"]}
    dielectric_mm = next(layer["thickness_mm"] for layer in stack["layers"] if layer["name"] == "dielectric 2")
    zones = {}
    for net, layer in [("bus_p", "In2.Cu"), ("hv_ret", "In1.Cu"), ("leg_ret", "In1.Cu")]:
        shapes = []
        for item in copper["items"]:
            if item["kind"] == "zone" and item["net"] == net and layer in item["layers"]:
                shape = Polygon(item["polygon"])
                shapes.append(shape if shape.is_valid else shape.buffer(0))
        zones[net] = unary_union(shapes)
    pairs = {"bus_p:hv_ret": zones["bus_p"].intersection(zones["hv_ret"]),
             "bus_p:leg_ret": zones["bus_p"].intersection(zones["leg_ret"])}
    paths = {}
    for name, (start, end, net1, net2) in POWER_PATHS.items():
        return_net = net2 if net1 == "bus_p" else net1
        paths[name] = {"from": start, "to": end, "conductor_nets": [net1, net2],
                       **section(pads[start], pads[end], pairs["bus_p:" + return_net], dielectric_mm)}
    gates = {}
    for ref, (driver, rin, rout, gate, ret, source, output_net, gate_net) in GATES.items():
        output_tracks = [x for x in copper["items"] if x["kind"] == "track" and x["net"] == output_net]
        gate_tracks = [x for x in copper["items"] if x["kind"] == "track" and x["net"] == gate_net]
        gates[ref] = {"driver": driver, "series_resistor": [rin, rout], "gate": gate,
                      "driver_return": ret, "source": source,
                      "geometry_source": "native-13 authored tracks and native pad positions in copper.json.gz/vias-and-pads.json",
                      "driver_to_resistor_track_length_mm": sum(math.dist(t["start"], t["end"]) for t in output_tracks),
                      "resistor_to_gate_net_track_length_mm": sum(math.dist(t["start"], t["end"]) for t in gate_tracks),
                      "driver_to_resistor_track_widths_mm": sorted(set(t["width"] for t in output_tracks)),
                      "return_chord_mm": math.dist(pads[ret], pads[source]),
                      "LG_nH": None,
                      "reason_LG_unresolved": "A source-return conductor paired continuously with each gate-track section has not been established; total gate-net tracks also include hold-off branches."}
    power_vias = [v for v in probe["vias"] if v["drill_mm"] == 0.8]
    # Through-via formula over only the F.Cu-to-In1 transition. This is a
    # candidate local term; current division among bank vias is unresolved.
    h = next(layer["thickness_mm"] for layer in stack["layers"] if layer["name"] == "dielectric 1")
    single_via_nh = MU0 * 1e6 * h / (2 * math.pi) * (math.log(4 * h / 0.8) + 1)
    output = {
        "status": "PARTIAL_BLOCKED", "evidence_class": "heuristic analytic estimates of sampled geometry only",
        "board_sha256": copper["board_sha256"],
        "input_sha256": {p.name: digest(p) for p in (copper_path, probe_path, stackup_path)},
        "plane_pair_paths": paths, "gate_paths": gates,
        "via_terms": {"formula": "mu0*h/(2*pi)*(ln(4*h/drill)+1)",
                      "source": "native-13 via drills/positions in vias-and-pads.json; F.Cu-to-In1 dielectric from stackup.json; formula from SIMULATION-RUNBOOK.md section 3",
                      "transition": "F.Cu to In1.Cu", "h_mm": h, "drill_mm": 0.8,
                      "single_via_nH": single_via_nh,
                      "power_via_centres": [{"net": v["net"], "centre_mm": v["centre_mm"]} for v in power_vias],
                      "parallel_bank_equivalent_nH": None,
                      "reason": "Current distribution across each bank has not been validated."},
        "deck_parameters_nH": {k: None for k in ("LD_HS", "LS_HS", "LD_LS", "LS_LS", "LCAP", "LCS", "LG", "LBULK")},
        "leg_total_nH": {leg: {corner: None for corner in ("low", "nominal", "high")} for leg in ("A", "B")},
        "missing_inputs": ["B32652A0104K000 capacitor ESL or measured self-resonance; TDK June 2026 series datasheet has no numeric value",
                           "continuous paired-current geometry and current division needed to map plane/via terms to LD_HS, LS_HS, LD_LS, LS_LS and LCS",
                           "source-return path geometry needed to assign LG"],
        "note": "The Infineon L1 subcircuit already contains package inductance; it must not be added to these board parameters. No placeholder defaults are substituted."}
    output_path.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
