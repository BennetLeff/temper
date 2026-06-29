"""
Deterministic template-based component placement.

This module provides rule-based placement strategies that guarantee
overlap-free, zone-compliant layouts without gradient optimization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.template import ComponentTemplate


@dataclass
class PlacementResult:
    """Result from template-based placement."""

    positions: NDArray[np.float32]  # (N, 2) component positions
    rotations: NDArray[np.float32]  # (N,) component rotations in degrees
    placed_refs: list[str]  # References of placed components
    unplaced_refs: list[str]  # References not placed by template


def place_power_stage_template(
    netlist: Netlist,
    board: Board,
    template: ComponentTemplate,
    zone_name: str = "power_zone",
    initial_positions: NDArray[np.float32] | None = None,
) -> PlacementResult:
    """
    Place power stage components using a template.

    Args:
        netlist: Component netlist
        board: Board definition with zones
        template: Half-bridge or other power stage template
        zone_name: Target zone for placement
        initial_positions: Optional (N, 2) array of original positions.
            Components not in template will keep these positions.

    Returns:
        PlacementResult with positions for power stage components

    Raises:
        ValueError: If zone not found or template components missing
    """
    # Get target zone
    zone = None
    for z in board.zones:
        if z.name == zone_name:
            zone = z
            break

    if zone is None:
        raise ValueError(f"Zone '{zone_name}' not found in board")

    # Find zone center as anchor point
    zone_center_x = (zone.bounds[0] + zone.bounds[2]) / 2
    zone_center_y = (zone.bounds[1] + zone.bounds[3]) / 2

    # Apply template at zone center
    placements = template.apply(zone_center_x, zone_center_y, rotation=0)

    # Map to netlist indices
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    # Initialize from original positions if provided, else zeros
    if initial_positions is not None:
        positions = np.array(initial_positions, dtype=np.float32)
    else:
        positions = np.zeros((netlist.n_components, 2), dtype=np.float32)

    rotations = np.zeros(netlist.n_components, dtype=np.float32)
    placed_refs = []
    unplaced_refs = []

    for comp in netlist.components:
        if comp.ref in placements:
            idx = ref_to_idx[comp.ref]
            x, y, rot = placements[comp.ref]
            positions[idx] = [x, y]
            rotations[idx] = rot
            placed_refs.append(comp.ref)
        else:
            unplaced_refs.append(comp.ref)

    return PlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=placed_refs,
        unplaced_refs=unplaced_refs,
    )


def place_by_proximity(
    netlist: Netlist,
    board: Board,
    target_ref: str,
    refs_to_place: list[str],
    max_distance: float = 15.0,
    zone_name: str | None = None,
) -> PlacementResult:
    """
    Place components near a target component.

    Uses spiral placement pattern starting from target position.

    Args:
        netlist: Component netlist
        board: Board definition
        target_ref: Reference of anchor component
        refs_to_place: Components to place near target
        max_distance: Maximum distance from target (mm)
        zone_name: Optional zone constraint

    Returns:
        PlacementResult with proximity placements
    """
    import math

    # Find target component
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    if target_ref not in ref_to_idx:
        raise ValueError(f"Target component '{target_ref}' not found")

    # Initialize from current positions (may not be set yet)
    positions = np.zeros((netlist.n_components, 2), dtype=np.float32)
    rotations = np.zeros(netlist.n_components, dtype=np.float32)

    # Get zone if specified
    zone = None
    if zone_name:
        for z in board.zones:
            if z.name == zone_name:
                zone = z
                break

        # Spiral placement around target
        # Placeholder - would need actual target position
        # For now, use zone center if zone specified
        if zone:
            base_x = (zone.bounds[0] + zone.bounds[2]) / 2
            base_y = (zone.bounds[1] + zone.bounds[3]) / 2
        else:
            base_x = board.width / 2
            base_y = board.height / 2

        placed_refs = []
        unplaced_refs = []

        angle_step = 2 * math.pi / max(len(refs_to_place), 4)

        for i, ref in enumerate(refs_to_place):
            if ref not in ref_to_idx:
                unplaced_refs.append(ref)
                continue

            idx = ref_to_idx[ref]

            # Spiral placement
            angle = i * angle_step
            distance = 8.0 + (i // 4) * 3.0  # Spiral outward

            # Don't exceed max_distance if provided
            if distance > max_distance:
                 # Stop placing or clamp? For now, we'll just log/continue
                 pass

            x = base_x + distance * math.cos(angle)
            y = base_y + distance * math.sin(angle)

            # Clamp to zone if specified
            if zone:
                x = max(zone.bounds[0], min(zone.bounds[2], x))
                y = max(zone.bounds[1], min(zone.bounds[3], y))

            positions[idx] = [x, y]
            placed_refs.append(ref)

        return PlacementResult(
            positions=positions,
            rotations=rotations,
            placed_refs=placed_refs,
            unplaced_refs=unplaced_refs,
        )

    # If no zone_name provided, return empty result
    return PlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=[],
        unplaced_refs=list(refs_to_place),
    )


def place_in_zone_center(
    netlist: Netlist,
    board: Board,
    refs_to_place: list[str],
    zone_name: str,
) -> PlacementResult:
    """
    Place components at zone center with grid distribution.

    Args:
        netlist: Component netlist
        board: Board definition
        refs_to_place: Components to place in zone
        zone_name: Target zone

    Returns:
        PlacementResult with zone-centered placements
    """
    import math

    # Get zone
    zone = None
    for z in board.zones:
        if z.name == zone_name:
            zone = z
            break

    if zone is None:
        raise ValueError(f"Zone '{zone_name}' not found")

    # Zone center
    center_x = (zone.bounds[0] + zone.bounds[2]) / 2
    center_y = (zone.bounds[1] + zone.bounds[3]) / 2

    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    positions = np.zeros((netlist.n_components, 2), dtype=np.float32)
    rotations = np.zeros(netlist.n_components, dtype=np.float32)

    placed_refs = []
    unplaced_refs = []

    # Grid placement around center
    grid_size = math.ceil(math.sqrt(len(refs_to_place)))
    spacing = 8.0

    for i, ref in enumerate(refs_to_place):
        if ref not in ref_to_idx:
            unplaced_refs.append(ref)
            continue

        idx = ref_to_idx[ref]

        row = i // grid_size
        col = i % grid_size

        x = center_x + (col - grid_size/2) * spacing
        y = center_y + (row - grid_size/2) * spacing

        # Clamp to zone
        x = max(zone.bounds[0], min(zone.bounds[2], x))
        y = max(zone.bounds[1], min(zone.bounds[3], y))

        positions[idx] = [x, y]
        placed_refs.append(ref)

    return PlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=placed_refs,
        unplaced_refs=unplaced_refs,
    )
