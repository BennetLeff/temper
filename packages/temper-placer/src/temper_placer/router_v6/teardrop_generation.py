"""
Router V6 Stage 5.3: Insert Teardrops

Adds teardrops to pad/via connections for improved reliability.
Part of temper-q5dh (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class Teardrop:
    """A teardrop at a pad/via connection."""

    net_name: str
    connection_point: tuple[float, float]  # Where trace meets pad/via
    connection_type: str  # "via" or "pad"
    length_mm: float  # Teardrop length along trace
    width_mm: float  # Teardrop width at widest point


@dataclass
class TeardropReport:
    """Report of generated teardrops."""

    teardrops: list[Teardrop]

    @property
    def teardrop_count(self) -> int:
        """Total number of teardrops generated."""
        return len(self.teardrops)

    @property
    def via_teardrop_count(self) -> int:
        """Number of via teardrops."""
        return sum(1 for t in self.teardrops if t.connection_type == "via")

    @property
    def pad_teardrop_count(self) -> int:
        """Number of pad teardrops."""
        return sum(1 for t in self.teardrops if t.connection_type == "pad")


def insert_teardrops(
    routing_results: RoutingResults,
    teardrop_length_ratio: float = 0.5,  # Length as ratio of pad/via diameter
    enable_via_teardrops: bool = True,
    enable_pad_teardrops: bool = False,  # Usually not needed for SMD pads
) -> TeardropReport:
    """
    Insert teardrops at pad/via connections.

    Teardrops provide gradual transition from narrow trace to wide pad/via,
    reducing mechanical stress and improving manufacturability.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        teardrop_length_ratio: Teardrop length as ratio of connection diameter
        enable_via_teardrops: Whether to add teardrops to vias
        enable_pad_teardrops: Whether to add teardrops to pads

    Returns:
        TeardropReport with all generated teardrops

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = insert_teardrops(results)
        >>> report.teardrop_count >= 0
        True
    """
    teardrops = []

    for net_name, compiled_route in routing_results.compiled_routes.items():
        # Add teardrops to vias if enabled
        if enable_via_teardrops:
            for via in compiled_route.vias:
                teardrop = _generate_via_teardrop(
                    net_name,
                    via,
                    compiled_route.width_mm,
                    teardrop_length_ratio,
                )
                if teardrop:
                    teardrops.append(teardrop)

        # Add teardrops to pads if enabled
        if enable_pad_teardrops:
            # Would analyze path endpoints and add pad teardrops
            # Simplified for now - SMD pads typically don't need teardrops
            pass

    return TeardropReport(teardrops=teardrops)


def _generate_via_teardrop(
    net_name: str,
    via,
    trace_width: float,
    length_ratio: float,
) -> Teardrop | None:
    """
    Generate teardrop for a via connection.

    Args:
        net_name: Net name
        via: Via object
        trace_width: Width of connecting trace
        length_ratio: Teardrop length ratio

    Returns:
        Teardrop or None if not needed
    """
    # Calculate teardrop dimensions
    teardrop_length = via.diameter * length_ratio
    teardrop_width = via.diameter

    # Only add teardrop if via is larger than trace
    if via.diameter > trace_width * 1.2:
        return Teardrop(
            net_name=net_name,
            connection_point=via.position,
            connection_type="via",
            length_mm=teardrop_length,
            width_mm=teardrop_width,
        )

    return None
