"""
Router V6 Stage 5.6: Verify Creepage / Clearance

Validates clearance distances for high-voltage isolation.

.. note::

   This module currently measures **straight-line clearance**
   (air-gap distance) between conductor segments — not true
   surface creepage.  True creepage requires a pathfinding
   approach along the PCB surface that routes around isolation
   slots, board edges, and other obstacles.

   **Isolation slots are not modeled.**

Part of temper-ytm8 (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6._check_report_base import BaseCheckReport


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CreepageViolation:
    """A clearance / creepage distance violation."""

    hv_net: str
    lv_net: str
    location: tuple[float, float]  # Closest approach point (midpoint)
    actual_distance: float         # Actual clearance distance (mm)
    required_distance: float       # Required minimum distance (mm)

    @property
    def deficiency(self) -> float:
        """How much the distance is under requirement."""
        return self.required_distance - self.actual_distance


@dataclass
class CreepageReport(BaseCheckReport):
    """Report of clearance / creepage distance violations."""

    violations: list[CreepageViolation]
    total_checks: int


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def verify_creepage(
    routing_results: RoutingResults,
    voltage_ratings: dict[str, float] | None = None,
    default_creepage: float | None = None,
) -> CreepageReport:
    """
    Verify clearance distances for high-voltage isolation.

    .. warning::

       This measures **straight-line (air-gap) clearance**, not true
       surface creepage.  True creepage requires a pathfinding
       approach along the PCB surface.  Isolation slots are **not**
       modelled.

    Args:
        routing_results: Compiled routing results from Stage 4.9.
        voltage_ratings: Optional dict mapping net name to working
            voltage (V).  Defaults to 230 V for unrecognised nets.
        default_creepage: When set, overrides the voltage-table
            lookup and uses this single value (mm) as the required
            distance for **every** HV net.

    Returns:
        CreepageReport with all violations.

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = verify_creepage(results)
        >>> report.violation_count >= 0
        True
    """
    violations: list[CreepageViolation] = []
    total_checks = 0

    if voltage_ratings is None:
        voltage_ratings = {}

    if default_creepage is not None and (
        math.isnan(default_creepage) or not math.isfinite(default_creepage)
    ):
        raise ValueError(
            f"default_creepage must be a finite number, got {default_creepage!r}"
        )

    # Identify every HV net
    hv_nets = [net for net in routing_results.compiled_routes
               if _is_high_voltage_net(net)]

    for hv_net in hv_nets:
        hv_route = routing_results.compiled_routes[hv_net]

        for other_net, other_route in routing_results.compiled_routes.items():
            if other_net == hv_net:
                continue

            total_checks += 1

            # ---- required distance -----------------------------------
            if default_creepage is not None:
                required_distance = default_creepage
            else:
                hv_voltage = voltage_ratings.get(hv_net, 230.0)
                required_distance = _calculate_required_creepage(hv_voltage)

            # ---- find *all* violating segment pairs ------------------
            pair_violations = _find_clearance_violations(
                hv_route, other_route,
                required_distance,
                hv_net, other_net,
            )
            violations.extend(pair_violations)

    return CreepageReport(violations=violations, total_checks=total_checks)


# ---------------------------------------------------------------------------
# HV net detection
# ---------------------------------------------------------------------------

def _is_high_voltage_net(net_name: str) -> bool:
    """
    Check whether *net_name* designates a high-voltage net.

    Matches a broad set of keywords commonly used in power-electronics
    schematics.  ``AC`` and ``HV`` are matched on word boundaries so
    that ``AC1``, ``HV_BUS``, ``_AC`` are recognised but ``TRACE`` is
    not.

    Args:
        net_name: Net name from the schematic / layout.

    Returns:
        ``True`` if the net is classified as high-voltage.
    """
    name_upper = net_name.upper()

    # Broad-match keywords (substring match is safe for these)
    broad_keywords = [
        'HIGH_VOLTAGE', 'MAINS',
        'LINE', 'NEUTRAL', 'PRIMARY', 'HOT',
        'L1', 'L2', 'L3', 'PHASE',
        'VBUS', 'B+',
    ]
    if any(kw in name_upper for kw in broad_keywords):
        return True

    # AC / HV with optional trailing underscore or digit
    # (?:^|_)  – start-of-string or underscore before
    # (?:$|[\d_]) – end-of-string, digit, or underscore after
    if re.search(r'(?:^|_)AC(?:$|[\d_])', name_upper):
        return True
    if re.search(r'(?:^|_)HV(?:$|[\d_])', name_upper):
        return True

    return False


# ---------------------------------------------------------------------------
# Clearance-distance helpers
# ---------------------------------------------------------------------------

def _extract_segments(
    route,
) -> list[tuple[float, float, float, float, str]]:
    """
    Extract line segments with layer information from a compiled route.

    Handles both ``RoutePath`` (single-layer) and ``RoutePath3D``
    (per-segment layers).

    Segments that contain NaN or infinite coordinates are silently
    skipped so they cannot poison downstream distance calculations.

    Returns:
        List of ``(x1, y1, x2, y2, layer)`` tuples.
    """
    segments: list[tuple[float, float, float, float, str]] = []

    def _ok(*values: float) -> bool:
        """True when all values are finite (no NaN, no inf)."""
        return all(math.isfinite(v) for v in values)

    if hasattr(route.path, 'segments'):
        # RoutePath3D  – (x, y, layer) triples
        pts = route.path.segments
        for i in range(len(pts) - 1):
            x1, y1, layer1 = pts[i]
            x2, y2, layer2 = pts[i + 1]
            if layer1 == layer2 and _ok(x1, y1, x2, y2):
                segments.append((x1, y1, x2, y2, layer1))
    else:
        # RoutePath – flat coordinates + single layer name
        coords = route.path.coordinates
        layer = route.path.layer_name
        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]
            if _ok(x1, y1, x2, y2):
                segments.append((x1, y1, x2, y2, layer))

    return segments


def _point_to_segment_distance(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> float:
    """Minimum distance from point *(px, py)* to segment *(x1,y1)-(x2,y2)*."""
    dx = x2 - x1
    dy = y2 - y1
    denom = dx * dx + dy * dy
    if denom == 0.0 or not math.isfinite(denom):
        return math.hypot(px - x1, py - y1)
    # Clamped projection parameter t ∈ [0, 1]
    t = ((px - x1) * dx + (py - y1) * dy) / denom
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _closest_point_on_segment(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> tuple[float, float]:
    """Closest point on segment *(x1,y1)-(x2,y2)* to point *(px, py)*."""
    dx = x2 - x1
    dy = y2 - y1
    denom = dx * dx + dy * dy
    if denom == 0.0 or not math.isfinite(denom):
        return (x1, y1)
    t = ((px - x1) * dx + (py - y1) * dy) / denom
    t = max(0.0, min(1.0, t))
    return (x1 + t * dx, y1 + t * dy)


def _segments_intersect(
    x1: float, y1: float, x2: float, y2: float,
    x3: float, y3: float, x4: float, y4: float,
) -> tuple[bool, float, float]:
    """
    Check whether two line segments intersect (proper intersection).

    Returns:
        ``(intersects, ix, iy)`` where *(ix, iy)* is the intersection
        point when ``intersects`` is ``True``.
    """
    def _orient(ax, ay, bx, by, cx, cy):
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    o1 = _orient(x1, y1, x2, y2, x3, y3)
    o2 = _orient(x1, y1, x2, y2, x4, y4)
    o3 = _orient(x3, y3, x4, y4, x1, y1)
    o4 = _orient(x3, y3, x4, y4, x2, y2)

    if o1 * o2 < 0.0 and o3 * o4 < 0.0:
        # Compute intersection point via parameter t on segment 2
        dx1, dy1 = x2 - x1, y2 - y1
        dx2, dy2 = x4 - x3, y4 - y3
        denom = dx1 * dy2 - dy1 * dx2
        if denom != 0.0:
            t = ((x1 - x3) * dy1 - (y1 - y3) * dx1) / denom
            ix = x3 + t * dx2
            iy = y3 + t * dy2
            return True, ix, iy

    return False, 0.0, 0.0


def _segment_to_segment_info(
    x1: float, y1: float, x2: float, y2: float,
    x3: float, y3: float, x4: float, y4: float,
) -> tuple[float, tuple[float, float], tuple[float, float]]:
    """
    Minimum distance between two line segments and the closest points.

    Returns:
        ``(distance, (cx1, cy1), (cx2, cy2))``.
    """
    # 1. Intersection → distance 0
    intersects, ix, iy = _segments_intersect(
        x1, y1, x2, y2, x3, y3, x4, y4,
    )
    if intersects:
        return 0.0, (ix, iy), (ix, iy)

    best_dist = float('inf')
    best_p1 = (0.0, 0.0)
    best_p2 = (0.0, 0.0)

    # 2. Endpoints of seg1 against seg2
    for (px, py) in [(x1, y1), (x2, y2)]:
        d = _point_to_segment_distance(px, py, x3, y3, x4, y4)
        if d < best_dist:
            best_dist = d
            best_p1 = (px, py)
            best_p2 = _closest_point_on_segment(px, py, x3, y3, x4, y4)

    # 3. Endpoints of seg2 against seg1
    for (px, py) in [(x3, y3), (x4, y4)]:
        d = _point_to_segment_distance(px, py, x1, y1, x2, y2)
        if d < best_dist:
            best_dist = d
            best_p1 = _closest_point_on_segment(px, py, x1, y1, x2, y2)
            best_p2 = (px, py)

    return best_dist, best_p1, best_p2


def _find_clearance_violations(
    route1,
    route2,
    required_distance: float,
    hv_net: str,
    lv_net: str,
) -> list[CreepageViolation]:
    """
    Find **all** clearance violations between two routes.

    Only segments residing on the **same layer** are compared.
    Cross-layer (via-to-via) creepage requires a separate pathfinding
    approach and is not computed here.

    Returns:
        List of ``CreepageViolation`` records (one per violating
        segment pair).
    """
    violations: list[CreepageViolation] = []

    segs1 = _extract_segments(route1)
    segs2 = _extract_segments(route2)

    for x1, y1, x2, y2, layer1 in segs1:
        for x3, y3, x4, y4, layer2 in segs2:
            if layer1 != layer2:
                # Different layers – via-to-via creepage not modelled
                continue

            dist, p1, p2 = _segment_to_segment_info(
                x1, y1, x2, y2, x3, y3, x4, y4,
            )

            if dist < required_distance:
                # Midpoint of closest approach as violation location
                loc = ((p1[0] + p2[0]) / 2.0,
                       (p1[1] + p2[1]) / 2.0)
                violations.append(CreepageViolation(
                    hv_net=hv_net,
                    lv_net=lv_net,
                    location=loc,
                    actual_distance=dist,
                    required_distance=required_distance,
                ))

    return violations


# ---------------------------------------------------------------------------
# Voltage → required creepage table
# ---------------------------------------------------------------------------

def _calculate_required_creepage(voltage: float) -> float:
    """
    Required creepage distance per IPC-2221 (simplified).

    ===========  =====
    Voltage (V)  mm
    ===========  =====
      0 –  15    0.13
     16 –  30    0.25
     31 –  50    0.50
     51 – 100    0.80
    101 – 150    1.25
    151 – 170    1.60
    171 – 250    3.20
    251 – 300    6.40
    301 – 600    8.00
    601 –1000   12.00
    ===========  =====

    Args:
        voltage: Working voltage (V).

    Returns:
        Required creepage distance (mm).

    Raises:
        ValueError: If *voltage* is NaN or not finite.
    """
    if math.isnan(voltage) or not math.isfinite(voltage):
        raise ValueError(
            f"Voltage must be a finite number, got {voltage!r}"
        )
    if voltage <= 15:
        return 0.13
    elif voltage <= 30:
        return 0.25
    elif voltage <= 50:
        return 0.5
    elif voltage <= 100:
        return 0.8
    elif voltage <= 150:
        return 1.25
    elif voltage <= 170:
        return 1.6
    elif voltage <= 250:
        return 3.2
    elif voltage <= 300:
        return 6.4
    elif voltage <= 600:
        return 8.0
    else:
        return 12.0
