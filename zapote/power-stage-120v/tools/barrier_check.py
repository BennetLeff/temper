#!/usr/bin/env python3
"""Plan-view barrier check across ALL copper-layer pairs.

KiCad's clearance and creepage rules compare items on the same layer only.
With inner planes, HOT copper on one layer could sit under SELV copper on
another, separated only by laminate. The provisional basis keeps every HOT
item at least 8.0 mm (plan view) from every SELV or PE item on any layer,
except within one barrier component's own pads, which the package rating
and the same-layer DRC already cover.

    python3 tools/barrier_check.py copper.json [--floor 8.0]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import write_rules  # noqa: E402


def geometry(item):
    if item["kind"] == "pad":
        return box(*item["box"])
    if item["kind"] == "via":
        return Point(*item["centre"]).buffer(item["radius"])
    if item["kind"] == "track":
        return LineString([item["start"], item["end"]]).buffer(item["width"] / 2)
    return Polygon(item["polygon"]).buffer(0)


def main() -> None:
    items = json.load(open(sys.argv[1]))
    floor = float(sys.argv[sys.argv.index("--floor") + 1]) if "--floor" in sys.argv else 8.0
    selv = write_rules.audit_selv_nets(write_rules.UNIT / "audit.rs") | write_rules.SELV_NC
    hot = set().union(*write_rules.HOT_GROUPS.values())
    barrier = [(i, geometry(i)) for i in items if i["net"] in selv or i["net"] in write_rules.PE]
    hot_items = [(i, geometry(i)) for i in items if i["net"] in hot]
    tree = STRtree([g for _i, g in hot_items])
    worst = []
    for item, geom in barrier:
        for idx in tree.query(geom.buffer(floor)):
            other, ogeom = hot_items[idx]
            if item["kind"] == "pad" and other["kind"] == "pad" and \
                    item["ref"].split(".")[0] == other["ref"].split(".")[0]:
                continue  # one barrier component's own pads
            gap = geom.distance(ogeom)
            if gap < floor:
                same = bool(set(item["layers"]) & set(other["layers"]))
                worst.append((round(gap, 2), item.get("ref", item["kind"]), item["net"], item["layers"],
                              other.get("ref", other["kind"]), other["net"], other["layers"], same))
    worst.sort()
    print(json.dumps({"floor_mm": floor, "violations": len(worst),
                      "cross_layer": sum(1 for w in worst if not w[7]),
                      "worst": worst[:25]}, indent=1))
    sys.exit(1 if worst else 0)


if __name__ == "__main__":
    main()
