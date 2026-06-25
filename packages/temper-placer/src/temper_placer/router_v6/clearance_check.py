"""
Router V6 Stage 5.7: Verify Clearance

Validates clearance distances between all conductors.
Part of temper-8vjm (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from temper_placer.router_v6.clearance_engine import get_clearance
from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class ClearanceViolation:
    """A clearance distance violation."""

    net1: str
    net2: str
    location: tuple[float, float]  # Violation location
    actual_clearance: float  # Actual spacing (mm); negative = overlap
    required_clearance: float  # Required minimum (mm)
    layer: str  # Layer where violation occurs

    @property
    def deficiency(self) -> float:
        """How much the clearance is under requirement."""
        return self.required_clearance - self.actual_clearance


@dataclass
class ClearanceReport:
    """Report of clearance violations."""

    violations: list[ClearanceViolation]
    total_checks: int

    @property
    def violation_count(self) -> int:
        """Number of clearance violations."""
        return len(self.violations)

    @property
    def pass_rate(self) -> float:
        """Percentage of checks that pass."""
        if self.total_checks == 0:
            return 100.0
        return ((self.total_checks - self.violation_count) /
                self.total_checks * 100.0)


def verify_clearance(
    routing_results: RoutingResults,
    min_clearance: float = 0.127,  # 5mil standard
    voltage_ratings: dict[str, float] | None = None,
) -> ClearanceReport:
    """
    Verify clearance distances between all conductors.

    Clearance is the straight-line distance through air between
    conductors. Critical for preventing shorts and ensuring reliability.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        min_clearance: Minimum clearance distance (mm)
        voltage_ratings: Optional dict of net_name -> voltage (V).
            Used to determine voltage-dependent HV clearance.

    Returns:
        ClearanceReport with violations

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = verify_clearance(results)
        >>> report.violation_count >= 0
        True
    """
    violations = []
    total_checks = 0

    if voltage_ratings is None:
        voltage_ratings = {}

    if math.isnan(min_clearance) or not math.isfinite(min_clearance):
        raise ValueError(
            f"min_clearance must be a finite number, got {min_clearance!r}"
        )

    # Get all route pairs to check
    routes = list(routing_results.compiled_routes.items())

    for i in range(len(routes)):
        net1, route1 = routes[i]

        for j in range(i + 1, len(routes)):
            net2, route2 = routes[j]

            # Skip if same net
            if net1 == net2:
                continue

            total_checks += 1

            # Check clearance between routes
            min_dist, location, layer = _calculate_minimum_clearance(
                route1,
                route2,
            )

            # Determine required clearance (unified multi-standard engine)
            required = _get_required_clearance(
                net1, net2, min_clearance, voltage_ratings,
                layer=layer,
            )

            if min_dist < required:
                violations.append(ClearanceViolation(
                    net1=net1,
                    net2=net2,
                    location=location,
                    actual_clearance=min_dist,
                    required_clearance=required,
                    layer=layer,
                ))

    return ClearanceReport(
        violations=violations,
        total_checks=total_checks,
    )


def _calculate_minimum_clearance(
    route1,
    route2,
) -> tuple[float, tuple[float, float], str]:
    """
    Calculate minimum edge-to-edge clearance between two routes.

    Uses analytical segment-to-segment closest-point computation
    (clamped projection) — no sampling.  Reports the actual closest-
    approach point and allows negative clearance for overlaps.

    Also checks via footprints against nearby traces for RoutePath3D
    cross-layer segments and explicit Via objects.
    """
    min_dist = float('inf')
    closest_point = (0.0, 0.0)
    violation_layer = "unknown"

    # Account for trace widths (with hasattr guard)
    width1 = getattr(route1, 'width_mm', 0.0)
    width2 = getattr(route2, 'width_mm', 0.0)
    # Guard against NaN / infinite widths
    if not math.isfinite(width1):
        width1 = 0.0
    if not math.isfinite(width2):
        width2 = 0.0

    # Default via diameter (used when no explicit Via object is available)
    via_diameter_default = max(width1, 0.6)

    # Extract same-layer segments (x1, y1, x2, y2, layer) from routes
    def get_segments(route):
        segs = []
        path = route.path
        if hasattr(path, 'segments'):  # RoutePath3D
            for i in range(len(path.segments) - 1):
                p1, p2 = path.segments[i], path.segments[i + 1]
                if p1[2] == p2[2]:  # Same layer segment
                    x1, y1, x2, y2 = p1[0], p1[1], p2[0], p2[1]
                    if all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                        segs.append((x1, y1, x2, y2, p1[2]))
        elif hasattr(path, 'coordinates'):  # RoutePath
            layer = getattr(path, 'layer_name', "F.Cu")
            for i in range(len(path.coordinates) - 1):
                p1, p2 = path.coordinates[i], path.coordinates[i + 1]
                x1, y1, x2, y2 = p1[0], p1[1], p2[0], p2[1]
                if all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                    segs.append((x1, y1, x2, y2, layer))
        return segs

    # Extract cross-layer (via) points: (x, y, from_layer, to_layer)
    def get_via_points_from_path(route):
        """Yield (x, y, layer1, layer2) for each layer-changing segment."""
        points = []
        path = route.path
        if hasattr(path, 'segments'):
            for i in range(len(path.segments) - 1):
                p1, p2 = path.segments[i], path.segments[i + 1]
                if p1[2] != p2[2]:  # Layer change = via
                    points.append((p1[0], p1[1], p1[2], p2[2]))
        return points

    segs1 = get_segments(route1)
    segs2 = get_segments(route2)

    # --- Same-layer segment-to-segment checks ---
    for s1 in segs1:
        for s2 in segs2:
            # ONLY check clearance if on the same layer
            if s1[4] != s2[4]:
                continue

            # Analytical segment-to-segment distance with closest points
            seg_dist, cp1, cp2 = _segment_to_segment_dist(
                (s1[0], s1[1]), (s1[2], s1[3]),
                (s2[0], s2[1]), (s2[2], s2[3]),
            )

            # Edge-to-edge distance (allows negative = overlap)
            edge_dist = seg_dist - (width1 / 2) - (width2 / 2)

            if edge_dist < min_dist:
                min_dist = edge_dist
                # Midpoint of the two closest-approach points
                closest_point = (
                    (cp1[0] + cp2[0]) / 2,
                    (cp1[1] + cp2[1]) / 2,
                )
                violation_layer = s1[4]

    # --- Via-to-trace checks ---
    # Check explicit Via objects from each route against the other route's
    # segments on the layers the via touches.

    def _check_via_against_segs(via, other_segs, other_width,
                                my_width_guard):
        """Update min_dist / closest_point / violation_layer if a closer
        approach is found between a via and a set of segments."""
        nonlocal min_dist, closest_point, violation_layer

        # via is a Via object with position, from_layer, to_layer, diameter
        via_x, via_y = via.position
        via_radius = via.diameter / 2.0
        # Layers spanned by this via (simplified: from_layer and to_layer)
        via_layers = {via.from_layer, via.to_layer}

        for seg in other_segs:
            if seg[4] not in via_layers:
                continue
            # Point-to-segment distance from via centre to segment
            pt_dist, _cp_on_seg, _ = _point_to_segment_dist(
                (via_x, via_y),
                (seg[0], seg[1]), (seg[2], seg[3]),
            )
            edge_dist = pt_dist - via_radius - (other_width / 2)
            if edge_dist < min_dist:
                min_dist = edge_dist
                closest_point = (via_x, via_y)
                violation_layer = seg[4]

    # Route1 vias vs route2 segments
    for via in getattr(route1, 'vias', []):
        _check_via_against_segs(via, segs2, width2, width1)

    # Route2 vias vs route1 segments
    for via in getattr(route2, 'vias', []):
        _check_via_against_segs(via, segs1, width1, width2)

    # --- Cross-layer segment via points (RoutePath3D fallback) ---
    # For paths that have layer-changing segments but no explicit Via
    # objects, treat the segment endpoint as a via pad.
    def _check_via_point_against_segs(vx, vy, via_diam,
                                       layers, other_segs, other_width):
        nonlocal min_dist, closest_point, violation_layer
        via_radius = via_diam / 2.0
        for seg in other_segs:
            if seg[4] not in layers:
                continue
            pt_dist, _cp_on_seg, _ = _point_to_segment_dist(
                (vx, vy),
                (seg[0], seg[1]), (seg[2], seg[3]),
            )
            edge_dist = pt_dist - via_radius - (other_width / 2)
            if edge_dist < min_dist:
                min_dist = edge_dist
                closest_point = (vx, vy)
                violation_layer = seg[4]

    # Cross-layer points from route1 vs route2 segments
    for vx, vy, l1, l2 in get_via_points_from_path(route1):
        _check_via_point_against_segs(
            vx, vy, via_diameter_default, {l1, l2}, segs2, width2)

    # Cross-layer points from route2 vs route1 segments
    for vx, vy, l1, l2 in get_via_points_from_path(route2):
        _check_via_point_against_segs(
            vx, vy, via_diameter_default, {l1, l2}, segs1, width1)

    # Return actual edge_dist (may be negative for overlaps) — do NOT
    # clamp to 0.0 so that overlap severity is visible.
    return min_dist, closest_point, violation_layer


def _point_to_segment_dist(p, a, b):
    """Closest distance from point p to segment a-b.

    Returns (distance, closest_point_on_segment, point_p).
    The third element is p itself for interface compatibility with
    ``_segment_to_segment_dist``.
    """
    ab = (b[0] - a[0], b[1] - a[1])
    ap = (p[0] - a[0], p[1] - a[1])
    len2 = ab[0] * ab[0] + ab[1] * ab[1]

    if len2 < 1e-12 or not math.isfinite(len2):
        # Degenerate segment: a and b coincide, or NaN/inf endpoints
        dx = p[0] - a[0]
        dy = p[1] - a[1]
        return (dx * dx + dy * dy) ** 0.5, a, p

    t = (ap[0] * ab[0] + ap[1] * ab[1]) / len2
    t = max(0.0, min(1.0, t))
    cp = (a[0] + t * ab[0], a[1] + t * ab[1])
    dx = p[0] - cp[0]
    dy = p[1] - cp[1]
    return (dx * dx + dy * dy) ** 0.5, cp, p


def _segment_to_segment_dist(a, b, c, d):
    """Analytical closest distance between two line segments AB and CD.

    Uses clamped-projection (the standard algorithm from
    Real-Time Collision Detection, Ericson 2005, §5.1.9).
    No sampling — exact result up to floating-point precision.

    Returns:
        (min_distance, closest_point_on_AB, closest_point_on_CD)
    """
    # Direction vectors
    ab = (b[0] - a[0], b[1] - a[1])
    cd = (d[0] - c[0], d[1] - c[1])
    # Vector from A to C
    ac = (c[0] - a[0], c[1] - a[1])

    a_len2 = ab[0] * ab[0] + ab[1] * ab[1]   # |AB|^2
    c_len2 = cd[0] * cd[0] + cd[1] * cd[1]   # |CD|^2
    eps = 1e-12

    # --- Degenerate cases: one or both segments are points ---
    if a_len2 < eps and c_len2 < eps:
        dx = ac[0]
        dy = ac[1]
        return (dx * dx + dy * dy) ** 0.5, a, c

    if a_len2 < eps:
        # AB is a point; distance from A to segment CD
        d_pt, cp, _ = _point_to_segment_dist(a, c, d)
        return d_pt, a, cp

    if c_len2 < eps:
        # CD is a point; distance from C to segment AB
        d_pt, cp, _ = _point_to_segment_dist(c, a, b)
        return d_pt, cp, c

    # --- General case: two non-degenerate segments ---
    ab_dot_cd = ab[0] * cd[0] + ab[1] * cd[1]
    ac_dot_ab = ac[0] * ab[0] + ac[1] * ab[1]
    ac_dot_cd = ac[0] * cd[0] + ac[1] * cd[1]

    # Solve the 2×2 linear system for the unconstrained minimum of
    #   f(s,t) = |(A + s*AB) - (C + t*CD)|^2
    #         = |(A-C) + s*AB - t*CD|^2
    #
    # ∂f/∂s = 2 AB·(A-C) + 2s|AB|² - 2t(AB·CD) = 0
    # ∂f/∂t = -2 CD·(A-C) - 2s(AB·CD) + 2t|CD|² = 0
    #
    #   |AB|² · s  +  (-AB·CD) · t  =  -AB·(A-C)  =  AB·(C-A)  =  ac_dot_ab
    #   (-AB·CD) · s  +  |CD|² · t  =  CD·(A-C)   =  -CD·(C-A) =  -ac_dot_cd
    det = a_len2 * c_len2 - ab_dot_cd * ab_dot_cd

    if det > eps:
        s = (ac_dot_ab * c_len2 + ab_dot_cd * (-ac_dot_cd)) / det
        t = (a_len2 * (-ac_dot_cd) + ab_dot_cd * ac_dot_ab) / det

        if 0.0 <= s <= 1.0 and 0.0 <= t <= 1.0:
            # Interior minimum
            cp1 = (a[0] + s * ab[0], a[1] + s * ab[1])
            cp2 = (c[0] + t * cd[0], c[1] + t * cd[1])
            dx = cp1[0] - cp2[0]
            dy = cp1[1] - cp2[1]
            return (dx * dx + dy * dy) ** 0.5, cp1, cp2

    # Minimum is on the boundary of the parameter square [0,1]×[0,1].
    # Check all four edges (point-to-segment); corner cases are covered
    # because _point_to_segment_dist clamps its parameter.
    best_dist = float('inf')
    best_cp1 = a
    best_cp2 = c

    def _update(dist, p1, p2):
        nonlocal best_dist, best_cp1, best_cp2
        if dist < best_dist:
            best_dist = dist
            best_cp1 = p1
            best_cp2 = p2

    # s = 0: point A to segment CD
    d0, cp, _ = _point_to_segment_dist(a, c, d)
    _update(d0, a, cp)

    # s = 1: point B to segment CD
    d1, cp, _ = _point_to_segment_dist(b, c, d)
    _update(d1, b, cp)

    # t = 0: point C to segment AB
    d2, cp, _ = _point_to_segment_dist(c, a, b)
    _update(d2, cp, c)

    # t = 1: point D to segment AB
    d3, cp, _ = _point_to_segment_dist(d, a, b)
    _update(d3, cp, d)

    return best_dist, best_cp1, best_cp2


def _get_required_clearance(
    net1: str,
    net2: str,
    default_clearance: float,
    voltage_ratings: dict[str, float] | None = None,
    *,
    layer: str = "F.Cu",
) -> float:
    """
    Get required clearance between two nets.

    For high-voltage nets the clearance is determined by the unified
    multi-standard clearance engine (IEC 60950-1, 60335-1, 60664-1,
    62368-1, IPC-2221).  Non-HV nets use the caller-supplied default.

    Args:
        net1: First net name
        net2: Second net name
        default_clearance: Default clearance (mm) for non-HV nets
        voltage_ratings: Optional dict of net_name -> voltage (V)
        layer: Layer name (e.g. "F.Cu", "In1.Cu") for
            internal-layer creepage reduction per IEC 60664-1.

    Returns:
        Required clearance (mm)
    """
    if voltage_ratings is None:
        voltage_ratings = {}

    hv_keywords = ['AC_', 'HV_', 'HIGH_VOLTAGE', 'MAINS']

    net1_upper = net1.upper()
    net2_upper = net2.upper()

    is_hv1 = any(kw in net1_upper for kw in hv_keywords)
    is_hv2 = any(kw in net2_upper for kw in hv_keywords)

    if is_hv1 or is_hv2:
        # Determine the governing voltage: pick the HV net's voltage
        # (if both are HV, take the higher voltage).
        voltage = 0.0
        if is_hv1:
            v1 = voltage_ratings.get(net1, 230.0)
            if math.isfinite(v1):
                voltage = max(voltage, v1)
            else:
                voltage = max(voltage, 230.0)
        if is_hv2:
            v2 = voltage_ratings.get(net2, 230.0)
            if math.isfinite(v2):
                voltage = max(voltage, v2)
            else:
                voltage = max(voltage, 230.0)

        # Classify each net for the unified engine
        class_a = _classify_net_class(net1)
        class_b = _classify_net_class(net2)

        layer_type = "internal" if _is_internal_layer(layer) else "external"

        hv_required = get_clearance(
            class_a, class_b,
            voltage=voltage,
            layer_type=layer_type,
        )
        return max(default_clearance, hv_required)

    return default_clearance


def _classify_net_class(net_name: str) -> str:
    """Map a net name to a net-class label for the clearance engine."""
    upper = net_name.upper()
    hv_keywords = ['AC_', 'HV_', 'HIGH_VOLTAGE', 'MAINS', 'LINE', 'NEUTRAL',
                   'PRIMARY', 'HOT', 'L1', 'L2', 'L3', 'PHASE', 'VBUS', 'B+']
    if any(kw in upper for kw in hv_keywords):
        return "HV"
    if any(kw in upper for kw in ('GND', 'VSS', 'PGND', 'CGND', 'AGND')):
        return "GND"
    if any(kw in upper for kw in ('VCC', 'VDD', '+3V3', '+5V', '+12V', '+15V', 'POWER')):
        return "POWER"
    return "SIGNAL"


def _is_internal_layer(layer_name: str) -> bool:
    """Return True if *layer_name* designates an internal copper layer."""
    return layer_name.startswith("In") or "In" in layer_name
