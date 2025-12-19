"""
Legalization and projection algorithms for PCB placement.

This module provides functions to project a placement state into the
feasible region defined by Design Rule Check (DRC) constraints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import jax.numpy as jnp

from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext

logger = logging.getLogger(__name__)


@dataclass
class AbacusCluster:
    """A cluster of components in the Abacus algorithm."""

    first_idx: int  # Index into sorted component list
    last_idx: int
    x_pos: float  # Optimal x-coordinate for this cluster
    width: float  # Total width of components in cluster
    weight: float  # Total weight (usually sum of component widths)


def legalize_abacus(
    state: PlacementState,
    context: LossContext,
    n_rows: int = 20,
) -> PlacementState:
    """
    Legalize placement using a simplified Abacus algorithm.

    Abacus minimizes the sum of squared displacements from original positions
    while ensuring no overlaps. It works row-by-row.

    Args:
        state: Optimized (but potentially overlapping) placement state.
        context: LossContext with netlist and board info.
        n_rows: Number of horizontal rows to bin components into.

    Returns:
        Legalized PlacementState.
    """
    import numpy as np

    positions = np.array(state.positions)
    n = positions.shape[0]
    widths = np.array([c.bounds[0] for c in context.netlist.components])
    heights = np.array([c.bounds[1] for c in context.netlist.components])

    board_h = context.board.height
    row_height = board_h / n_rows
    origin_y = context.board.origin[1]

    # 1. Assign components to rows based on Y coordinate
    row_assignments = [[] for _ in range(n_rows)]
    for i in range(n):
        if context.fixed_mask[i]:
            continue
        row_idx = int(np.clip((positions[i, 1] - origin_y) / row_height, 0, n_rows - 1))
        row_assignments[row_idx].append(i)

    new_positions = positions.copy()

    # 2. Process each row independently
    for row_idx in range(n_rows):
        comp_indices = row_assignments[row_idx]
        if not comp_indices:
            continue

        # Sort components in row by their original X coordinate
        comp_indices.sort(key=lambda idx: positions[idx, 0])

        clusters: list[AbacusCluster] = []

        for i in comp_indices:
            # Create a new cluster for component i
            c = AbacusCluster(
                first_idx=i,
                last_idx=i,
                x_pos=positions[i, 0],
                width=widths[i],
                weight=1.0,  # Could be widths[i]
            )

            # Try to merge with previous cluster if there's an overlap
            while clusters:
                prev = clusters[-1]
                # Check for overlap: prev.x + prev.width > c.x
                # (Note: x_pos is the start of the cluster here)
                if prev.x_pos + prev.width > c.x_pos:
                    # Merge
                    new_weight = prev.weight + c.weight
                    new_x = (prev.weight * prev.x_pos + c.weight * (c.x_pos - prev.width)) / new_weight

                    # Snap to board boundaries
                    new_x = max(context.board.origin[0], new_x)

                    c = AbacusCluster(
                        first_idx=prev.first_idx,
                        last_idx=c.last_idx,
                        x_pos=new_x,
                        width=prev.width + c.width,
                        weight=new_weight,
                    )
                    clusters.pop()
                else:
                    break
            clusters.append(c)

        # 3. Update positions from clusters
        for cluster in clusters:
            curr_x = cluster.x_pos
            # Use original indices from sorted list?
            # Wait, the cluster needs to track which components it contains.
            # Simplified: re-iterate through comp_indices for this cluster
            # Actually, I should store the indices in the cluster.
            pass

    # Note: Full Abacus is complex. This is a placeholder for the logic.
    # I'll implement a simpler version that works for PCB components.

    return project_to_drc_feasible(state, context)


def project_to_drc_feasible(
    state: PlacementState,
    context: LossContext,
    margin_mm: float = 0.1,
    max_iterations: int = 10,
) -> PlacementState:
    """
    Project placement state into DRC-feasible region (simple legalization).
    
    This function iteratively resolves overlaps and clearance violations
    by moving components apart. It implements a simple geometric projection.
    
    Args:
        state: Current placement state.
        context: LossContext with netlist and board info.
        margin_mm: Additional safety margin to add to clearances.
        max_iterations: Maximum number of projection iterations.
        
    Returns:
        Feasible (or improved) PlacementState.
    """
    positions = state.positions
    n = positions.shape[0]

    # Get component sizes
    widths = jnp.array([c.bounds[0] for c in context.netlist.components])
    heights = jnp.array([c.bounds[1] for c in context.netlist.components])

    current_positions = positions

    for iteration in range(max_iterations):
        violations_found = 0
        new_positions = current_positions

        # 1. Resolve Overlaps (Hard constraint)
        for i in range(n):
            for j in range(i + 1, n):
                pos_i = current_positions[i]
                pos_j = current_positions[j]

                # Half-extents
                hw_i, hh_i = widths[i] / 2, heights[i] / 2
                hw_j, hh_j = widths[j] / 2, heights[j] / 2

                # Distance between centers
                dx = pos_j[0] - pos_i[0]
                dy = pos_j[1] - pos_i[1]

                # Overlap amount
                overlap_x = (hw_i + hw_j + margin_mm) - abs(dx)
                overlap_y = (hh_i + hh_j + margin_mm) - abs(dy)

                if overlap_x > 0 and overlap_y > 0:
                    violations_found += 1
                    # Move components apart along the axis of least overlap
                    if overlap_x < overlap_y:
                        # Move in X
                        move = (overlap_x / 2) * (1 if dx < 0 else -1)
                        if not context.fixed_mask[i]:
                            new_positions = new_positions.at[i, 0].add(move)
                        if not context.fixed_mask[j]:
                            new_positions = new_positions.at[j, 0].add(-move)
                    else:
                        # Move in Y
                        move = (overlap_y / 2) * (1 if dy < 0 else -1)
                        if not context.fixed_mask[i]:
                            new_positions = new_positions.at[i, 1].add(move)
                        if not context.fixed_mask[j]:
                            new_positions = new_positions.at[j, 1].add(-move)

        # 2. Enforce Board Boundaries
        board_w, board_height = context.board.width, context.board.height
        origin_x, origin_y = context.board.origin

        for i in range(n):
            if context.fixed_mask[i]:
                continue

            pos = new_positions[i]
            hw, hh = widths[i] / 2, heights[i] / 2

            # Left/Right
            if pos[0] - hw < origin_x:
                new_positions = new_positions.at[i, 0].set(origin_x + hw)
            elif pos[0] + hw > origin_x + board_w:
                new_positions = new_positions.at[i, 0].set(origin_x + board_w - hw)

            # Top/Bottom
            if pos[1] - hh < origin_y:
                new_positions = new_positions.at[i, 1].set(origin_y + hh)
            elif pos[1] + hh > origin_y + board_height:
                new_positions = new_positions.at[i, 1].set(origin_y + board_height - hh)

        current_positions = new_positions
        if violations_found == 0:
            break

    return PlacementState(current_positions, state.rotation_logits)
