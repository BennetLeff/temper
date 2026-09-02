#!/usr/bin/env python3
"""Bounded characterization of zone-emission's GEOS mitre buffer.

This is intentionally a measurement tool, not a production implementation.
It compares Shapely/GEOS ``buffer(join_style=2)`` with the independent
unlimited-mitre offset construction that was proposed for a Rust port. The
production inputs are replayed through the live pad collectors, clustering,
exemptions, dedupe, and ``cluster=False`` power-island call shape. Crafted
and seeded random cases exercise the bevel-at-mitre-limit and LineString
(stadium) boundaries.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

import shapely
from shapely import geos_version_string
from shapely.geometry import MultiPoint, Polygon

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "pcb" / "temper.kicad_pcb"
EXPECTED_SHAPELY = "2.1.2"
EXPECTED_GEOS = "3.13.1"
EXPECTED_BOARD_SHA256 = "00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9"
EXPECTED_ZONE_NETS = {
    "ac_n", "ac_l", "+170V_BUS", "PWR_RTN", "hb-gnd", "SW_NODE",
    "tank.c_tank1-p2", "DC_BUS_RTN", "w1_1", "w1_2", "power_in.ntc-no",
    "tank-out",
}
EXPECTED_POWER_NETS = {"+3V3", "vcc", "+15V", "V_BUS_SENSE"}


def _line_intersection(a, b, c, d):
    x1, y1 = a
    x2, y2 = b
    x3, y3 = c
    x4, y4 = d
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if den == 0.0:
        return None
    p = x1 * y2 - y1 * x2
    q = x3 * y4 - y3 * x4
    return (
        (p * (x3 - x4) - (x1 - x2) * q) / den,
        (p * (y3 - y4) - (y1 - y2) * q) / den,
    )


def _unlimited_mitre(ring, margin):
    """Independent outward-normal offset, without GEOS's mitre limit."""
    vertices = list(ring[:-1])
    result = []
    for i, vertex in enumerate(vertices):
        previous = vertices[i - 1]
        following = vertices[(i + 1) % len(vertices)]

        def offset(a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            return (
                (a[0] - margin * dy / length, a[1] + margin * dx / length),
                (b[0] - margin * dy / length, b[1] + margin * dx / length),
            )

        incoming = offset(previous, vertex)
        outgoing = offset(vertex, following)
        direction_in = (vertex[0] - previous[0], vertex[1] - previous[1])
        direction_out = (following[0] - vertex[0], following[1] - vertex[1])
        intersection = _line_intersection(
            incoming[1],
            (incoming[1][0] + direction_in[0], incoming[1][1] + direction_in[1]),
            outgoing[0],
            (outgoing[0][0] + direction_out[0], outgoing[0][1] + direction_out[1]),
        )
        result.append(intersection or incoming[1])
    return result


def _formatted(points):
    return tuple((f"{x:.4f}", f"{y:.4f}") for x, y in points)


def _square_fallback(point, margin):
    x, y = point
    h = margin if margin > 0 else 0.1
    return [(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)]


def _signed_area(ring):
    return sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(ring[:-1], ring[1:], strict=True)
    ) / 2.0


def _compare(points, margin):
    hull = MultiPoint(points).convex_hull
    if hull.geom_type == "Point" and len(points) == 1:
        # This is zone_emission.py's production fallback, not GEOS Point.buffer.
        return {
            "kind": "Point",
            "geos_vertices": None,
            "analytic_vertices": None,
            "compared": False,
            "formatted_equal": None,
            "symmetric_difference_mm2": None,
            "production_vertices": len(_square_fallback(points[0], margin)),
        }
    if not isinstance(hull, Polygon):
        buffered = hull.buffer(margin, join_style=2)
        geos_coords = list(buffered.exterior.coords)
        return {
            "kind": hull.geom_type,
            "geos_vertices": len(geos_coords) - 1,
            "analytic_vertices": None,
            "compared": False,
            "formatted_equal": None,
            "symmetric_difference_mm2": None,
        }
    buffered = hull.buffer(margin, join_style=2)
    hull_coords = list(hull.exterior.coords)
    if _signed_area(hull_coords) >= 0.0:
        raise RuntimeError("GEOS convex hull winding changed from clockwise")
    buffered_coords = list(buffered.exterior.coords)
    analytic = _unlimited_mitre(hull_coords, margin)
    analytic_polygon = Polygon(analytic)
    # GEOS overlay can report a large false-looking difference for polygons
    # whose coordinates are already equal at the measured precision. Preserve
    # raw-region sensitivity for real differences, but guard this numerical
    # equality before asking GEOS for a symmetric difference.
    if buffered.equals_exact(analytic_polygon, 1.0e-12):
        symmetric_difference = 0.0
    else:
        symmetric_difference = buffered.symmetric_difference(analytic_polygon).area
    return {
        "kind": "Polygon",
        "geos_vertices": len(buffered_coords) - 1,
        "analytic_vertices": len(analytic),
        "compared": True,
        "formatted_equal": _formatted(buffered_coords[:-1]) == _formatted(analytic),
        "symmetric_difference_mm2": symmetric_difference,
    }


