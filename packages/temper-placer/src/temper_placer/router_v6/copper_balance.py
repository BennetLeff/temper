"""
Router V6 Stage 5.5: Analyze and Balance Copper

Analyzes copper distribution to prevent PCB warping.
Part of temper-nd5z (Stage 5 - Manufacturing DRC)

.. note::

    Copper pours, filled zones, and polygons are **not** currently
    accounted for in the copper area estimation.  Only trace segments
    (including per-layer segments from ``RoutePath3D``), via annular
    rings (pad minus drill), and plane-net approximations are included.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from temper_placer.core.board import STANDARD_LAYER_ORDER
from temper_placer.router_v6.routing_results import RoutingResults

if TYPE_CHECKING:
    from temper_placer.router_v6.astar_core import RoutePath3D

# ---------------------------------------------------------------------------
# Plane-net → layer mapping
# ---------------------------------------------------------------------------
# When a net carries ``width_mm == 0.0`` it is a plane net (connected
# through an inner-layer copper pour rather than discrete traces).
# The mapping below assigns each known plane net to its canonical layer.
# Nets not listed here default to ``"In1.Cu"`` (the ground plane).
_PLANE_NET_LAYER: dict[str, str] = {
    # Ground nets -> In1.Cu (inner ground plane)
    "GND": "In1.Cu",
    "PGND": "In1.Cu",
    "CGND": "In1.Cu",
    # Power rails -> In2.Cu (inner power island)
    "+15V": "In2.Cu",
    "+3V3": "In2.Cu",
    "+5V": "In2.Cu",
    "VCC": "In2.Cu",
    "VDD": "In2.Cu",
}

# Typical fill ratio for a plane layer (copper pour with
# anti-pad / thermal relief cut-outs).  Based on IPC-2221 guidance
# that plane layers should have ≥ 80 % copper coverage.
_PLANE_FILL_RATIO: float = 0.85

# ---------------------------------------------------------------------------
# Canonical 4-layer order as KiCad layer names (top → bottom).
# Used to enumerate intermediate layers for through-hole vias.
_LAYER_ORDER_NAMES: tuple[str, ...] = tuple(
    str(idx) for idx in STANDARD_LAYER_ORDER
)  # ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")


@dataclass
class LayerCopperBalance:
    """Copper balance analysis for a single layer."""

    layer_name: str
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
    total_area_mm2: float  # Board area computed once (width × height)

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
    # Compute board-level constant once — guard degenerate dimensions
    if (
        math.isnan(board_width)
        or math.isnan(board_height)
        or math.isinf(board_width)
        or math.isinf(board_height)
    ):
        total_area = 0.0
    else:
        total_area = board_width * board_height

    layer_balances: list[LayerCopperBalance] = []
    layers_to_check = [str(idx) for idx in STANDARD_LAYER_ORDER]

    for layer_name in layers_to_check:
        copper_area = _calculate_layer_copper_area(
            routing_results,
            layer_name,
            total_area,
        )

        copper_percentage = (
            (copper_area / total_area) * 100.0 if total_area > 0 else 0.0
        )
        is_balanced = (
            min_copper_percentage <= copper_percentage <= max_copper_percentage
        )

        layer_balances.append(
            LayerCopperBalance(
                layer_name=layer_name,
                copper_area_mm2=copper_area,
                copper_percentage=copper_percentage,
                is_balanced=is_balanced,
            )
        )

    return CopperBalanceReport(
        layer_balances=layer_balances,
        total_area_mm2=total_area,
    )


def _calculate_layer_copper_area(
    routing_results: RoutingResults,
    layer_name: str,
    total_area: float,
) -> float:
    """
    Calculate copper area on a specific layer.

    Args:
        routing_results: Routing results
        layer_name: Layer to analyze
        total_area: Board total area in mm² (width × height)

    Returns:
        Copper area in mm²
    """
    copper_area = 0.0

    for net_name, compiled_route in routing_results.compiled_routes.items():
        # ---------------------------------------------------------------
        # Trace area
        # ---------------------------------------------------------------
        if compiled_route.width_mm == 0.0:
            # Plane net — estimate copper from board area × fill ratio
            plane_layer = _PLANE_NET_LAYER.get(net_name, "In1.Cu")
            if layer_name == plane_layer:
                copper_area += total_area * _PLANE_FILL_RATIO
            continue  # Plane nets have no traces or vias to add

        # --- RoutePath (single-layer) ---
        if hasattr(compiled_route.path, "layer_name"):
            if compiled_route.path.layer_name == layer_name:
                trace_length = compiled_route.path.path_length
                trace_width = compiled_route.width_mm
                copper_area += trace_length * trace_width
        else:
            # --- RoutePath3D (multi-layer segments) ---
            # segments: list of (x, y, layer) tuples
            if not hasattr(compiled_route.path, "segments"):
                continue
            segments = compiled_route.path.segments
            for i in range(len(segments) - 1):
                x1, y1, seg_layer = segments[i]
                x2, y2, _ = segments[i + 1]
                if seg_layer == layer_name:
                    seg_length = math.hypot(x2 - x1, y2 - y1)
                    copper_area += seg_length * compiled_route.width_mm

        # ---------------------------------------------------------------
        # Via annular ring area (pad minus drill hole)
        # ---------------------------------------------------------------
        for via in compiled_route.vias:
            # --- Direct connections (from_layer / to_layer) ---
            if via.from_layer == layer_name or via.to_layer == layer_name:
                copper_area += _via_annular_area(via)

            # --- Intermediate layers (through-hole barrel) ---
            if layer_name != via.from_layer and layer_name != via.to_layer:
                if _layer_is_between(via.from_layer, via.to_layer, layer_name):
                    copper_area += _via_annular_area(via)

    return copper_area


def _via_annular_area(via: object) -> float:
    """
    Return the annular ring area of a via pad on one layer (mm²).

    Annular area = π ( (diameter/2)² - (drill/2)² )

    When *drill* is ``None`` or zero the hole term is omitted.
    """
    diameter = via.diameter
    drill = getattr(via, "drill", 0.0) or 0.0

    # Guard: NaN / inf diameter or drill → 0.0
    if (
        math.isnan(diameter)
        or math.isnan(drill)
        or math.isinf(diameter)
        or math.isinf(drill)
    ):
        return 0.0

    # Guard: non-positive diameter or drill >= diameter → 0.0
    if diameter <= 0.0 or drill >= diameter:
        return 0.0

    r_pad = diameter / 2.0
    r_hole = drill / 2.0 if drill > 0.0 else 0.0
    return math.pi * (r_pad * r_pad - r_hole * r_hole)


def _layer_is_between(from_layer: str, to_layer: str, candidate: str) -> bool:
    """
    Return ``True`` if *candidate* lies strictly between
    *from_layer* and *to_layer* in the standard 4-layer stack-up.
    """
    try:
        idx_from = _LAYER_ORDER_NAMES.index(from_layer)
        idx_to = _LAYER_ORDER_NAMES.index(to_layer)
        idx_candidate = _LAYER_ORDER_NAMES.index(candidate)
    except ValueError:
        return False
    lo = min(idx_from, idx_to)
    hi = max(idx_from, idx_to)
    return lo < idx_candidate < hi
