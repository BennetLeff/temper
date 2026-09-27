#!/usr/bin/env python3
"""Reproduce independent analytic failures of the task-04 starter solver.

This is an instrument audit, not a replacement board solver. Run with the
Miniforge Python. JSON output is retained verbatim in outputs/.
"""

import importlib.util
import json
import math
import sys
import warnings
from pathlib import Path

from scipy.sparse.linalg import MatrixRankWarning
from shapely.geometry import Point


KIT = Path(__file__).resolve().parents[3] / "validation-plan/sim-kit/04-current/sheet_solver.py"
spec = importlib.util.spec_from_file_location("kit_sheet_solver", KIT)
solver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solver)


def four_layer_via():
    net = solver.Net(pitch_mm=1)
    rectangle = [[(0, 0), (2, 0), (2, 2), (0, 2)]]
    layers = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    for layer in layers:
        net.add_layer(layer, rectangle, 70 if layer in (layers[0], layers[-1]) else 61)
    net.add_via((0.5, 0.5), 0.8, 18, layers, length_mm=1.6)
    got = net.solve([("F.Cu", 0.5, 0.5, 1)], [("B.Cu", 0.5, 0.5)])
    ri = 0.8e-3 / 2
    area = math.pi * ((ri + 18e-6) ** 2 - ri**2)
    expected = solver.RHO_CU * 1.6e-3 / area
    return {"kit_ohm": got["r_ohm"], "analytic_ohm": expected,
            "ratio": got["r_ohm"] / expected, "current_edges_a": [x["amps"] for x in got["via_currents"]]}


def unequal_sources():
    net = solver.Net(pitch_mm=0.5)
    net.add_layer("F.Cu", [[(0, 0), (20, 0), (20, 1), (0, 1)]], 70)
    sources = [("F.Cu", 0.25, 0.25, 1), ("F.Cu", 10.25, 0.25, 1)]
    got = net.solve(sources, [("F.Cu", 19.75, 0.25), ("F.Cu", 19.75, 0.75)])
    index, _ = net._index()
    source_volts = [float(got["v"][net._cell(index, layer, x, y)]) for layer, x, y, _ in sources]
    energy_equiv_r = sum(v for v in source_volts) / 4
    return {"kit_ohm": got["r_ohm"], "power_equivalent_ohm": energy_equiv_r,
            "ratio": got["r_ohm"] / energy_equiv_r, "source_volts": source_volts}


def outside_copper_snap():
    net = solver.Net(pitch_mm=0.5)
    net.add_layer("F.Cu", [[(0, 0), (1, 0), (1, 1), (0, 1)]], 70)
    index, _ = net._index()
    point = (1.1, 0.25)
    return {"point_mm": point, "covered_by_polygon": bool(net.layers["F.Cu"]["geom"].covers(Point(*point))),
            "accepted_node": int(net._cell(index, "F.Cu", *point))}


def disconnected_region():
    net = solver.Net(pitch_mm=0.5)
    net.add_layer("F.Cu", [[(0, 0), (1, 0), (1, 1), (0, 1)],
                           [(3, 0), (4, 0), (4, 1), (3, 1)]], 70)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", MatrixRankWarning)
        got = net.solve([("F.Cu", 0.25, 0.25, 1)], [("F.Cu", 0.75, 0.25)])
    return {"resistance_ohm": got["r_ohm"] if math.isfinite(got["r_ohm"]) else "NaN",
            "matrix_rank_warnings": [str(w.message) for w in captured if issubclass(w.category, MatrixRankWarning)]}


if __name__ == "__main__":
    via = four_layer_via()
    sources = unequal_sources()
    snap = outside_copper_snap()
    disconnected = disconnected_region()
    reproduced = (abs(via["ratio"] - 3) < 1e-9 and sources["ratio"] > 1.2
                  and not snap["covered_by_polygon"] and snap["accepted_node"] >= 0
                  and disconnected["resistance_ohm"] == "NaN"
                  and bool(disconnected["matrix_rank_warnings"]))
    print(json.dumps({"kit_path": str(KIT), "four_layer_via": via,
                      "unequal_sources": sources, "outside_copper_snap": snap,
                      "disconnected_region": disconnected,
                      "audit_reproduced": reproduced}, indent=2, allow_nan=False))
    sys.exit(0 if reproduced else 1)
