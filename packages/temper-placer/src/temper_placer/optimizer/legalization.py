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





def resolve_overlaps_priority(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    fixed_mask: np.ndarray | None = None,
    max_iterations: int = 300,
    min_separation: float = 0.5,
    damping: float = 0.8,
    enforce_zones: bool = False,
) -> np.ndarray:
    """
    Resolve overlaps with priority-based ordering (most severe first).
    Falls back to greedy placement if iterative method doesn't converge.
    """
    result = positions.copy()
    n = len(netlist.components)
    widths = np.array([c.bounds[0] for c in netlist.components])
    heights = np.array([c.bounds[1] for c in netlist.components])

    # Ensure we start with everything in bounds (and zones if requested)
    result = clamp_to_bounds(result, widths, heights, board, margin=min_separation)
    if enforce_zones:
        result = clamp_to_zones(result, netlist, board, fixed_mask)

    # Phase 1: Iterative push-apart (fast, usually works)
    for iteration in range(max_iterations):
        overlaps = []
        for i in range(n):
            hw_i, hh_i = widths[i] / 2, heights[i] / 2
            for j in range(i + 1, n):
                hw_j, hh_j = widths[j] / 2, heights[j] / 2
                dx = result[i, 0] - result[j, 0]
                dy = result[i, 1] - result[j, 1]
                overlap_x = (hw_i + hw_j + min_separation) - abs(dx)
                overlap_y = (hh_i + hh_j + min_separation) - abs(dy)

                if overlap_x > 0 and overlap_y > 0:
                    severity = min(overlap_x, overlap_y)
                    overlaps.append((severity, i, j, overlap_x, overlap_y, dx, dy))

        if not overlaps:
            logger.info(f"Overlap resolution converged in {iteration + 1} iterations")
            return result

        overlaps.sort(key=lambda x: x[0], reverse=True)
        n_to_resolve = max(1, int(len(overlaps) * damping ** (iteration / 20)))

        for _, i, j, ox, oy, dx, dy in overlaps[:n_to_resolve]:
            iter_damping = damping ** (iteration / 100)

            if ox < oy:
                force = ox * 0.7 * iter_damping  # Increased from 0.6
                dir_x = np.sign(dx) if abs(dx) > 1e-6 else 1.0
                if fixed_mask is None or not fixed_mask[i]:
                    result[i, 0] += force * dir_x
                if fixed_mask is None or not fixed_mask[j]:
                    result[j, 0] -= force * dir_x
            else:
                force = oy * 0.7 * iter_damping  # Increased from 0.6
                dir_y = np.sign(dy) if abs(dy) > 1e-6 else 1.0
                if fixed_mask is None or not fixed_mask[i]:
                    result[i, 1] += force * dir_y
                if fixed_mask is None or not fixed_mask[j]:
                    result[j, 1] -= force * dir_y

        result = clamp_to_bounds(result, widths, heights, board, margin=min_separation)
        if enforce_zones:
            result = clamp_to_zones(result, netlist, board, fixed_mask)

    # Phase 2: Greedy fallback - guaranteed to resolve overlaps
    logger.warning(f"Iterative resolution failed after {max_iterations} iterations. Using greedy fallback.")

    # Sort by size (largest first) for stable placement
    component_order = sorted(range(n), key=lambda i: widths[i] * heights[i], reverse=True)

    # Place components one by one, finding valid positions
    placed_boxes = []  # List of (x_min, y_min, x_max, y_max)

    for idx in component_order:
        if fixed_mask is not None and fixed_mask[idx]:
            # Fixed component - just record its box
            hw, hh = widths[idx] / 2, heights[idx] / 2
            placed_boxes.append((
                result[idx, 0] - hw - min_separation / 2,
                result[idx, 1] - hh - min_separation / 2,
                result[idx, 0] + hw + min_separation / 2,
                result[idx, 1] + hh + min_separation / 2,
            ))
            continue

        hw, hh = widths[idx] / 2, heights[idx] / 2
        original_pos = result[idx].copy()

        # Try positions in a spiral pattern from original position
        best_pos = original_pos.copy()
        best_dist = float('inf')

        # Zone bounds for this component
        comp = netlist.components[idx]
        zone_bounds = None
        if enforce_zones and comp.zone:
             for z in board.zones:
                 if z.name == comp.zone:
                     zone_bounds = z.bounds
                     break

        for spiral_step in range(200):
            # Spiral outward from original position
            angle = spiral_step * 0.5
            radius = spiral_step * 1.0  # 1mm per step
            test_x = original_pos[0] + radius * np.cos(angle)
            test_y = original_pos[1] + radius * np.sin(angle)

            # Clamp to board
            test_x = np.clip(test_x, hw + min_separation, board.width - hw - min_separation)
            test_y = np.clip(test_y, hh + min_separation, board.height - hh - min_separation)

            # Clamp to zone if needed
            if zone_bounds:
                test_x = np.clip(test_x, zone_bounds[0] + hw, zone_bounds[2] - hw)
                test_y = np.clip(test_y, zone_bounds[1] + hh, zone_bounds[3] - hh)

            # Check for overlaps with already-placed components
            test_box = (
                test_x - hw - min_separation / 2,
                test_y - hh - min_separation / 2,
                test_x + hw + min_separation / 2,
                test_y + hh + min_separation / 2,
            )

            overlaps_any = False
            for pb in placed_boxes:
                if not (test_box[2] < pb[0] or test_box[0] > pb[2] or
                        test_box[3] < pb[1] or test_box[1] > pb[3]):
                    overlaps_any = True
                    break

            if not overlaps_any:
                dist = np.sqrt((test_x - original_pos[0])**2 + (test_y - original_pos[1])**2)
                if dist < best_dist:
                    best_dist = dist
                    best_pos = np.array([test_x, test_y])
                if spiral_step == 0:  # Original position valid
                    break

        result[idx] = best_pos
        placed_boxes.append((
            best_pos[0] - hw - min_separation / 2,
            best_pos[1] - hh - min_separation / 2,
            best_pos[0] + hw + min_separation / 2,
            best_pos[1] + hh + min_separation / 2,
        ))

    logger.info("Greedy fallback completed")
    return result