def main():
    import sys

    sys.path.insert(0, str(ROOT / "packages" / "temper-placer" / "src"))
    import temper_orchestration as _to

    if shapely.__version__ != EXPECTED_SHAPELY or geos_version_string != EXPECTED_GEOS:
        raise RuntimeError(
            "unsupported Shapely/GEOS oracle: "
            f"got {shapely.__version__} / GEOS {geos_version_string}, "
            f"expected {EXPECTED_SHAPELY} / GEOS {EXPECTED_GEOS}"
        )
    board_sha256 = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    if board_sha256 != EXPECTED_BOARD_SHA256:
        raise RuntimeError(
            f"board content changed: got {board_sha256}, expected {EXPECTED_BOARD_SHA256}"
        )

    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6._ground_plane import _dedupe_positions
    from temper_placer.router_v6._power_islands import POWER_ISLAND_NETS
    from temper_placer.router_v6._zone_pour_stitch import (
        _CONTINUITY_EXEMPT_CLASSES,
        _CONTINUITY_EXEMPT_NETS,
        _zone_layers_for_net,
        _zone_params_for_net,
    )
    from temper_placer.router_v6.pad_connectivity_audit import _pads_by_net
    from temper_placer.router_v6.zone_emission import _cluster_positions

    pcb = parse_kicad_pcb_v6(BOARD)
    pad_positions = dict(_to.run_collect_pad_positions(pcb))
    pads_by_net = _pads_by_net(pcb)
    production = {"zone_pour_stitch": {}, "power_islands": {}}
    for name in sorted(pad_positions):
        positions = pad_positions[name]
        if not positions or not _zone_layers_for_net(name):
            continue
        netclass = TEMPER_NET_ASSIGNMENTS.get(name, "")
        exempt = netclass in _CONTINUITY_EXEMPT_CLASSES or name in _CONTINUITY_EXEMPT_NETS
        groups = [positions] if exempt else _cluster_positions(positions)
        margin = _zone_params_for_net(name)[0]
        for index, group in enumerate(groups):
            shape = "single-exempt" if exempt else "clustered"
            key = f"{name}:group-{index}:{shape}"
            production["zone_pour_stitch"][key] = _compare(group, margin)

    for name in sorted(POWER_ISLAND_NETS):
        pads = pads_by_net.get(name, [])
        if not pads:
            continue
        positions = _dedupe_positions([pad.position for pad in pads])
        production["power_islands"][f"{name}:single:cluster-false"] = _compare(positions, 0.5)

    zone_keys = production["zone_pour_stitch"]
    zone_nets = {key.split(":", 1)[0] for key in zone_keys}
    power_keys = production["power_islands"]
    power_nets = {key.split(":", 1)[0] for key in power_keys}
    if len(zone_keys) != 35 or zone_nets != EXPECTED_ZONE_NETS:
        raise RuntimeError(
            f"production zone corpus drifted: {len(zone_keys)} calls / {sorted(zone_nets)}"
        )
    if len(power_keys) != 4 or power_nets != EXPECTED_POWER_NETS:
        raise RuntimeError(
            f"production power corpus drifted: {len(power_keys)} calls / {sorted(power_nets)}"
        )

    crafted = {
        "acute_triangle": _compare([(0.0, 0.0), (10.0, 0.0), (0.1, 0.01)], 1.0),
        "obtuse_triangle": _compare([(0.0, 0.0), (10.0, 0.0), (5.0, 1.0)], 1.0),
        "rectangle": _compare([(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)], 1.0),
        "two_point_stadium": _compare([(0.0, 0.0), (10.0, 0.0)], 2.0),
        "collinear_stadium": _compare([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)], 2.0),
    }
    rng = random.Random(20260901)
    random_case_count = 0
    random_compared_count = 0
    random_not_compared_count = 0
    random_formatted_mismatches = 0
    random_max_symmetric_difference_mm2 = 0.0
    for _ in range(1000):
        points = [
            (rng.uniform(-100.0, 100.0), rng.uniform(-100.0, 100.0))
            for _ in range(rng.randint(3, 30))
        ]
        case = _compare(points, 10 ** rng.uniform(-2.0, 1.0))
        random_case_count += 1
        if case["compared"]:
            random_compared_count += 1
            random_formatted_mismatches += not case["formatted_equal"]
            random_max_symmetric_difference_mm2 = max(
                random_max_symmetric_difference_mm2, case["symmetric_difference_mm2"]
            )
        else:
            random_not_compared_count += 1
    if random_case_count != 1000 or random_compared_count != 1000:
        raise RuntimeError(
            "random corpus drifted: "
            f"{random_case_count} cases / {random_compared_count} polygon comparisons"
        )
    result = {
        "board": str(BOARD.relative_to(ROOT)),
        "board_sha256": board_sha256,
        "shapely_geos": f"{shapely.__version__} / GEOS {geos_version_string}",
        "production_sets": production,
        "crafted": crafted,
        "random_seed": 20260901,
        "random_cases": random_case_count,
        "random_compared": random_compared_count,
        "random_not_compared": random_not_compared_count,
        "random_formatted_mismatches": random_formatted_mismatches,
        "random_max_symmetric_difference_mm2": random_max_symmetric_difference_mm2,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
