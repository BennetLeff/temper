"""Brute-force O(n**2) clearance oracle for DRC completeness validation.

This module provides an independent O(n**2) pair-check implementation
with **zero** code-path overlap with ``clearance_check.py`` or
``clearance_engine.py``.  It is used by the completeness PBT to verify
the production engine finds **all** violations (not just that all
reported violations are genuine).

Gated by ``if __debug__:`` to exclude from production deployments (NFR3).

Usage (test only)::

    from temper_placer.router_v6.clearance_oracle import oracle_clearance_violations
    violations = oracle_clearance_violations(results, min_clearance=0.127)
"""

from __future__ import annotations

import math

from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults


def oracle_clearance_violations(
    routing_results: RoutingResults,
    min_clearance: float = 0.127,
) -> list[tuple[str, str, str, float]]:
    """Return all clearance violations using an O(n**2) brute-force check.

    Returns a list of ``(net1, net2, layer, actual_clearance)`` tuples
    where ``actual_clearance < min_clearance``.

    This implementation shares **no** code paths with the production
    ``clearance_check.py`` or ``clearance_engine.py``.  It uses its own
    segment extraction, distance computation, and width handling.
    """
    violations: list[tuple[str, str, str, float]] = []
    routes = list(routing_results.compiled_routes.items())

    if not __debug__:
        return violations

    for i in range(len(routes)):
        net1, route1 = routes[i]
        segs1 = _oracle_get_segments(route1)
        width1 = _oracle_get_width(route1)
        via_points1 = _oracle_get_via_points(route1)

        for j in range(i + 1, len(routes)):
            net2, route2 = routes[j]
            if net1 == net2:
                continue

            segs2 = _oracle_get_segments(route2)
            width2 = _oracle_get_width(route2)
            via_points2 = _oracle_get_via_points(route2)

            # Same-layer segment-to-segment
            for s1 in segs1:
                for s2 in segs2:
                    if s1[4] != s2[4]:
                        continue
                    seg_dist = _oracle_seg_seg_dist(
                        s1[0], s1[1], s1[2], s1[3],
                        s2[0], s2[1], s2[2], s2[3],
                    )
                    edge_dist = seg_dist - (width1 / 2.0) - (width2 / 2.0)
                    if edge_dist < min_clearance:
                        violations.append((net1, net2, s1[4], edge_dist))

            # Via-to-segment (route1 vias vs route2 segments)
            for vp1 in via_points1:
                vx, vy, layers, dia = vp1
                via_radius = dia / 2.0
                for s2 in segs2:
                    if s2[4] not in layers:
                        continue
                    pt_dist = _oracle_pt_seg_dist(vx, vy, s2[0], s2[1], s2[2], s2[3])
                    edge_dist = pt_dist - via_radius - (width2 / 2.0)
                    if edge_dist < min_clearance:
                        violations.append((net1, net2, s2[4], edge_dist))

            # Via-to-segment (route2 vias vs route1 segments)
            for vp2 in via_points2:
                vx, vy, layers, dia = vp2
                via_radius = dia / 2.0
                for s1 in segs1:
                    if s1[4] not in layers:
                        continue
                    pt_dist = _oracle_pt_seg_dist(vx, vy, s1[0], s1[1], s1[2], s1[3])
                    edge_dist = pt_dist - via_radius - (width1 / 2.0)
                    if edge_dist < min_clearance:
                        violations.append((net1, net2, s1[4], edge_dist))

    return violations


# ---------------------------------------------------------------------------
# Independent segment extraction — handles RoutePath (coordinates) and
# RoutePath3D (segments).  ZERO overlap with clearance_check.py.
# ---------------------------------------------------------------------------


def _oracle_get_segments(route: CompiledRoute) -> list[tuple[float, float, float, float, str]]:
    """Extract same-layer segments as ``(x1, y1, x2, y2, layer)``."""
    segs: list[tuple[float, float, float, float, str]] = []
    path = route.path
    if hasattr(path, 'segments'):  # RoutePath3D
        pts = path.segments
        for k in range(len(pts) - 1):
            p1, p2 = pts[k], pts[k + 1]
            if p1[2] == p2[2]:
                x1, y1 = p1[0], p1[1]
                x2, y2 = p2[0], p2[1]
                if all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                    segs.append((x1, y1, x2, y2, p1[2]))
    elif hasattr(path, 'coordinates'):  # RoutePath
        coords = path.coordinates
        layer = getattr(path, 'layer_name', 'F.Cu')
        for k in range(len(coords) - 1):
            p1, p2 = coords[k], coords[k + 1]
            x1, y1 = p1[0], p1[1]
            x2, y2 = p2[0], p2[1]
            if all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                segs.append((x1, y1, x2, y2, layer))
    return segs


