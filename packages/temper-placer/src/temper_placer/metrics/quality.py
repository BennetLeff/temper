"""
Quality metrics suite for placement comparison.

This module provides metrics to evaluate and compare placement quality
for different placements (optimized, hand-placed, random baseline).

All metrics are normalized to [0, 1] range for easy comparison:
- Higher score = better placement quality
- 1.0 = perfect/ideal
- 0.0 = worst case

The exception is total_wirelength which returns raw mm value (lower is better).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.losses.wirelength import WirelengthLoss


def total_wirelength(
    state: PlacementState,
    netlist: Netlist,
    context: LossContext,
    alpha: float = 10.0,
) -> float:
    """
    Compute total Half-Perimeter Wire Length (HPWL) for a placement.

    Lower is better - represents total estimated wire length in mm.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        context: Pre-computed loss context.
        alpha: LogSumExp smoothing parameter.

    Returns:
        Total HPWL in mm (lower is better).
    """
    if context.net_pin_indices.shape[0] == 0:
        return 0.0

    # Convert rotation logits to soft one-hot using softmax (no sampling for determinism)
    rotations = jax.nn.softmax(state.rotation_logits)

    loss = WirelengthLoss(alpha=alpha)
    result = loss(state.positions, rotations, context)
    return float(result.value)


def thermal_score(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    thermal_components: Set[str],
    target_edge: str = "TOP",
    max_distance: float = 10.0,
) -> float:
    """
    Score thermal component placement (0-1, higher is better).

    Measures how well thermal components (e.g., IGBTs) are placed near
    board edges for heatsink mounting.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition.
        thermal_components: Set of component refs that need edge placement.
        target_edge: Board edge for thermal components ("TOP", "BOTTOM", "LEFT", "RIGHT").
        max_distance: Maximum acceptable distance from edge in mm.

    Returns:
        Score in [0, 1] where 1.0 = all thermal components at edge,
        0.0 = all at maximum distance from edge.
    """
    if not thermal_components:
        return 1.0  # Perfect score if nothing to optimize

    board_bounds = board.get_bounds_array()
    x_min, y_min, x_max, y_max = board_bounds

    total_score = 0.0
    count = 0

    for ref in thermal_components:
        try:
            idx = netlist.get_component_index(ref)
        except KeyError:
            continue

        pos = state.positions[idx]
        x, y = float(pos[0]), float(pos[1])

        # Distance to target edge
        if target_edge == "TOP":
            distance = float(y_max) - y
        elif target_edge == "BOTTOM":
            distance = y - float(y_min)
        elif target_edge == "LEFT":
            distance = x - float(x_min)
        elif target_edge == "RIGHT":
            distance = float(x_max) - x
        else:
            distance = max_distance  # Unknown edge

        # Normalize: 0 distance = 1.0 score, max_distance = 0.0 score
        component_score = max(0.0, 1.0 - distance / max_distance)
        total_score += component_score
        count += 1

    return total_score / count if count > 0 else 1.0


def zone_compliance_score(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    zone_assignments: Dict[str, str],
) -> float:
    """
    Score zone membership compliance (0-1, higher is better).

    Measures fraction of components that are placed within their
    designated zones.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition with zones.
        zone_assignments: Dict mapping component_ref -> zone_name.

    Returns:
        Score in [0, 1] where 1.0 = all assigned components in correct zones.
    """
    if not zone_assignments or not board.zones:
        return 1.0  # Perfect score if nothing to check

    # Build zone lookup
    zone_lookup = {z.name: z for z in board.zones}

    correct = 0
    total = 0

    for ref, zone_name in zone_assignments.items():
        if zone_name not in zone_lookup:
            continue

        try:
            idx = netlist.get_component_index(ref)
        except KeyError:
            continue

        zone = zone_lookup[zone_name]
        pos = state.positions[idx]
        x, y = float(pos[0]), float(pos[1])

        # Check if position is within zone bounds
        x_min, y_min, x_max, y_max = zone.bounds
        in_zone = x_min <= x <= x_max and y_min <= y <= y_max

        if in_zone:
            correct += 1
        total += 1

    return correct / total if total > 0 else 1.0


def hv_lv_clearance_score(
    state: PlacementState,
    netlist: Netlist,
    hv_components: Set[str],
    lv_components: Set[str],
    min_clearance: float = 8.0,
) -> float:
    """
    Score HV-LV clearance compliance (0-1, higher is better).

    Measures whether HV and LV components maintain minimum clearance.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        hv_components: Set of high-voltage component refs.
        lv_components: Set of low-voltage component refs.
        min_clearance: Required minimum clearance in mm.

    Returns:
        Score in [0, 1] where 1.0 = all clearances satisfied,
        0.0 = severe violations.
    """
    if not hv_components or not lv_components:
        return 1.0  # Perfect score if nothing to check

    # Get positions for HV and LV components
    hv_positions = []
    hv_bounds = []
    for ref in hv_components:
        try:
            idx = netlist.get_component_index(ref)
            hv_positions.append(state.positions[idx])
            hv_bounds.append(netlist.components[idx].bounds)
        except KeyError:
            continue

    lv_positions = []
    lv_bounds = []
    for ref in lv_components:
        try:
            idx = netlist.get_component_index(ref)
            lv_positions.append(state.positions[idx])
            lv_bounds.append(netlist.components[idx].bounds)
        except KeyError:
            continue

    if not hv_positions or not lv_positions:
        return 1.0

    # Compute minimum clearance across all HV-LV pairs
    min_found_clearance = float("inf")

    for i, hv_pos in enumerate(hv_positions):
        hv_hw, hv_hh = hv_bounds[i][0] / 2, hv_bounds[i][1] / 2

        for j, lv_pos in enumerate(lv_positions):
            lv_hw, lv_hh = lv_bounds[j][0] / 2, lv_bounds[j][1] / 2

            # Compute edge-to-edge distance (axis-aligned approximation)
            dx = abs(float(hv_pos[0]) - float(lv_pos[0])) - hv_hw - lv_hw
            dy = abs(float(hv_pos[1]) - float(lv_pos[1])) - hv_hh - lv_hh

            if dx > 0 and dy > 0:
                # Corner separation
                clearance = (dx**2 + dy**2) ** 0.5
            else:
                # Edge separation or overlap
                clearance = max(dx, dy)

            min_found_clearance = min(min_found_clearance, clearance)

    # Score: 1.0 if clearance >= min_clearance, 0.0 if clearance <= 0
    if min_found_clearance >= min_clearance:
        return 1.0
    elif min_found_clearance <= 0:
        return 0.0
    else:
        return min_found_clearance / min_clearance


def loop_area_score(
    state: PlacementState,
    netlist: Netlist,
    context: LossContext,
    loop_components: List[List[str]],
    max_area: float = 100.0,
) -> float:
    """
    Score critical loop area minimization (0-1, higher is better).

    Measures how small critical current loops are. Smaller loops = better EMI.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        context: Pre-computed loss context.
        loop_components: List of loops, each loop is list of component refs.
            Components should be listed in order around the loop perimeter.
        max_area: Maximum acceptable loop area in mm² (areas above this = 0 score).

    Returns:
        Score in [0, 1] where 1.0 = minimal loop areas, 0.0 = large loops.
    """
    if not loop_components:
        return 1.0  # Perfect if nothing to check

    total_score = 0.0
    count = 0

    for loop_refs in loop_components:
        if len(loop_refs) < 3:
            continue  # Need at least 3 points for a polygon

        # Get positions for components in this loop
        positions = []
        for ref in loop_refs:
            try:
                idx = netlist.get_component_index(ref)
                positions.append(state.positions[idx])
            except KeyError:
                continue

        if len(positions) < 3:
            continue

        # Compute polygon area using shoelace formula
        vertices = jnp.array([[float(p[0]), float(p[1])] for p in positions])
        vertices_next = jnp.roll(vertices, -1, axis=0)
        cross = vertices[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * vertices[:, 1]
        area = abs(float(jnp.sum(cross)) / 2.0)

        # Score: 1.0 for zero area, 0.0 for max_area or larger
        loop_score = max(0.0, 1.0 - area / max_area)
        total_score += loop_score
        count += 1

    return total_score / count if count > 0 else 1.0


def congestion_score(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    context: LossContext,
    grid_shape: tuple[int, int] = (10, 10),
    capacity_per_cell: float = 10.0,
) -> float:
    """
    Score routing congestion (0-1, higher is better = less congestion).

    Estimates routing demand across a grid and penalizes hotspots.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition.
        context: Pre-computed loss context.
        grid_shape: (rows, cols) for congestion grid.
        capacity_per_cell: Maximum demand per cell before congestion.

    Returns:
        Score in [0, 1] where 1.0 = evenly distributed demand,
        0.0 = severe congestion hotspots.
    """
    from temper_placer.losses.congestion import compute_routing_demand

    board_bounds = board.get_bounds_array()
    demand = compute_routing_demand(state.positions, context, grid_shape, board_bounds)

    # Compute overflow ratio
    overflow = jnp.maximum(0.0, demand - capacity_per_cell)
    total_overflow = float(jnp.sum(overflow))
    total_demand = float(jnp.sum(demand))

    if total_demand <= 0:
        return 1.0  # No demand = no congestion

    # Score based on overflow ratio
    # 0 overflow = 1.0 score, high overflow = low score
    overflow_ratio = total_overflow / total_demand
    return max(0.0, 1.0 - overflow_ratio)


def compactness_score(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
) -> float:
    """
    Score placement compactness (0-1, higher is better).

    Measures how efficiently components use the board area.
    Compact placements leave more room for routing and future additions.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition.

    Returns:
        Score in [0, 1] where 1.0 = tightly packed, 0.0 = spread across board.
    """
    if netlist.n_components < 2:
        return 1.0  # Single component is always compact

    positions = state.positions

    # Compute bounding box of all placed components
    x_coords = positions[:, 0]
    y_coords = positions[:, 1]

    x_min, x_max = float(jnp.min(x_coords)), float(jnp.max(x_coords))
    y_min, y_max = float(jnp.min(y_coords)), float(jnp.max(y_coords))

    # Add component sizes to get actual bounding box
    half_widths = jnp.array([c.bounds[0] / 2 for c in netlist.components])
    half_heights = jnp.array([c.bounds[1] / 2 for c in netlist.components])

    placement_width = (x_max - x_min) + float(jnp.max(half_widths)) * 2
    placement_height = (y_max - y_min) + float(jnp.max(half_heights)) * 2

    # Compute total component area
    total_component_area = sum(c.bounds[0] * c.bounds[1] for c in netlist.components)

    # Placement bounding box area
    placement_area = placement_width * placement_height

    if placement_area <= 0:
        return 1.0

    # Score based on utilization (component area / placement bbox area)
    # Higher utilization = more compact
    utilization = total_component_area / placement_area

    # Clamp to [0, 1] - utilization > 1 is impossible in practice
    # but can happen with overlaps
    return min(1.0, utilization)


def connectivity_clustering_score(
    state: PlacementState,
    netlist: Netlist,
    context: LossContext,
) -> float:
    """
    Score connectivity clustering (0-1, higher is better).

    Measures how well-clustered connected components are. For each net,
    computes the ratio of actual pin bounding box area to the minimum
    possible area (sum of component areas on that net).

    Args:
        state: Current placement state.
        netlist: Design netlist.
        context: Pre-computed loss context.

    Returns:
        Score in [0, 1] where 1.0 = perfectly clustered, 0.0 = spread out.
    """
    if not netlist.nets:
        return 1.0

    positions = state.positions
    total_score = 0.0
    count = 0

    # We use the pre-computed net pin indices from context for efficiency
    # net_pin_indices: (M, P)
    # net_pin_mask: (M, P)
    for i in range(context.net_pin_indices.shape[0]):
        indices = context.net_pin_indices[i]
        mask = context.net_pin_mask[i]
        
        # Filter valid pins
        valid_indices = indices[mask]
        if len(valid_indices) < 2:
            continue
            
        # Get positions of components in this net
        net_comp_positions = positions[valid_indices]
        
        # Compute actual bounding box of component centers
        x_min = jnp.min(net_comp_positions[:, 0])
        x_max = jnp.max(net_comp_positions[:, 0])
        y_min = jnp.min(net_comp_positions[:, 1])
        y_max = jnp.max(net_comp_positions[:, 1])
        
        # Add half-widths/heights to get component-aware bounding box
        net_components = [netlist.components[idx] for idx in valid_indices.tolist()]
        max_hw = max(c.width / 2 for c in net_components)
        max_hh = max(c.height / 2 for c in net_components)
        
        bbox_width = (x_max - x_min) + 2 * max_hw
        bbox_height = (y_max - y_min) + 2 * max_hh
        actual_area = bbox_width * bbox_height
        
        # Compute minimum possible area (sum of component areas)
        min_possible_area = sum(c.width * c.height for c in net_components)
        
        # Clustering ratio: min_area / actual_area (1.0 = optimal)
        # We take max(min_possible_area, actual_area) to avoid > 1.0 due to overlaps
        if actual_area > 0:
            ratio = min_possible_area / max(actual_area, min_possible_area)
            total_score += float(ratio)
            count += 1

    return total_score / count if count > 0 else 1.0


def compute_quality_report(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    context: LossContext,
    config: Dict[str, Any],
) -> Dict[str, float]:
    """
    Compute comprehensive quality report with all metrics.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition.
        context: Pre-computed loss context.
        config: Configuration dict with:
            - thermal_components: Set[str] - refs of thermal components
            - hv_components: Set[str] - refs of HV components
            - lv_components: Set[str] - refs of LV components
            - zone_assignments: Dict[str, str] - component -> zone mapping
            - loop_components: List[List[str]] - list of component loops
            - min_hv_lv_clearance: float - required HV-LV clearance (mm)

    Returns:
        Dict with all metric scores and overall score:
        - total_wirelength: float (raw mm, not normalized)
        - thermal_score: float [0, 1]
        - zone_compliance_score: float [0, 1]
        - hv_lv_clearance_score: float [0, 1]
        - loop_area_score: float [0, 1]
        - congestion_score: float [0, 1]
        - compactness_score: float [0, 1]
        - connectivity_clustering_score: float [0, 1]
        - overall_score: float [0, 1] (weighted average)
    """
    # Extract config
    thermal_comps = config.get("thermal_components", set())
    hv_comps = config.get("hv_components", set())
    lv_comps = config.get("lv_components", set())
    zone_assigns = config.get("zone_assignments", {})
    loop_comps = config.get("loop_components", [])
    min_clearance = config.get("min_hv_lv_clearance", 8.0)

    # Compute all metrics
    wl = total_wirelength(state, netlist, context)
    thermal = thermal_score(state, netlist, board, thermal_comps)
    zone = zone_compliance_score(state, netlist, board, zone_assigns)
    clearance = hv_lv_clearance_score(state, netlist, hv_comps, lv_comps, min_clearance)
    loop = loop_area_score(state, netlist, context, loop_comps)
    congestion = congestion_score(state, netlist, board, context)
    compact = compactness_score(state, netlist, board)
    clustering = connectivity_clustering_score(state, netlist, context)

    # Compute overall score (equal weighting of normalized scores)
    # Note: wirelength is not included since it's not normalized
    normalized_scores = [thermal, zone, clearance, loop, congestion, compact, clustering]
    overall = sum(normalized_scores) / len(normalized_scores)

    return {
        "total_wirelength": wl,
        "thermal_score": thermal,
        "zone_compliance_score": zone,
        "hv_lv_clearance_score": clearance,
        "loop_area_score": loop,
        "congestion_score": congestion,
        "compactness_score": compact,
        "connectivity_clustering_score": clustering,
        "overall_score": overall,
    }
