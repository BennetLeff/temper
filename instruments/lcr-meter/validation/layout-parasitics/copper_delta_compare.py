"""Shapely half of copper_delta.sh: analog items identical?  GND-fill change per layer and its distance to analog copper."""

import json
import sys

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

d = json.load(open(sys.argv[1]))
ref, new = d["ref"], d["new"]
analog = unary_union([LineString(s) for s in new["analog_segments"]])
out = {
    "reference_rev": sys.argv[2],
    "analog_items": len(new["items"]),
    "analog_items_identical": ref["items"] == new["items"],
    "gnd_fill_change": {},
}
for layer in sorted(set(ref["fills"]) | set(new["fills"])):
    def union(side):
        return unary_union([Polygon(p["o"], p["h"]).buffer(0) for p in side["fills"].get(layer, [])])
    x = union(ref).symmetric_difference(union(new)).buffer(-0.01).buffer(0.01)
    out["gnd_fill_change"][layer] = (
        {"area_mm2": 0.0}
        if x.is_empty
        else {"area_mm2": round(x.area, 2), "nearest_analog_copper_mm": round(x.distance(analog), 2)}
    )
print(json.dumps(out, indent=1))
