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

    Args:
        route1: First route
        route2: Second route

    Returns:
        Tuple of (min_clearance, location, layer)
    """
    min_dist = float('inf')
    closest_point = (0.0, 0.0)
    layer = route1.path.layer_name
    
    # Account for trace widths
    width1 = route1.width_mm
    width2 = route2.width_mm
    
    # Check all point pairs
    for p1 in route1.path.coordinates:
        for p2 in route2.path.coordinates:
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            center_dist = (dx**2 + dy**2)**0.5
            
            # Edge-to-edge distance
            edge_dist = center_dist - (width1 / 2) - (width2 / 2)
            
            if edge_dist < min_dist:
                min_dist = edge_dist
                closest_point = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    
    return max(0.0, min_dist), closest_point, layer


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
