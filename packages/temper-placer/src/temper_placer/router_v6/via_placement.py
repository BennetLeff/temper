"""
Router V6 Stage 4.3: Place Vias

Places vias for layer transitions in routed paths.
Part of temper-zh0p (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    via_diameter: float = 0.6,
    via_drill: float = 0.3,
    net_class_assignments: dict[str, str] | None = None,
    net_class_rules: dict | None = None,
    design_rules: Any = None,
) -> ViaPlacement:
    """
    Place vias for layer transitions in routed paths.

    When *design_rules* is provided (U4 pipeline wiring), per-netclass
    sizing is resolved from the board's netclass assignments and rules.
    """
    if design_rules is not None:
        net_class_assignments = getattr(design_rules, 'net_class_assignments', None)
        net_class_rules = getattr(design_rules, 'net_classes', None)
    vias = []

    for net_name, route_path in pathfinding_result.routed_paths.items():
        dia, drill = via_diameter, via_drill
        if net_class_assignments and net_class_rules:
            nc_name = net_class_assignments.get(net_name)
            if nc_name:
                rules = net_class_rules.get(nc_name, {})
                dia = getattr(rules, "via_diameter_mm", via_diameter)
                drill = getattr(rules, "via_drill_mm", via_drill)
        vias.extend(
            _place_vias_for_path(net_name, route_path, dia, drill)
        )
    for net_name, geometry in getattr(pathfinding_result, "tree_routes", {}).items():
        dia, drill = via_diameter, via_drill
        if net_class_assignments and net_class_rules:
            nc_name = net_class_assignments.get(net_name)
            if nc_name:
                rules = net_class_rules.get(nc_name, {})
                dia = getattr(rules, "via_diameter_mm", via_diameter)
                drill = getattr(rules, "via_drill_mm", via_drill)
        for branch in geometry.branches:
            vias.extend(
                _place_vias_for_path(net_name, branch.path, dia, drill)
            )

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

    # If RoutePath3D, use explicit via_positions from pathfinder.
    # U3: derive from_layer/to_layer from the actual segment layers on
    # either side of each transition, not the hardcoded F.Cu/B.Cu pair.
    if hasattr(route_path, "via_positions") and hasattr(route_path, "segments"):
        segs = route_path.segments
        for vx, vy in route_path.via_positions:
            vi = None
            for i, (sx, sy, _) in enumerate(segs):
                if abs(sx - vx) < 1e-4 and abs(sy - vy) < 1e-4:
                    vi = i
                    break
            if vi is not None and vi + 1 < len(segs):
                from_layer = segs[vi][2]
                to_layer = segs[vi + 1][2]
            else:
                from_layer = "F.Cu"
                to_layer = "B.Cu"
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
