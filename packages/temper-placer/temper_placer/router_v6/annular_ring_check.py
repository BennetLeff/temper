"""
Router V6 Stage 5.2: Check Annular Rings

Validates that via annular rings meet minimum manufacturing requirements.
Part of temper-j2xd (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class AnnularRingViolation:
    """An annular ring violation on a via."""

    net_name: str
    via_position: tuple[float, float]
    pad_diameter: float  # Via pad diameter (mm)
    drill_diameter: float  # Via drill diameter (mm)
    actual_ring_width: float  # Actual annular ring width (mm)
    minimum_required: float  # Minimum required ring width (mm)

    @property
    def deficiency(self) -> float:
        """How much the ring is undersized."""
        return self.minimum_required - self.actual_ring_width


@dataclass
class AnnularRingReport:
    """Report of annular ring violations."""

    violations: list[AnnularRingViolation]
    total_vias_checked: int

    @property
    def violation_count(self) -> int:
        """Number of vias with violations."""
        return len(self.violations)

    @property
    def pass_rate(self) -> float:
        """Percentage of vias that pass."""
        if self.total_vias_checked == 0:
            return 100.0
        return ((self.total_vias_checked - self.violation_count) /
                self.total_vias_checked * 100.0)


def check_annular_rings(
    routing_results: RoutingResults,
    min_annular_ring: float = 0.15,  # IPC-6012 Class 2: 0.05mm minimum
) -> AnnularRingReport:
    """
    Check via annular rings for manufacturing compliance.

    The annular ring is the copper remaining around the drill hole.
    Too small = unreliable connection, drill wander risk.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        min_annular_ring: Minimum annular ring width (mm)

    Returns:
        AnnularRingReport with violations

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = check_annular_rings(results)
        >>> report.violation_count >= 0
        True
    """
    violations = []
    total_vias = 0

    for net_name, compiled_route in routing_results.compiled_routes.items():
        # Check all vias for this net
        for via in compiled_route.vias:
            total_vias += 1

            # Calculate annular ring width
            # Ring width = (pad_diameter - drill_diameter) / 2
            ring_width = (via.diameter - via.drill) / 2.0

            if ring_width < min_annular_ring:
                # Violation detected
                violations.append(AnnularRingViolation(
                    net_name=net_name,
                    via_position=via.position,
                    pad_diameter=via.diameter,
                    drill_diameter=via.drill,
                    actual_ring_width=ring_width,
                    minimum_required=min_annular_ring,
                ))

    return AnnularRingReport(
        violations=violations,
        total_vias_checked=total_vias,
    )
