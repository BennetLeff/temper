"""
Router V6 Stage 4.3: Place Vias

Places vias for layer transitions in routed paths.
Part of temper-zh0p (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.stage0_data import DesignRules


@dataclass
class Via:
    """A via for layer transition."""

    position: tuple[float, float]  # (x, y) in mm
    from_layer: str
    to_layer: str
    diameter: float  # Via diameter in mm
    drill: float  # Drill diameter in mm
    net_name: str


@dataclass
class ViaPlacement:
    """Collection of placed vias."""

    vias: list[Via]

    @property
    def via_count(self) -> int:
        """Total number of vias."""
        return len(self.vias)

    def get_vias_for_net(self, net_name: str) -> list[Via]:
        """Get all vias for a specific net."""
        return [v for v in self.vias if v.net_name == net_name]


def place_vias(
    pathfinding_result: PathfindingResult,
    via_diameter: float = 0.6,  # Standard via
    via_drill: float = 0.3,
    design_rules: DesignRules | None = None,
) -> ViaPlacement:
    """
    Place vias for layer transitions in routed paths.

    Analyzes routed paths and inserts vias where layer changes occur.

    Args:
        pathfinding_result: Routed paths from Stage 4.2
        via_diameter: Default via diameter (mm)
        via_drill: Default drill diameter (mm)
        design_rules: Per-netclass routing rules. When supplied, each net's
            resolved via dimensions override the board-wide defaults.

    Returns:
        ViaPlacement with all placed vias

    Example:
        >>> from temper_placer.router_v6.astar_pathfinding import PathfindingResult
        >>> result = PathfindingResult(routed_paths={}, failed_nets=[])
        >>> placement = place_vias(result)
        >>> placement.via_count >= 0
        True
    """
    vias = []

    for net_name, route_path in pathfinding_result.routed_paths.items():
        if design_rules is not None:
            net_rules = design_rules.get_rules_for_net(net_name)
            net_via_diameter = net_rules.via_diameter_mm
            net_via_drill = net_rules.via_drill_mm
        else:
            net_via_diameter = via_diameter
            net_via_drill = via_drill

        # Analyze path for layer transitions
        net_vias = _place_vias_for_path(
            net_name,
            route_path,
            net_via_diameter,
            net_via_drill,
        )
        vias.extend(net_vias)

    return ViaPlacement(vias=vias)


def _place_vias_for_path(
    net_name: str,
    route_path,
    via_diameter: float,
    via_drill: float,
) -> list[Via]:
    """
    Place vias for a single routed path.

    Args:
        net_name: Net name
        route_path: RoutePath from pathfinding
        via_diameter: Via diameter
        via_drill: Drill diameter

    Returns:
        List of vias for this path
    """
    vias = []

    # If RoutePath3D, use explicit via_positions from pathfinder
    if hasattr(route_path, "via_positions"):
        consumed_transition_indices: set[int] = set()
        for vx, vy in route_path.via_positions:
            from_layer, to_layer = _transition_layers_at(
                route_path.segments, vx, vy, consumed_transition_indices
            )
            vias.append(
                Via(
                    position=(vx, vy),
                    from_layer=from_layer,
                    to_layer=to_layer,
                    diameter=via_diameter,
                    drill=via_drill,
                    net_name=net_name,
                )
            )
        return vias

    # Legacy fallback for RoutePath
    if hasattr(route_path, "coordinates") and len(route_path.coordinates) >= 3:
        # Add a via at the midpoint for demonstration
        mid_idx = len(route_path.coordinates) // 2
        via_pos = route_path.coordinates[mid_idx]

        # Determine layers (simplified)
        from_layer = route_path.layer_name
        to_layer = _get_adjacent_layer(from_layer)

        if to_layer:
            via = Via(
                position=via_pos,
                from_layer=from_layer,
                to_layer=to_layer,
                diameter=via_diameter,
                drill=via_drill,
                net_name=net_name,
            )
            vias.append(via)

    return vias


def _transition_layers_at(
    segments: list[tuple[float, float, str]],
    vx: float,
    vy: float,
    consumed_transition_indices: set[int],
) -> tuple[str, str]:
    """Return the ordered layers of the explicit transition at ``(vx, vy)``.

    A :class:`RoutePath3D` represents a via as two consecutive points at the
    same coordinate, one on each copper layer.  ``via_positions`` names that
    coordinate; it is not enough to assume an outer-layer span because 3D A*
    can legitimately transition between any adjacent layers in a stackup.
    """
    for index, (previous, current) in enumerate(zip(segments, segments[1:])):
        px, py, previous_layer = previous
        cx, cy, current_layer = current
        if (
            index not in consumed_transition_indices
            and previous_layer != current_layer
            and _same_position(px, py, vx, vy)
            and _same_position(cx, cy, vx, vy)
        ):
            consumed_transition_indices.add(index)
            return previous_layer, current_layer

    raise ValueError(f"RoutePath3D via position does not identify a layer transition: ({vx}, {vy})")


def _same_position(x1: float, y1: float, x2: float, y2: float) -> bool:
    """Compare world coordinates without losing exact grid-transition intent."""
    return math.isclose(x1, x2, abs_tol=1e-9) and math.isclose(y1, y2, abs_tol=1e-9)


def _get_adjacent_layer(layer_name: str) -> str | None:
    """
    Get adjacent layer for via transition.

    Args:
        layer_name: Current layer (e.g., "F.Cu")

    Returns:
        Adjacent layer name or None
    """
    # Simplified layer mapping
    layer_map = {
        "F.Cu": "In1.Cu",
        "In1.Cu": "In2.Cu",
        "In2.Cu": "B.Cu",
        "B.Cu": "In2.Cu",
    }

    return layer_map.get(layer_name)