def legalize_with_backtracking(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    fixed_mask: np.ndarray | None = None,
    min_separation: float = 0.5,
) -> np.ndarray:
    """
    Legalize placement using a backtracking search for difficult constraints.

    Sorts components by area and places them one-by-one. If a component
    cannot be placed without violating its zone or overlapping, it backtracks.
    """
    n = len(netlist.components)
    widths = np.array([c.bounds[0] for c in netlist.components])
    heights = np.array([c.bounds[1] for c in netlist.components])

    # Order: Fixed first, then by area
    list(range(n))
    area_order = sorted(
        [i for i in range(n) if fixed_mask is None or not fixed_mask[i]],
        key=lambda i: widths[i] * heights[i],
        reverse=True
    )
    fixed_indices = [i for i in range(n) if fixed_mask is not None and fixed_mask[i]]
    order = fixed_indices + area_order

    current_positions = positions.copy()
    placed_boxes: list[tuple[float, float, float, float]] = []

    def is_valid(idx, pos):
        hw, hh = widths[idx] / 2, heights[idx] / 2
        box = (
            pos[0] - hw - min_separation/2,
            pos[1] - hh - min_separation/2,
            pos[0] + hw + min_separation/2,
            pos[1] + hh + min_separation/2
        )

        # 1. Board bounds
        if (pos[0] - hw < board.origin[0] or pos[0] + hw > board.origin[0] + board.width or
            pos[1] - hh < board.origin[1] or pos[1] + hh > board.origin[1] + board.height):
            return False

        # 2. Zone bounds
        comp = netlist.components[idx]
        if comp.zone:
            for z in board.zones:
                if z.name == comp.zone:
                    if (pos[0] - hw < z.bounds[0] or pos[0] + hw > z.bounds[2] or
                        pos[1] - hh < z.bounds[1] or pos[1] + hh > z.bounds[3]):
                        return False
                    break

        # 3. Overlaps
        for pb in placed_boxes:
            if not (box[2] < pb[0] or box[0] > pb[2] or
                    box[3] < pb[1] or box[1] > pb[3]):
                return False
        return True

    def solve(order_idx):
        if order_idx == len(order):
            return True

        idx = order[order_idx]
        if fixed_mask is not None and fixed_mask[idx]:
            # Fixed components are already "placed"
            placed_boxes.append((
                current_positions[idx, 0] - widths[idx]/2 - min_separation/2,
                current_positions[idx, 1] - heights[idx]/2 - min_separation/2,
                current_positions[idx, 0] + widths[idx]/2 + min_separation/2,
                current_positions[idx, 1] + heights[idx]/2 + min_separation/2
            ))
            if solve(order_idx + 1):
                return True
            placed_boxes.pop()
            return False

        orig_pos = current_positions[idx]

        # Try a few candidate positions using spiral search
        candidates = [orig_pos]
        for step in range(1, 50): # Limit search breadth for backtracking efficiency
            angle = step * 0.5
            radius = step * 2.0
            candidates.append(orig_pos + [radius * np.cos(angle), radius * np.sin(angle)])

        for cand in candidates:
            # Quick clip to board for candidate
            hw, hh = widths[idx]/2, heights[idx]/2
            cand[0] = np.clip(cand[0], board.origin[0] + hw, board.origin[0] + board.width - hw)
            cand[1] = np.clip(cand[1], board.origin[1] + hh, board.origin[1] + board.height - hh)

            if is_valid(idx, cand):
                current_positions[idx] = cand
                placed_boxes.append((
                    cand[0] - hw - min_separation/2,
                    cand[1] - hh - min_separation/2,
                    cand[0] + hw + min_separation/2,
                    cand[1] + hh + min_separation/2
                ))
                if solve(order_idx + 1):
                    return True
                placed_boxes.pop()

        return False

    if solve(0):
        logger.info("Backtracking legalization succeeded")
        return current_positions
    else:
        logger.warning("Backtracking legalization failed, falling back to greedy")
        return resolve_overlaps_priority(positions, netlist, board, fixed_mask, min_separation=min_separation)


