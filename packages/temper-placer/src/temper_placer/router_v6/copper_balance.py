"""
Router V6 Stage 5.5: Analyze and Balance Copper

Analyzes copper distribution to prevent PCB warping.
Part of temper-nd5z (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class LayerCopperBalance:
    """Copper balance analysis for a single layer."""

    layer_name: str
    total_area_mm2: float
    copper_area_mm2: float
    copper_percentage: float
    is_balanced: bool  # Within 30-70% range

    @property
    def needs_balancing(self) -> bool:
        """Check if layer needs copper balancing."""
        return not self.is_balanced


@dataclass
class CopperBalanceReport:
    """Report of copper balance across all layers."""

    layer_balances: list[LayerCopperBalance]

    @property
    def balanced_layer_count(self) -> int:
        """Number of layers within balance range."""
        return sum(1 for lb in self.layer_balances if lb.is_balanced)

    @property
    def unbalanced_layer_count(self) -> int:
        """Number of layers needing balancing."""
        return sum(1 for lb in self.layer_balances if not lb.is_balanced)


def analyze_copper_balance(
    routing_results: RoutingResults,
    board_width: float,
    board_height: float,
    min_copper_percentage: float = 30.0,
    max_copper_percentage: float = 70.0,
) -> CopperBalanceReport:
    """
    Analyze copper distribution across PCB layers.

    Copper imbalance causes thermal stress during reflow,
    leading to board warping. Target: 30-70% copper coverage.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        board_width: Board width (mm)
        board_height: Board height (mm)
        min_copper_percentage: Minimum acceptable copper %
        max_copper_percentage: Maximum acceptable copper %

    Returns:
        CopperBalanceReport with per-layer analysis

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = analyze_copper_balance(results, 100, 100)
        >>> report.balanced_layer_count >= 0
        True
    """
    layer_balances = []

    # Calculate total board area
    total_area = board_width * board_height

    # Analyze each layer
    layers_to_check = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

    for layer_name in layers_to_check:
        # Calculate copper area on this layer
        copper_area = _calculate_layer_copper_area(
            routing_results,
            layer_name,
        )

        # Calculate percentage
        copper_percentage = (copper_area / total_area) * 100.0 if total_area > 0 else 0.0

        # Check if balanced
        is_balanced = (min_copper_percentage <= copper_percentage <= max_copper_percentage)

        layer_balances.append(LayerCopperBalance(
            layer_name=layer_name,
            total_area_mm2=total_area,
            copper_area_mm2=copper_area,
            copper_percentage=copper_percentage,
            is_balanced=is_balanced,
        ))

    return CopperBalanceReport(layer_balances=layer_balances)


def _calculate_layer_copper_area(
    routing_results: RoutingResults,
    layer_name: str,
) -> float:
    """
    Calculate copper area on a specific layer.

    Args:
        routing_results: Routing results
        layer_name: Layer to analyze

    Returns:
        Copper area in mm²
    """
    copper_area = 0.0

    for net_name, compiled_route in routing_results.compiled_routes.items():
        # Check if route is on this layer
        if compiled_route.path.layer_name == layer_name:
            # Estimate copper area from trace length × width
            trace_length = compiled_route.path.path_length
            trace_width = compiled_route.width_mm
            copper_area += trace_length * trace_width

        # Add via pad area on this layer
        for via in compiled_route.vias:
            if via.from_layer == layer_name or via.to_layer == layer_name:
                # Via pad area = π × (diameter/2)²
                via_area = 3.14159 * (via.diameter / 2.0) ** 2
                copper_area += via_area

    return copper_area
