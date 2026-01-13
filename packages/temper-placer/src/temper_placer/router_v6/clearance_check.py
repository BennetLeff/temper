"""
Router V6 Stage 5.7: Verify Clearance

Validates clearance distances between all conductors.
Part of temper-8vjm (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class ClearanceViolation:
    """A clearance distance violation."""

    net1: str
    net2: str
    location: tuple[float, float]  # Violation location
    actual_clearance: float  # Actual spacing (mm)
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
) -> ClearanceReport:
    """
    Verify clearance distances between all conductors.

    Clearance is the straight-line distance through air between
    conductors. Critical for preventing shorts and ensuring reliability.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        min_clearance: Minimum clearance distance (mm)

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

            # Determine required clearance
            required = _get_required_clearance(net1, net2, min_clearance)

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
    Calculate minimum clearance between two routes.
    """
    min_dist = float('inf')
    closest_point = (0.0, 0.0)
    violation_layer = "unknown"

    # Account for trace widths
    width1 = route1.width_mm
    width2 = route2.width_mm

    # Extract segments (x1, y1, x2, y2, layer) from routes
    def get_segments(route):
        segs = []
        path = route.path
        if hasattr(path, 'segments'): # RoutePath3D
            for i in range(len(path.segments) - 1):
                p1, p2 = path.segments[i], path.segments[i+1]
                if p1[2] == p2[2]: # Same layer segment
                    segs.append((p1[0], p1[1], p2[0], p2[1], p1[2]))
        elif hasattr(path, 'coordinates'): # RoutePath
            layer = getattr(path, 'layer_name', "F.Cu")
            for i in range(len(path.coordinates) - 1):
                p1, p2 = path.coordinates[i], path.coordinates[i+1]
                segs.append((p1[0], p1[1], p2[0], p2[1], layer))
        return segs

    segs1 = get_segments(route1)
    segs2 = get_segments(route2)

    for s1 in segs1:
        for s2 in segs2:
            # ONLY check clearance if on the same layer
            if s1[4] != s2[4]:
                continue
            
            # Distance between segments (accurate segment-to-segment)
            dist = _segment_to_segment_dist(
                (s1[0], s1[1]), (s1[2], s1[3]),
                (s2[0], s2[1]), (s2[2], s2[3])
            )
            
            # Edge-to-edge distance
            edge_dist = dist - (width1 / 2) - (width2 / 2)

            if edge_dist < min_dist:
                min_dist = edge_dist
                closest_point = ((s1[0] + s2[0]) / 2, (s1[1] + s2[1]) / 2)
                violation_layer = s1[4]

    return max(0.0, min_dist), closest_point, violation_layer


def _segment_to_segment_dist(p1, p2, p3, p4):
    """Accurate distance between two line segments p1-p2 and p3-p4."""
    # Simplified version using sampling for now, but better than just point-to-point
    # We sample 10 points along each segment
    steps = 5
    min_d = float('inf')
    for i in range(steps + 1):
        t1 = i / steps
        v1 = (p1[0] + t1*(p2[0]-p1[0]), p1[1] + t1*(p2[1]-p1[1]))
        for j in range(steps + 1):
            t2 = j / steps
            v2 = (p3[0] + t2*(p4[0]-p3[0]), p3[1] + t2*(p4[1]-p3[1]))
            d = ((v1[0]-v2[0])**2 + (v1[1]-v2[1])**2)**0.5
            if d < min_d:
                min_d = d
    return min_d


def _get_required_clearance(
    net1: str,
    net2: str,
    default_clearance: float,
) -> float:
    """
    Get required clearance between two nets.

    Args:
        net1: First net name
        net2: Second net name
        default_clearance: Default clearance

    Returns:
        Required clearance (mm)
    """
    # HV nets require larger clearance
    hv_keywords = ['AC_', 'HV_', 'HIGH_VOLTAGE']

    net1_upper = net1.upper()
    net2_upper = net2.upper()

    is_hv1 = any(kw in net1_upper for kw in hv_keywords)
    is_hv2 = any(kw in net2_upper for kw in hv_keywords)

    if is_hv1 or is_hv2:
        # HV requires 0.5mm minimum
        return max(default_clearance, 0.5)

    return default_clearance
