"""
Deterministic template-based component placement.

This module provides rule-based placement strategies that guarantee
overlap-free, zone-compliant layouts without gradient optimization.

Wave 4, **Phase 4** (placer non-`cp_sat` slice): the per-component
placement compute of ``place_power_stage_template`` (template application
at the zone center + the mapping loop into the float32 arrays),
``place_by_proximity`` (the #763-fixed spiral loop) and
``place_in_zone_center`` (the grid distribution loop) is implemented in
Rust in the ``temper-io-types/placer_core`` crate (``temper_io_types.
placer_place_power_stage_template`` / ``placer_place_by_proximity`` /
``placer_place_in_zone_center``). ``PlacementResult`` stays a Python
dataclass; the zone lookup, ``board.zones``/``netlist.components``
navigation and the numpy assembly stay here (object navigation /
marshalling). The ``math.cos``/``math.sin`` spiral transcendental is a
Python seam (``(cos, sin)`` callable) so the oracle's libm bits are
preserved by construction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

import numpy as np
import temper_io_types as _t

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

from numpy.typing import NDArray

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.template import ComponentTemplate


def _cos_sin(theta: float) -> tuple[float, float]:
    """Python seam: ``math.cos``/``math.sin`` of the spiral angle."""
    return (math.cos(theta), math.sin(theta))


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

    # The kernel applies the template at the zone center and maps the
    # placements onto the component arrays. Anchor resolution mirrors the
    # template's own apply() contract (raise when the anchor is missing).
    anchor = template.get_anchor_position()
    if anchor is None:
        raise ValueError(f"Anchor point {template.anchor_point} not found in template")
    anchor_idx = next(
        i for i, comp in enumerate(template.components) if comp.ref == template.anchor_point
    )

    # Oracle's np.array(initial_positions, dtype=np.float32) cast happens
    # here; the kernel receives the float32 values widened to f64.
    initial = None
    if initial_positions is not None:
        initial = (
            np.asarray(initial_positions, dtype=np.float32).reshape(-1).astype(np.float64).tolist()
        )

    flat, rotations_flat, placed_refs, unplaced_refs = _t.placer_place_power_stage_template(
        [comp.ref for comp in netlist.components],
        [c.ref for c in template.components],
        [c.x for c in template.components],
        [c.y for c in template.components],
        [c.rotation for c in template.components],
        anchor_idx,
        zone_center_x,
        zone_center_y,
        0,
        initial,
        _cos_sin,
    )

    n = len(netlist.components)
    positions = np.asarray(flat, dtype=np.float32).reshape((n, 2))
    rotations = np.asarray(rotations_flat, dtype=np.float32)

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
    # `max_distance` is the oracle's dead parameter: its `if distance >
    # max_distance: pass` branch is a literal no-op, pinned invariant by the
    # differential (`test_place_by_proximity_no_zone` parametrized over it).
    # Kept for API compatibility.
    _ = max_distance

    # Find target component
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    if target_ref not in ref_to_idx:
        raise ValueError(f"Target component '{target_ref}' not found")

    # Get zone if specified
    zone = None
    if zone_name:
        for z in board.zones:
            if z.name == zone_name:
                zone = z
                break

    # Spiral placement around target: base position from the zone center if
    # a zone is given, else the board center. (The #763 fix: the spiral loop
    # itself runs at function level regardless of zone_name.)
    if zone:
        base_x = (zone.bounds[0] + zone.bounds[2]) / 2
        base_y = (zone.bounds[1] + zone.bounds[3]) / 2
    else:
        base_x = board.width / 2
        base_y = board.height / 2

    refs = list(refs_to_place)
    indices = [ref_to_idx.get(r) for r in refs]
    zone_bounds = None if zone is None else tuple(zone.bounds)

    n = netlist.n_components
    flat, placed_refs, unplaced_refs = _t.placer_place_by_proximity(
        n,
        refs,
        indices,
        base_x,
        base_y,
        zone_bounds,
        _cos_sin,
    )

    positions = np.asarray(flat, dtype=np.float32).reshape((n, 2))
    rotations = np.zeros(n, dtype=np.float32)

    return PlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=placed_refs,
        unplaced_refs=unplaced_refs,
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

    refs = list(refs_to_place)
    indices = [ref_to_idx.get(r) for r in refs]

    n = netlist.n_components
    flat, placed_refs, unplaced_refs = _t.placer_place_in_zone_center(
        n,
        refs,
        indices,
        center_x,
        center_y,
        tuple(zone.bounds),
    )

    positions = np.asarray(flat, dtype=np.float32).reshape((n, 2))
    rotations = np.zeros(n, dtype=np.float32)

    return PlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=placed_refs,
        unplaced_refs=unplaced_refs,
    )