def _oracle_get_via_points(
    route: CompiledRoute,
) -> list[tuple[float, float, set[str], float]]:
    """Extract via positions as ``(x, y, {layers}, diameter)``.

    Handles explicit ``Via`` objects AND ``RoutePath3D`` layer-changing
    segment endpoints.
    """
    points: list[tuple[float, float, set[str], float]] = []
    path = route.path

    # Explicit Via objects from CompiledRoute.vias
    for via in getattr(route, 'vias', []):
        vx, vy = via.position[0], via.position[1]
        dia = getattr(via, 'diameter', 0.6)
        layers: set[str] = set()
        for attr in ('from_layer', 'to_layer'):
            val = getattr(via, attr, None)
            if val:
                layers.add(str(val))
        if layers:
            points.append((vx, vy, layers, dia))

    # RoutePath3D layer-changing segment endpoints (via fallback)
    if hasattr(path, 'segments'):
        pts = path.segments
        for k in range(len(pts) - 1):
            p1, p2 = pts[k], pts[k + 1]
            if p1[2] != p2[2]:
                dia = max(getattr(route, 'width_mm', 0.6), 0.6)
                points.append((p1[0], p1[1], {p1[2], p2[2]}, dia))

    return points


def _oracle_get_width(route: CompiledRoute) -> float:
    """Get trace width from route, guarding against NaN/inf."""
    w = getattr(route, 'width_mm', 0.0)
    if not math.isfinite(w):
        return 0.0
    return w


# ---------------------------------------------------------------------------
# Independent distance computation — analytical, clamped-projection.
# ZERO overlap with clearance_check.py helpers.
# ---------------------------------------------------------------------------


def _oracle_pt_seg_dist(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> float:
    """Distance from point (px,py) to segment (ax,ay)-(bx,by).

    Clamped-projection — analytical (no sampling).
    """
    abx = bx - ax
    aby = by - ay
    len2 = abx * abx + aby * aby

    if len2 < 1e-12 or not math.isfinite(len2):
        dx = px - ax
        dy = py - ay
        return math.hypot(dx, dy)

    apx = px - ax
    apy = py - ay
    t = (apx * abx + apy * aby) / len2
    t = max(0.0, min(1.0, t))
    cpx = ax + t * abx
    cpy = ay + t * aby
    return math.hypot(px - cpx, py - cpy)


def _oracle_seg_seg_dist(
    ax: float, ay: float, bx: float, by: float,
    cx: float, cy: float, dx: float, dy: float,
) -> float:
    """Distance between two line segments AB and CD.

    Clamped-projection analytical algorithm (Ericson 2005, sec 5.1.9).
    """
    abx = bx - ax
    aby = by - ay
    cdx = dx - cx
    cdy = dy - cy
    acx = cx - ax
    acy = cy - ay

    a_len2 = abx * abx + aby * aby
    c_len2 = cdx * cdx + cdy * cdy
    eps = 1e-12

    if a_len2 < eps and c_len2 < eps:
        return math.hypot(acx, acy)
    if a_len2 < eps:
        return _oracle_pt_seg_dist(ax, ay, cx, cy, dx, dy)
    if c_len2 < eps:
        return _oracle_pt_seg_dist(cx, cy, ax, ay, bx, by)

    ab_dot_cd = abx * cdx + aby * cdy
    ac_dot_ab = acx * abx + acy * aby
    ac_dot_cd = acx * cdx + acy * cdy

    det = a_len2 * c_len2 - ab_dot_cd * ab_dot_cd
    if det > eps:
        s = (ac_dot_ab * c_len2 + ab_dot_cd * (-ac_dot_cd)) / det
        t = (a_len2 * (-ac_dot_cd) + ab_dot_cd * ac_dot_ab) / det
        if 0.0 <= s <= 1.0 and 0.0 <= t <= 1.0:
            cp1x = ax + s * abx
            cp1y = ay + s * aby
            cp2x = cx + t * cdx
            cp2y = cy + t * cdy
            return math.hypot(cp1x - cp2x, cp1y - cp2y)

    d0 = _oracle_pt_seg_dist(ax, ay, cx, cy, dx, dy)
    d1 = _oracle_pt_seg_dist(bx, by, cx, cy, dx, dy)
    d2 = _oracle_pt_seg_dist(cx, cy, ax, ay, bx, by)
    d3 = _oracle_pt_seg_dist(dx, dy, ax, ay, bx, by)
    return min(d0, d1, d2, d3)
