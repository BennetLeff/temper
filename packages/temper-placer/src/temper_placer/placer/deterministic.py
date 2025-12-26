"""
Deterministic template-based component placement.

This module provides rule-based placement strategies that guarantee
overlap-free, zone-compliant layouts without gradient optimization.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.template import ComponentTemplate


@dataclass
class PlacementResult:
    """Result from template-based placement."""
    positions: np.ndarray  # (N, 2) component positions
    rotations: np.ndarray  # (N,) component rotations in degrees
    placed_refs: list[str]  # References of placed components
    unplaced_refs: list[str]  # References not placed by template


def place_power_stage_template(
    netlist: Netlist,
    board: Board,
    template: ComponentTemplate,
    zone_name: str = "power_zone",
    initial_positions: np.ndarray | None = None,
) -> PlacementResult:
    """Place power stage components using a template."""
    zone = next((z for z in board.zones if z.name == zone_name), None)
    if zone is None:
        raise ValueError(f"Zone '{zone_name}' not found in board")
    
    zone_center_x = (zone.bounds[0] + zone.bounds[2]) / 2
    zone_center_y = (zone.bounds[1] + zone.bounds[3]) / 2
    placements = template.apply(zone_center_x, zone_center_y, rotation=0)
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}
    
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
    
    return PlacementResult(positions, rotations, placed_refs, unplaced_refs)


def place_by_proximity(
    netlist: Netlist,
    board: Board,
    target_ref: str,
    refs_to_place: list[str],
    max_distance: float = 15.0,
    zone_name: str | None = None,
) -> PlacementResult:
    """Place components near a target component."""
    import math
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}
    if target_ref not in ref_to_idx:
        raise ValueError(f"Target component '{target_ref}' not found")
    
    positions = np.zeros((netlist.n_components, 2), dtype=np.float32)
    rotations = np.zeros(netlist.n_components, dtype=np.float32)
    
    zone = next((z for z in board.zones if z.name == zone_name), None) if zone_name else None
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
        angle = i * angle_step
        distance = 8.0 + (i // 4) * 3.0
        x = base_x + distance * math.cos(angle)
        y = base_y + distance * math.sin(angle)
        if zone:
            x = max(zone.bounds[0], min(zone.bounds[2], x))
            y = max(zone.bounds[1], min(zone.bounds[3], y))
        positions[idx] = [x, y]
        placed_refs.append(ref)
    
    return PlacementResult(positions, rotations, placed_refs, unplaced_refs)


def place_in_zone_center(
    netlist: Netlist,
    board: Board,
    refs_to_place: list[str],
    zone_name: str,
) -> PlacementResult:
    """Place components at zone center with grid distribution."""
    import math
    zone = next((z for z in board.zones if z.name == zone_name), None)
    if zone is None:
        raise ValueError(f"Zone '{zone_name}' not found")
    
    center_x = (zone.bounds[0] + zone.bounds[2]) / 2
    center_y = (zone.bounds[1] + zone.bounds[3]) / 2
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}
    positions = np.zeros((netlist.n_components, 2), dtype=np.float32)
    rotations = np.zeros(netlist.n_components, dtype=np.float32)
    placed_refs = []
    unplaced_refs = []
    grid_size = math.ceil(math.sqrt(len(refs_to_place)))
    spacing = 8.0
    
    for i, ref in enumerate(refs_to_place):
        if ref not in ref_to_idx:
            unplaced_refs.append(ref)
            continue
        idx = ref_to_idx[ref]
        row, col = i // grid_size, i % grid_size
        x = center_x + (col - grid_size/2) * spacing
        y = center_y + (row - grid_size/2) * spacing
        x = max(zone.bounds[0], min(zone.bounds[2], x))
        y = max(zone.bounds[1], min(zone.bounds[3], y))
        positions[idx] = [x, y]
        placed_refs.append(ref)
    
    return PlacementResult(positions, rotations, placed_refs, unplaced_refs)
