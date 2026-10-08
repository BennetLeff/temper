#!/usr/bin/env python3
"""Measure native copper intersections with the unqualified leg crop lines."""
from __future__ import annotations

import gzip
import json
from collections import defaultdict

from audit_geometry import BOARD_SHA, COPPER, HERE, board_drill_voids, digest, primitive_shape
from estimate_tiling import ROIS
from shapely.geometry import LineString
from shapely.ops import unary_union


def main() -> None:
    dataset = json.load(gzip.open(COPPER, "rt"))
    if dataset["board_sha256"] != BOARD_SHA:
        raise ValueError("native copper does not match frozen board")
    shapes = defaultdict(list)
    for primitive in dataset["primitives"]:
        shapes[primitive["net"], primitive["layer"]].append(primitive_shape(primitive))
    bores = board_drill_voids(dataset)
    native = {(net, layer): unary_union(items).difference(bores[layer])
              for (net, layer), items in shapes.items()}
    result = {"status": "CROPS_UNQUALIFIED", "board_sha256": BOARD_SHA,
              "export_sha256": digest(COPPER), "legs": {}}
    for leg, (x0, y0, x1, y1) in ROIS.items():
        cuts = {}
        for net, layer in (("bus_p", "In2.Cu"), ("hv_ret", "In1.Cu"),
                           ("leg_ret", "In1.Cu"), ("sw_a" if leg == "A" else "sw_b", "F.Cu")):
            copper = native.get((net, layer))
            if copper is None:
                continue
            left = LineString(((x0, y0), (x0, y1)))
            right = LineString(((x1, y0), (x1, y1)))
            cuts[f"{net}/{layer}"] = {"left_mm": copper.intersection(left).length,
                                      "right_mm": copper.intersection(right).length}
        result["legs"][leg] = {"roi_xy_mm": [x0, y0, x1, y1], "native_copper_cuts": cuts}
    (HERE / "crop-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