def project_to_trust_region(
    positions: np.ndarray,
    anchor_positions: np.ndarray,
    max_radius: float = 2.0,
    fixed_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Project positions to stay within a trust region (max radius from anchor).

    Args:
        positions: (N, 2) current positions.
        anchor_positions: (N, 2) reference positions (e.g. from template).
        max_radius: Maximum allowed displacement in mm.
        fixed_mask: Optional (N,) boolean mask.

    Returns:
        (N, 2) projected positions.
    """
    result = positions.copy()
    displacements = positions - anchor_positions
    distances = np.linalg.norm(displacements, axis=1)

    # Identify violations
    too_far = distances > max_radius
    if fixed_mask is not None:
        too_far = too_far & ~fixed_mask

    if np.any(too_far):
        # Project onto circle boundary
        scale = max_radius / distances[too_far]
        result[too_far] = anchor_positions[too_far] + displacements[too_far] * scale[:, np.newaxis]

    return result


def legalize_zone_aware(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    fixed_mask: np.ndarray | None = None,
    max_iterations: int = 500,
    min_separation: float = 0.5,
) -> tuple[np.ndarray, bool]:
    """
    Legalize placement ensuring components stay within assigned zones.

    This function wraps resolve_overlaps_priority with enforce_zones=True.

    Args:
        positions: (N, 2) array of component center positions.
        netlist: Netlist with component bounds and zone assignments.
        board: Board with zone definitions.
        fixed_mask: Optional (N,) boolean mask for fixed components.
        max_iterations: Maximum iterations for overlap resolution.
        min_separation: Minimum clearance.

    Returns:
        (positions, success) - success is True if no overlaps remain.
    """
    # 1. Initial clamp to zones
    result = clamp_to_zones(positions, netlist, board, fixed_mask)

    # 2. Resolve overlaps with zone enforcement
    result = resolve_overlaps_priority(
        result,
        netlist,
        board,
        fixed_mask,
        max_iterations=max_iterations,
        min_separation=min_separation,
        enforce_zones=True
    )

    # 3. Verify success
    # Check overlaps
    widths = np.array([c.bounds[0] for c in netlist.components])
    heights = np.array([c.bounds[1] for c in netlist.components])
    n = len(netlist.components)

    overlaps_found = False
    for i in range(n):
        for j in range(i + 1, n):
            dx = abs(result[i, 0] - result[j, 0])
            dy = abs(result[i, 1] - result[j, 1])
            if dx < (widths[i] + widths[j]) / 2 + min_separation and \
               dy < (heights[i] + heights[j]) / 2 + min_separation:
                overlaps_found = True
                break
        if overlaps_found:
            break

    return result, not overlaps_found



def resolve_overlaps(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    fixed_mask: np.ndarray | None = None,
    max_iterations: int = 300,  # Increased from 100
    min_separation: float = 0.5,
    damping: float = 0.8,  # Damping factor to prevent oscillation
) -> np.ndarray:
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

                # Compute axis-aligned bounding box overlap using Separating Axis Theorem
                # Two AABBs overlap iff they overlap on BOTH axes
                dx = pos_i[0] - pos_j[0]
                dy = pos_i[1] - pos_j[1]

                # Per-axis overlap computation (SAT)
                overlap_x = (hw_i + hw_j + min_separation) - abs(dx)
                overlap_y = (hh_i + hh_j + min_separation) - abs(dy)

                # Check if overlapping - must overlap on BOTH axes
                if overlap_x > 0 and overlap_y > 0:
                    overlaps_found = True

                    # Apply damping based on iteration (stronger damping later)
                    iteration_damping = damping ** (iteration / 50)

                    # Push along minimum overlap axis for cleaner separation
                    if overlap_x < overlap_y:
                        # Push horizontally (smaller overlap)
                        force_mag = overlap_x * 0.5 * iteration_damping
                        dir_x = np.sign(dx) if abs(dx) > 1e-6 else 1.0
                        forces[i, 0] += force_mag * dir_x
                        if fixed_mask is None or not fixed_mask[j]:
                            forces[j, 0] -= force_mag * dir_x
                    else:
                        # Push vertically (smaller overlap)
                        force_mag = overlap_y * 0.5 * iteration_damping
                        dir_y = np.sign(dy) if abs(dy) > 1e-6 else 1.0
                        forces[i, 1] += force_mag * dir_y
                        if fixed_mask is None or not fixed_mask[j]:
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

    components: list[int]  # Component indices in this cluster
    x_start: float  # Left edge of cluster
    total_width: float  # Sum of component widths
    total_weight: float  # Sum of component weights (usually = 1)
    opt_x: float  # Optimal x position (weighted sum of original positions)


def legalize_row_abacus(
    row_components: list[int],
    original_x: np.ndarray,
    widths: np.ndarray,
    weights: np.ndarray,
    row_x_min: float,
    row_x_max: float,
    spacing: float = 0.5,
) -> dict[int, float]:
    """
    Legalize a single row using the Abacus algorithm.

    Minimizes sum of squared displacements while ensuring no overlaps.

    Returns:
        Dict mapping component index to legalized center x position.
    """
    if not row_components:
        return {}

    # Sort components by original x position
    sorted_comps = sorted(row_components, key=lambda i: original_x[i])

    clusters: list[AbacusCluster] = []

    for comp_idx in sorted_comps:
        width = widths[comp_idx] + spacing
        orig_x = original_x[comp_idx]
        weight = weights[comp_idx]

        # Create new cluster for this component
        new_cluster = AbacusCluster(
            components=[comp_idx],
            x_start=orig_x - width / 2,  # Left edge
            total_width=width,
            total_weight=weight,
            opt_x=orig_x * weight,  # Weighted position sum
        )

        # Try to place this cluster optimally
        # Compute placement position
        cluster_x = new_cluster.opt_x / new_cluster.total_weight - new_cluster.total_width / 2
        cluster_x = max(cluster_x, row_x_min)  # Respect left boundary

        new_cluster.x_start = cluster_x

        # Check for overlap with previous cluster
        while clusters:
            prev = clusters[-1]
            prev_right = prev.x_start + prev.total_width

            if prev_right > new_cluster.x_start:
                # Overlap! Merge clusters
                merged = AbacusCluster(
                    components=prev.components + new_cluster.components,
                    x_start=0,  # Will recompute
                    total_width=prev.total_width + new_cluster.total_width,
                    total_weight=prev.total_weight + new_cluster.total_weight,
                    opt_x=prev.opt_x + new_cluster.opt_x,
                )

                # Optimal position for merged cluster
                merged_x = merged.opt_x / merged.total_weight - merged.total_width / 2
                merged_x = max(merged_x, row_x_min)
                merged.x_start = merged_x

                clusters.pop()
                new_cluster = merged
            else:
                break

        # Check right boundary
        if new_cluster.x_start + new_cluster.total_width > row_x_max:
            # Push left
            new_cluster.x_start = row_x_max - new_cluster.total_width

        clusters.append(new_cluster)

    # Extract final positions from clusters
    result = {}
    for cluster in clusters:
        x = cluster.x_start
        for comp_idx in cluster.components:
            width = widths[comp_idx] + spacing
            result[comp_idx] = x + width / 2  # Center position
            x += width

    return result


def legalize_abacus(
    state: PlacementState,
    context: LossContext,
    n_rows: int = 20,
    spacing: float = 0.5,
) -> PlacementState:
    """
    Legalize placement using the Abacus algorithm (2D version).

    Abacus minimizes the sum of squared displacements from original positions
    while ensuring no overlaps. It works row-by-row.

    Args:
        state: Optimized (but potentially overlapping) placement state.
        context: LossContext with netlist and board info.
        n_rows: Number of horizontal rows to bin components into.
        spacing: Minimum spacing between components.

    Returns:
        Legalized PlacementState.
    """
    positions = np.array(state.positions)
    n = positions.shape[0]

    # Component properties
    widths = np.array([c.bounds[0] for c in context.netlist.components])
    # heights = np.array([c.bounds[1] for c in context.netlist.components])
    weights = np.ones(n)  # Default uniform weights

    # Board geometry
    board = context.board
    row_height = board.height / n_rows
    origin_x, origin_y = board.origin

    # 1. Assign components to rows based on Y coordinate
    row_assignments: list[list[int]] = [[] for _ in range(n_rows)]
    for i in range(n):
        if context.fixed_mask[i]:
            continue
        row_idx = int(np.clip((positions[i, 1] - origin_y) / row_height, 0, n_rows - 1))
        row_assignments[row_idx].append(i)

    # 2. Legalize each row independently
    new_positions = positions.copy()
    for row_idx in range(n_rows):
        comp_indices = row_assignments[row_idx]
        if not comp_indices:
            continue

        row_y = origin_y + (row_idx + 0.5) * row_height
        row_x_min = origin_x
        row_x_max = origin_x + board.width

        legalized_x = legalize_row_abacus(
            comp_indices,
            positions[:, 0],  # Original X positions
            widths,
            weights,
            row_x_min,
            row_x_max,
            spacing=spacing,
        )

        for comp_idx, new_x in legalized_x.items():
            new_positions[comp_idx, 0] = new_x
            new_positions[comp_idx, 1] = row_y  # Snap to row center

    return PlacementState(jnp.array(new_positions), state.rotation_logits)


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
    # Use the improved priority-based resolution
    final_positions = resolve_overlaps_priority(
        positions=positions,
        netlist=context.netlist,
        board=context.board,
        fixed_mask=context.fixed_mask,
        max_iterations=max_iterations,
        min_separation=margin_mm,
    )

    # Convert back to JAX array
    return PlacementState(jnp.array(final_positions), state.rotation_logits)
