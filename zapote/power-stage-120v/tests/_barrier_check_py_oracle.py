#!/usr/bin/env python3
"""Pinned pre-Rust Shapely oracle for differential tests only.

Copied from b230bb5fd's barrier_check.py. It uses GEOS polygonal circle and
capsule approximations, so Rust's exact distances may flag an extra borderline
case; the oracle must never justify a Rust undercount.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

from shapely import make_valid
from shapely.geometry import LineString, Point, Polygon, box
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import write_rules  # noqa: E402

SCHEMA = "temper.power-stage-120v.copper-evidence.v1"
KINDS = {"pad", "track", "via", "zone"}


def finite_numbers(value: object) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(value)
    return isinstance(value, (list, tuple)) and bool(value) and all(
        finite_numbers(item) for item in value
    )


def geometry(item: dict):
    kind = item["kind"]
    if kind == "pad":
        coords = item["box"]
        if len(coords) != 4 or not finite_numbers(coords) or coords[0] >= coords[2] or coords[1] >= coords[3]:
            raise ValueError(f"invalid pad bounds: {item.get('ref')}")
        result = box(*coords)
    elif kind == "via":
        if len(item["centre"]) != 2 or not finite_numbers(item["centre"]) or not finite_numbers(item["radius"]) or item["radius"] <= 0:
            raise ValueError("invalid via geometry")
        result = Point(*item["centre"]).buffer(item["radius"])
    elif kind == "track":
        if any(len(item[key]) != 2 or not finite_numbers(item[key]) for key in ("start", "end")) or not finite_numbers(item["width"]) or item["width"] <= 0:
            raise ValueError("invalid track geometry")
        result = LineString([item["start"], item["end"]]).buffer(item["width"] / 2)
    elif kind == "zone":
        pts = item["polygon"]
        if len(pts) < 3 or any(len(pt) != 2 or not finite_numbers(pt) for pt in pts):
            raise ValueError("invalid zone outline")
        result = Polygon(pts)
        if not result.is_valid:
            # KiCad can emit touching contours as one outline. Repair them
            # without dropping islands (buffer(0) can discard a lobe).
            result = make_valid(result)
    else:
        raise ValueError(f"unsupported copper kind: {kind}")
    if result.is_empty or not result.is_valid:
        raise ValueError(f"invalid copper geometry: {kind}")
    return result


def checked_items(evidence: dict) -> list[dict]:
    if evidence.get("schema") != SCHEMA:
        raise ValueError("unsupported or legacy copper evidence schema")
    board_path = Path(evidence["board_path"])
    if not board_path.is_file() or hashlib.sha256(board_path.read_bytes()).hexdigest() != evidence["board_sha256"]:
        raise ValueError("copper evidence is stale or its board is missing")
    items = evidence["items"]
    if not isinstance(items, list):
        raise ValueError("copper items must be a list")
    digest = hashlib.sha256(json.dumps(items, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()
    if digest != evidence["items_sha256"]:
        raise ValueError("copper items differ from the evidence digest")
    layers = evidence["copper_layers"]
    if not isinstance(layers, list) or len(set(layers)) != len(layers) or not layers:
        raise ValueError("invalid copper-layer census")
    counts = Counter(item.get("kind") for item in items)
    if set(counts) - KINDS:
        raise ValueError(f"unsupported copper item kinds: {set(counts) - KINDS}")
    census = evidence["census"]
    expected = {"pads": counts["pad"], "tracks": counts["track"],
                "vias": counts["via"], "filled_zone_polygons": counts["zone"],
                "items": len(items)}
    if any(census.get(key) != value for key, value in expected.items()):
        raise ValueError("copper item census disagrees with exported items")
    if census.get("zones", 0) > counts["zone"] or census.get("zones", 0) < 0:
        raise ValueError("filled zone census disagrees with exported items")
    if census.get("footprints", 0) <= 0 or counts["pad"] <= 0:
        raise ValueError("missing footprint/pad census")
    selv = write_rules.audit_selv_nets(write_rules.UNIT / "audit.rs") | write_rules.SELV_NC
    hot = set().union(*write_rules.HOT_GROUPS.values())
    known = selv | hot | write_rules.PE
    for item in items:
        if not item.get("net") or item["net"] not in known:
            raise ValueError(f"unclassified copper net: {item.get('net')}")
        if not isinstance(item.get("layers"), list) or not item["layers"] or set(item["layers"]) - set(layers):
            raise ValueError(f"invalid layers on copper item: {item.get('kind')}")
        geometry(item)
    return items


def check(evidence: dict, floor: float) -> dict:
    if not math.isfinite(floor) or floor <= 0:
        raise ValueError("barrier floor must be positive and finite")
    items = checked_items(evidence)
    selv = write_rules.audit_selv_nets(write_rules.UNIT / "audit.rs") | write_rules.SELV_NC
    hot = set().union(*write_rules.HOT_GROUPS.values())
    barrier = [(i, geometry(i)) for i in items if i["net"] in selv or i["net"] in write_rules.PE]
    hot_items = [(i, geometry(i)) for i in items if i["net"] in hot]
    if not barrier or not hot_items:
        raise ValueError("missing barrier or HOT copper")
    tree = STRtree([g for _i, g in hot_items])
    worst = []
    for item, geom in barrier:
        for idx in tree.query(geom.buffer(floor)):
            other, ogeom = hot_items[idx]
            if item["kind"] == "pad" and other["kind"] == "pad" and \
                    item["ref"].split(".")[0] == other["ref"].split(".")[0]:
                continue  # one barrier component's own pads; KiCad DRC checks package spacing
            gap = geom.distance(ogeom)
            if gap < floor:
                same = bool(set(item["layers"]) & set(other["layers"]))
                worst.append((round(gap, 2), item.get("ref", item["kind"]), item["net"], item["layers"],
                              other.get("ref", other["kind"]), other["net"], other["layers"], same))
    worst.sort()
    return {"floor_mm": floor, "board_sha256": evidence["board_sha256"],
            "census": evidence["census"], "violations": len(worst),
            "cross_layer": sum(1 for w in worst if not w[7]), "worst": worst[:25]}


def main() -> None:
    if len(sys.argv) not in (2, 4) or (len(sys.argv) == 4 and sys.argv[2] != "--floor"):
        raise SystemExit("usage: barrier_check.py copper.json [--floor millimetres]")
    floor = float(sys.argv[3]) if len(sys.argv) == 4 else 8.0
    result = check(json.loads(Path(sys.argv[1]).read_text()), floor)
    print(json.dumps(result, indent=1))
    raise SystemExit(1 if result["violations"] else 0)


if __name__ == "__main__":
    main()
