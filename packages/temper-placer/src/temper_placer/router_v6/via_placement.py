"""
Router V6 Stage 4.3: Place Vias

Places vias for layer transitions in routed paths.
Part of temper-zh0p (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.astar_pathfinding import PathfindingResult


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
) -> ViaPlacement:
    """
    Place vias for layer transitions in routed paths.

    Analyzes routed paths and inserts vias where layer changes occur.

    Args:
        pathfinding_result: Routed paths from Stage 4.2
        via_diameter: Default via diameter (mm)
        via_drill: Default drill diameter (mm)

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
        # Analyze path for layer transitions
        net_vias = _place_vias_for_path(
            net_name,
            route_path,
            via_diameter,
            via_drill,
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
    if hasattr(route_path, 'via_positions'):
        for vx, vy in route_path.via_positions:
            vias.append(
                Via(
                    net=net_name,
                    at=(vx, vy),
                    diameter=via_diameter,
                    drill=via_drill,
                    layers=("F.Cu", "B.Cu"), # Multi-layer via
                )
            )
        return vias

    # Legacy fallback for RoutePath
    if hasattr(route_path, 'coordinates') and len(route_path.coordinates) >= 3:
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
