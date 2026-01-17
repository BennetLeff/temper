"""
Router V6 Stage 1.6: Reserve Via Positions in Grid

Marks escape via cells as BLOCKED in occupancy grid to prevent routing conflicts.
Part of temper-6wgs (Stage 1 - Pin Escape Planning)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReservedViaPosition:
    """A reserved position in the routing grid for an escape via."""

    position: tuple[float, float]  # (x, y) in mm
    via_diameter_mm: float
    via_drill_mm: float
    net_name: str
    layers: tuple[str, str]  # (start_layer, end_layer), e.g., ("L1", "L2")
    component_ref: str  # Reference of component this via escapes from

    @property
    def is_through_via(self) -> bool:
        """True if this is a through-hole via (all layers)."""
        # Through via typically goes L1 to Ln
        return self.layers[0] == "L1" and self.layers[1].startswith("L") and int(self.layers[1][1:]) >= 4

    @property
    def blocked_layers(self) -> list[str]:
        """Return list of layers this via blocks."""
        if self.is_through_via:
            # Through via blocks all layers
            # Assume L1-L4 for 4-layer board
            return ["L1", "L2", "L3", "L4"]
        else:
            # Blind/buried via blocks only relevant layers
            start_num = int(self.layers[0][1:])
            end_num = int(self.layers[1][1:])
            return [f"L{i}" for i in range(start_num, end_num + 1)]


def reserve_via_positions(
    escape_vias: list[tuple[tuple[float, float], float, float, str, str, tuple[str, str]]],
    grid_resolution_mm: float = 0.1,
) -> list[ReservedViaPosition]:
    """
    Reserve via positions in routing grid to prevent conflicts.

    Args:
        escape_vias: List of (position, diameter, drill, net_name, component_ref, layers) tuples
        grid_resolution_mm: Grid resolution for snapping (default 0.1mm)

    Returns:
        List of ReservedViaPosition instances with snapped positions.

    Example:
        >>> vias = [
        ...     ((5.0, 10.0), 0.35, 0.15, "USB_DP", "U1", ("L1", "L2")),
        ... ]
        >>> reserved = reserve_via_positions(vias)
        >>> len(reserved)
        1
    """
    reserved = []

    for position, diameter, drill, net_name, component_ref, layers in escape_vias:
        # Snap position to grid
        snapped_x = round(position[0] / grid_resolution_mm) * grid_resolution_mm
        snapped_y = round(position[1] / grid_resolution_mm) * grid_resolution_mm
        snapped_position = (snapped_x, snapped_y)

        reserved.append(
            ReservedViaPosition(
                position=snapped_position,
                via_diameter_mm=diameter,
                via_drill_mm=drill,
                net_name=net_name,
                layers=layers,
                component_ref=component_ref,
            )
        )

    return reserved


def check_via_conflicts(
    reserved_vias: list[ReservedViaPosition],
    min_via_spacing_mm: float = 0.3,
) -> list[tuple[ReservedViaPosition, ReservedViaPosition, float]]:
    """
    Check for conflicts between reserved via positions.

    Args:
        reserved_vias: List of ReservedViaPosition instances
        min_via_spacing_mm: Minimum allowed spacing between vias (default 0.3mm)

    Returns:
        List of (via1, via2, distance) tuples for conflicting via pairs.

    Example:
        >>> conflicts = check_via_conflicts(reserved)
        >>> len(conflicts)
        0  # No conflicts
    """
    conflicts = []

    for i, via1 in enumerate(reserved_vias):
        for via2 in reserved_vias[i + 1:]:
            # Calculate distance
            dx = via2.position[0] - via1.position[0]
            dy = via2.position[1] - via1.position[1]
            distance = (dx**2 + dy**2)**0.5

            # Check if vias are on overlapping layers
            layers1 = set(via1.blocked_layers)
            layers2 = set(via2.blocked_layers)

            if layers1.intersection(layers2) and distance < min_via_spacing_mm:
                conflicts.append((via1, via2, distance))

    return conflicts
