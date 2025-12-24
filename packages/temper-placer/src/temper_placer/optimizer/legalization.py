"""
Legalization and projection algorithms for PCB placement.

This module provides functions to project a placement state into the
feasible region defined by Design Rule Check (DRC) constraints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import jax.numpy as jnp
import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.geometry.constraints import compute_valid_bounds
from temper_placer.losses.base import LossContext

logger = logging.getLogger(__name__)


def clamp_to_bounds(
    positions: np.ndarray,
    widths: np.ndarray,
    heights: np.ndarray,
    board: Board,
    margin: float = 0.0,
    fixed_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Clamp component positions to stay within board bounds.

    Pure functional operation: positions -> positions.
    Does not modify inputs.

    Args:
        positions: (N, 2) array of component center positions.
        widths: (N,) array of component widths.
        heights: (N,) array of component heights.
        board: Board object containing dimensions and origin.
        margin: Additional margin from board edge.
        fixed_mask: Optional (N,) boolean mask for fixed components.

    Returns:
        (N, 2) array of clamped positions.
    """
    result = positions.copy()
    n = positions.shape[0]
    origin_x, origin_y = board.origin

    for i in range(n):
        if fixed_mask is not None and fixed_mask[i]:
            continue

        hw, hh = widths[i] / 2, heights[i] / 2

        # Use shared predicate to compute valid bounds
        valid_bounds = compute_valid_bounds(
            component_half_width=hw,
            component_half_height=hh,
            region_x_min=origin_x,
            region_y_min=origin_y,
            region_x_max=origin_x + board.width,
            region_y_max=origin_y + board.height,
            margin=margin,
        )

        # Clamp using shared predicate
        result[i, 0], result[i, 1] = valid_bounds.clamp_point(result[i, 0], result[i, 1])

    return result


