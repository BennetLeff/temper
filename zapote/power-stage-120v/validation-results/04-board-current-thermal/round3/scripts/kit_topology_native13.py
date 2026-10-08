#!/usr/bin/env python3
"""Check the corrected kit's grid graph against real native-13 copper.

For every (net, layer) in the round-2 copper export, build the kit's grid
(sheet_solver.Net, drills subtracted) and label its connected components.
Every grid component must lie inside a single physical copper component
(polygon of the net on that layer, drills removed). A grid component that
spans two physical components is a false connection across a real gap.

Usage: kit_topology_native13.py <power_copper.json.gz> <out.json> [pitch_mm]
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.sparse.csgraph import connected_components
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[3] / "validation-plan/sim-kit/04-current/sheet_solver.py"
spec = importlib.util.spec_from_file_location("kit_sheet_solver", KIT)
solver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solver)


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    pitch = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25
    with gzip.open(src, "rt") as f:
        ev = json.load(f)
    grouped = defaultdict(list)
    for it in ev["primitives"]:
        grouped[(it["net"], it["layer"])].append(it)
    result = {"board_sha256": ev["board_sha256"], "pitch_mm": pitch, "kit": str(KIT.name), "layers": {}}
    total_bad = 0
    for (net, layer), items in sorted(grouped.items()):
        polys, holes = [], []
        n = solver.Net(pitch_mm=pitch)
        for it in items:
            k = it["kind"]
            if k in ("zone", "pad"):
                polys.append(it["shell"]); holes.extend(it["holes"])
                if k == "pad" and it["drill_mm"][0] > 0:
                    d = it["drill_mm"][0]
                    holes.append(list(Point(it["centre"]).buffer(d / 2, 32).exterior.coords))
            elif k == "track":
                polys.append(list(LineString([it["start"], it["end"]]).buffer(it["width_mm"] / 2, 16).exterior.coords))
            elif k == "via":
                polys.append(list(Point(it["centre"]).buffer(it["diameter_mm"] / 2, 32).exterior.coords))
                holes.append(list(Point(it["centre"]).buffer(it["drill_mm"] / 2, 32).exterior.coords))
        n.add_layer(layer, polys, 70, holes_mm=holes)
        grids, _, G, _ = n._build()
        g = grids[layer]
        phys = g["geom"]
        parts = list(phys.geoms) if hasattr(phys, "geoms") else [phys]
        _, lab = connected_components(G, directed=False)
        ii, jj = np.nonzero(g["ids"] >= 0)
        comp_parts = defaultdict(set)
        for i, j in zip(ii, jj):
            p = Point(g["xs"][i], g["ys"][j])
            pid = next(k_ for k_, part in enumerate(parts) if part.covers(p))
            comp_parts[int(lab[g["ids"][i, j]])].add(pid)
        bad = sum(1 for s in comp_parts.values() if len(s) > 1)
        total_bad += bad
        result["layers"][f"{net}/{layer}"] = {
            "grid_nodes": int(len(ii)), "grid_components": len(comp_parts),
            "physical_components": len(parts), "dropped_edges": g["dropped_edges"],
            "grid_components_spanning_two_physical": bad}
    result["total_spanning"] = total_bad
    Path(out).write_text(json.dumps(result, indent=2) + "\n")
    for k, v in result["layers"].items():
        print(k, v)
    print("TOTAL grid components spanning two physical copper components:", total_bad)
    sys.exit(0 if total_bad == 0 else 1)


if __name__ == "__main__":
    main()
