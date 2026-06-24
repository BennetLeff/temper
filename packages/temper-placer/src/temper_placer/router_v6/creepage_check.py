"""
Router V6 Stage 5.6: Verify Creepage

Validates creepage distances for high-voltage isolation.
Part of temper-ytm8 (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class CreepageViolation:
    """A creepage distance violation."""

    hv_net: str
    lv_net: str
    location: tuple[float, float]  # Closest approach point
    actual_distance: float  # Actual creepage distance (mm)
    required_distance: float  # Required minimum distance (mm)

    @property
    def deficiency(self) -> float:
        """How much the distance is under requirement."""
        return self.required_distance - self.actual_distance


@dataclass
class CreepageReport:
    """Report of creepage distance violations."""

    violations: list[CreepageViolation]
    total_checks: int

    @property
    def violation_count(self) -> int:
        """Number of creepage violations."""
        return len(self.violations)

    @property
    def pass_rate(self) -> float:
        """Percentage of checks that pass."""
        if self.total_checks == 0:
            return 100.0
        return ((self.total_checks - self.violation_count) /
                self.total_checks * 100.0)


def verify_creepage(
    routing_results: RoutingResults,
    voltage_ratings: dict[str, float] | None = None,
    _default_creepage: float = 0.5,  # IPC-2221: 0.5mm for 50V
) -> CreepageReport:
    """
    Verify creepage distances for high-voltage isolation.

    Creepage is the shortest path along the PCB surface between
    conductors. Critical for safety in high-voltage designs.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        voltage_ratings: Optional dict of net_name -> voltage
        _default_creepage: Default minimum creepage distance (mm)

    Returns:
        CreepageReport with violations

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = verify_creepage(results)
        >>> report.violation_count >= 0
        True
    """
    violations = []
    total_checks = 0

    if voltage_ratings is None:
        voltage_ratings = {}

    # Find all HV net combinations that need checking
    hv_nets = [net for net in routing_results.compiled_routes.keys()
               if _is_high_voltage_net(net)]

    # Check HV nets against all other nets
    for hv_net in hv_nets:
        hv_route = routing_results.compiled_routes[hv_net]

        for other_net, other_route in routing_results.compiled_routes.items():
            if other_net == hv_net:
                continue

            total_checks += 1

            # Calculate minimum distance between nets
            min_distance, location = _calculate_minimum_distance(
                hv_route,
                other_route,
            )

            # Determine required creepage based on voltage
            hv_voltage = voltage_ratings.get(hv_net, 230.0)  # Default AC mains
            required_distance = _calculate_required_creepage(hv_voltage)

            if min_distance < required_distance:
                violations.append(CreepageViolation(
                    hv_net=hv_net,
                    lv_net=other_net,
                    location=location,
                    actual_distance=min_distance,
                    required_distance=required_distance,
                ))

    return CreepageReport(
        violations=violations,
        total_checks=total_checks,
    )


def _is_high_voltage_net(net_name: str) -> bool:
    """
    Check if net is high voltage.

    Args:
        net_name: Net name

    Returns:
        True if HV net
    """
    name_upper = net_name.upper()
    hv_keywords = ['AC_', 'HV_', 'HIGH_VOLTAGE', 'MAINS']
    return any(kw in name_upper for kw in hv_keywords)


def _calculate_minimum_distance(
    route1,
    route2,
) -> tuple[float, tuple[float, float]]:
    """
    Calculate minimum distance between two routes.

    Args:
        route1: First route
        route2: Second route

    Returns:
        Tuple of (min_distance, location)
    """
    min_dist = float('inf')
    closest_point = (0.0, 0.0)

    # Extract coordinates handling RoutePath3D
    def get_coords(route):
        if hasattr(route.path, 'segments'):
            return [c[:2] for c in route.path.segments]
        return route.path.coordinates

    coords1 = get_coords(route1)
    coords2 = get_coords(route2)

    # Check all point pairs between routes
    for p1 in coords1:
        for p2 in coords2:
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dist = (dx**2 + dy**2)**0.5

            if dist < min_dist:
                min_dist = dist
                closest_point = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)

    return min_dist, closest_point


def _calculate_required_creepage(voltage: float) -> float:
    """
    Calculate required creepage distance based on voltage.

    IPC-2221 guidelines (simplified):
    - 0-15V: 0.13mm
    - 16-30V: 0.25mm
    - 31-50V: 0.5mm
    - 51-100V: 0.8mm
    - 101-150V: 1.25mm
    - 151-170V: 1.6mm
    - 171-250V: 3.2mm
    - 251-300V: 6.4mm

    Args:
        voltage: Voltage (V)

    Returns:
        Required creepage distance (mm)
    """
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
    else:
        return 6.4