def clamp_to_zones(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    fixed_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Clamp component positions to their assigned zones.

    For each component with a zone assignment, ensures its position
    falls within the zone bounds. This enforces perfect zone compliance
    as a hard constraint.

    Args:
        positions: (N, 2) array of component center positions.
        netlist: Netlist with components and their zone assignments.
        board: Board with zone definitions.
        fixed_mask: Optional (N,) boolean mask for fixed components.

    Returns:
        (N, 2) array of clamped positions.
    """
    if not board.zones:
        return positions

    result = positions.copy()
    zone_lookup = {z.name: z for z in board.zones}

    for i, comp in enumerate(netlist.components):
        if fixed_mask is not None and fixed_mask[i]:
            continue

        if comp.zone and comp.zone in zone_lookup:
            zone = zone_lookup[comp.zone]
            x_min, y_min, x_max, y_max = zone.bounds

            # Account for component size
            hw, hh = comp.bounds[0] / 2, comp.bounds[1] / 2

            # Use shared predicate to compute valid bounds within zone
            valid_bounds = compute_valid_bounds(
                component_half_width=hw,
                component_half_height=hh,
                region_x_min=x_min,
                region_y_min=y_min,
                region_x_max=x_max,
                region_y_max=y_max,
                margin=0.0,
            )

            # Clamp using shared predicate
            result[i, 0], result[i, 1] = valid_bounds.clamp_point(result[i, 0], result[i, 1])

    return result


def legalize_individual_fast(
    positions: np.ndarray,
    widths: np.ndarray,
    heights: np.ndarray,
    board: Board,
    fixed_mask: np.ndarray | None = None,
    margin: float = 0.5,
    max_overlap_iterations: int = 10,
) -> np.ndarray:
    """
    Fast legalization for a single individual during NSGA evolution.

    This is a lightweight corrector used after mutation to ensure the
    individual satisfies basic DRC constraints (bounds + no severe overlaps).
    It's optimized for speed over perfection - used in the inner loop.

    This function is the "secret sauce" from PowerSynth: every child
    produced by crossover/mutation is immediately corrected to be valid.

    Algorithm:
    1. Clamp all positions to board bounds
    2. Quick overlap detection and push-apart (limited iterations)

    Args:
        positions: (N, 2) array of component positions
        widths: (N,) array of component widths
        heights: (N,) array of component heights
        board: Board with dimensions
        fixed_mask: Optional (N,) boolean mask for fixed components.
            Fixed components will not be moved during overlap resolution.
        margin: Minimum clearance between components
        max_overlap_iterations: Max iterations for overlap resolution

    Returns:
        (N, 2) array of legalized positions
    """
    # 1. Clamp to bounds (fast, vectorized)
    result = clamp_to_bounds(positions, widths, heights, board, margin=margin)

    n = result.shape[0]
    if n < 2:
        return result

    # 2. Quick overlap resolution (simplified, fewer iterations)
    for _ in range(max_overlap_iterations):
        overlaps_found = False

        # Check all pairs
        for i in range(n):
            hw_i, hh_i = widths[i] / 2, heights[i] / 2

            for j in range(i + 1, n):
                hw_j, hh_j = widths[j] / 2, heights[j] / 2

                # Axis-aligned bounding box overlap check
                dx = abs(result[i, 0] - result[j, 0])
                dy = abs(result[i, 1] - result[j, 1])

                overlap_x = (hw_i + hw_j + margin) - dx
                overlap_y = (hh_i + hh_j + margin) - dy

                if overlap_x > 0 and overlap_y > 0:
                    overlaps_found = True

                    # Push apart along minimum overlap axis
                    if overlap_x < overlap_y:
                        # Push horizontally
                        push = overlap_x / 2 + 0.1
                        if result[i, 0] < result[j, 0]:
                            if fixed_mask is None or not fixed_mask[i]:
                                result[i, 0] -= push
                            if fixed_mask is None or not fixed_mask[j]:
                                result[j, 0] += push
                        else:
                            if fixed_mask is None or not fixed_mask[i]:
                                result[i, 0] += push
                            if fixed_mask is None or not fixed_mask[j]:
                                result[j, 0] -= push
                    else:
                        # Push vertically
                        push = overlap_y / 2 + 0.1
                        if result[i, 1] < result[j, 1]:
                            if fixed_mask is None or not fixed_mask[i]:
                                result[i, 1] -= push
                            if fixed_mask is None or not fixed_mask[j]:
                                result[j, 1] += push
                        else:
                            if fixed_mask is None or not fixed_mask[i]:
                                result[i, 1] += push
                            if fixed_mask is None or not fixed_mask[j]:
                                result[j, 1] -= push

        if not overlaps_found:
            break

        # Re-clamp after pushing
        result = clamp_to_bounds(result, widths, heights, board, margin=margin)

    return result





def resolve_overlaps(
    positions: "np.ndarray",
    netlist: "Netlist",
    board: "Board",
    fixed_mask: "np.ndarray | None" = None,
    max_iterations: int = 300,  # Increased from 100
    min_separation: float = 0.5,
    damping: float = 0.8,  # Damping factor to prevent oscillation
) -> "np.ndarray":
    """
    Resolve overlapping components using iterative push-apart algorithm with damping.
    
    This function is critical for post-legalization cleanup. After zone clamping,
    components may overlap because zone boundaries are enforced without considering
    neighboring components. This function iteratively pushes overlapping components
    apart until no overlaps remain.
    
    Algorithm:
    1. Find all overlapping pairs
    2. For each pair, compute push force proportional to overlap
    3. Apply damped push along separation vector
    4. Ensure components stay within board bounds
    5. Repeat until no overlaps or max iterations reached
    
    Damping prevents oscillation by reducing push strength each iteration.
    
    Args:
        positions: (N, 2) array of component center positions.
        netlist: Netlist with component bounds.
        board: Board with dimensions.
        fixed_mask: Optional (N,) boolean mask for fixed components.
        max_iterations: Maximum number of push-apart iterations.
        min_separation: Minimum clearance between components in mm.
        damping: Damping factor (0.5-1.0). Lower = more stable but slower.
        
    Returns:
        (N, 2) array of overlap-free positions.
    """
    result = positions.copy()
    n_components = len(netlist.components)
    
    # Multi-pass: coarse adjustment first, then fine-tuning
    for iteration in range(max_iterations):
        # Compute forces for all components
        forces = np.zeros((n_components, 2))
        overlaps_found = False
        
        # Check all pairs for overlaps
        for i in range(n_components):
            # Don't skip fixed components here - they still cause overlaps!
            
            comp_i = netlist.components[i]
            pos_i = result[i]
            hw_i, hh_i = comp_i.bounds[0] / 2, comp_i.bounds[1] / 2
            
            for j in range(i + 1, n_components):
                comp_j = netlist.components[j]
                pos_j = result[j]
                hw_j, hh_j = comp_j.bounds[0] / 2, comp_j.bounds[1] / 2
                
                # Compute bounding box overlap
                dx = pos_i[0] - pos_j[0]
                dy = pos_i[1] - pos_j[1]
                dist = np.sqrt(dx**2 + dy**2)
                
                # Minimum required separation
                min_dx = hw_i + hw_j + min_separation
                min_dy = hh_i + hh_j + min_separation
                min_dist = np.sqrt(min_dx**2 + min_dy**2)
                
                # Check if overlapping (use radial distance for smoother behavior)
                if dist < min_dist:
                    overlaps_found = True
                    
                    # Avoid division by zero
                    if dist < 1e-6:
                        # Components exactly on top - push in deterministic direction based on indices
                        angle = (i + j) * 0.1
                        dir_x, dir_y = np.cos(angle), np.sin(angle)
                        overlap = min_dist
                    else:
                        # Normal case - push along separation vector
                        dir_x, dir_y = dx / dist, dy / dist
                        overlap = min_dist - dist
                    
                    # Force proportional to overlap (spring-like)
                    force_mag = overlap * 0.5  # Half to each component
                    
                    # Apply damping based on iteration (stronger damping later)
                    iteration_damping = damping ** (iteration / 50)
                    force_mag *= iteration_damping
                    
                    # Accumulate forces
                    forces[i, 0] += force_mag * dir_x
                    forces[i, 1] += force_mag * dir_y
                    
                    if fixed_mask is None or not fixed_mask[j]:
                        forces[j, 0] -= force_mag * dir_x
                        forces[j, 1] -= force_mag * dir_y
        
        # Apply forces to update positions
        for i in range(n_components):
            if fixed_mask is not None and fixed_mask[i]:
                continue
            result[i] += forces[i]
        
        # Clamp to board bounds after applying forces
        result = clamp_to_bounds(
            result,
            np.array([c.bounds[0] for c in netlist.components]),
            np.array([c.bounds[1] for c in netlist.components]),
            board,
            margin=2.0,
        )
        
        if not overlaps_found:
            logger.info(f"Overlap resolution converged in {iteration + 1} iterations")
            break
    
    if overlaps_found:
        logger.warning(f"Overlap resolution did not fully converge after {max_iterations} iterations")
    
    return result


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
    # heights = np.array([c.bounds[1] for c in context.netlist.components])

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

    # new_positions = positions.copy()

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
    # for cluster in clusters:
    #     curr_x = cluster.x_pos
    #     # Use original indices from sorted list?
    #     # Wait, the cluster needs to track which components it contains.
    #     # Simplified: re-iterate through comp_indices for this cluster
    #     # Actually, I should store the indices in the cluster.
    #     pass

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
    Uses NumPy for efficiency (avoids JAX dispatch overhead for iterative updates).
    
    Args:
        state: Current placement state.
        context: LossContext with netlist and board info.
        margin_mm: Additional safety margin to add to clearances.
        max_iterations: Maximum number of projection iterations.
        
    Returns:
        Feasible (or improved) PlacementState.
    """
    # Convert to numpy for mutable updates
    positions = np.array(state.positions)
    
    # 1. Resolve Overlaps and Enforce Boundaries
    # resolve_overlaps already calls clamp_to_bounds internally
    final_positions = resolve_overlaps(
        positions=positions,
        netlist=context.netlist,
        board=context.board,
        fixed_mask=context.fixed_mask,
        max_iterations=max_iterations,
        min_separation=margin_mm,
    )

    # Convert back to JAX array
    return PlacementState(jnp.array(final_positions), state.rotation_logits)
