"""
Legalization and projection algorithms for PCB placement.

This module provides functions to project a placement state into the
feasible region defined by Design Rule Check (DRC) constraints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

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
    """Clamp component positions to stay within board bounds."""
    result = positions.copy()
    n = positions.shape[0]
    origin_x, origin_y = board.origin

    for i in range(n):
        if fixed_mask is not None and fixed_mask[i]:
            continue

        hw, hh = widths[i] / 2, heights[i] / 2
        valid_bounds = compute_valid_bounds(
            component_half_width=hw,
            component_half_height=hh,
            region_x_min=origin_x,
            region_y_min=origin_y,
            region_x_max=origin_x + board.width,
            region_y_max=origin_y + board.height,
            margin=margin,
        )
        result[i, 0], result[i, 1] = valid_bounds.clamp_point(result[i, 0], result[i, 1])

    return result


def clamp_to_zones(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    fixed_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Clamp component positions to their assigned zones."""
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
            hw, hh = comp.bounds[0] / 2, comp.bounds[1] / 2
            valid_bounds = compute_valid_bounds(
                component_half_width=hw,
                component_half_height=hh,
                region_x_min=x_min,
                region_y_min=y_min,
                region_x_max=x_max,
                region_y_max=y_max,
                margin=0.0,
            )
            result[i, 0], result[i, 1] = valid_bounds.clamp_point(result[i, 0], result[i, 1])

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
    """Resolve overlaps with priority-based ordering."""
    result = positions.copy()
    n = len(netlist.components)
    widths = np.array([c.bounds[0] for c in netlist.components])
    heights = np.array([c.bounds[1] for c in netlist.components])

    result = clamp_to_bounds(result, widths, heights, board, margin=min_separation)
    if enforce_zones:
        result = clamp_to_zones(result, netlist, board, fixed_mask)

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
            return result

        overlaps.sort(key=lambda x: x[0], reverse=True)
        n_to_resolve = max(1, int(len(overlaps) * damping ** (iteration / 20)))
        
        for _, i, j, ox, oy, dx, dy in overlaps[:n_to_resolve]:
            iter_damping = damping ** (iteration / 100)
            if ox < oy:
                force = ox * 0.7 * iter_damping
                dir_x = np.sign(dx) if abs(dx) > 1e-6 else 1.0
                if fixed_mask is None or not fixed_mask[i]:
                    result[i, 0] += force * dir_x
                if fixed_mask is None or not fixed_mask[j]:
                    result[j, 0] -= force * dir_x
            else:
                force = oy * 0.7 * iter_damping
                dir_y = np.sign(dy) if abs(dy) > 1e-6 else 1.0
                if fixed_mask is None or not fixed_mask[i]:
                    result[i, 1] += force * dir_y
                if fixed_mask is None or not fixed_mask[j]:
                    result[j, 1] -= force * dir_y

        result = clamp_to_bounds(result, widths, heights, board, margin=min_separation)
        if enforce_zones:
            result = clamp_to_zones(result, netlist, board, fixed_mask)

    logger.warning(f"Iterative resolution failed after {max_iterations} iterations. Using greedy fallback.")
    
    component_order = sorted(range(n), key=lambda i: widths[i] * heights[i], reverse=True)
    placed_boxes = []
    
    for idx in component_order:
        hw, hh = widths[idx] / 2, heights[idx] / 2
        if fixed_mask is not None and fixed_mask[idx]:
            placed_boxes.append((result[idx, 0] - hw, result[idx, 1] - hh, result[idx, 0] + hw, result[idx, 1] + hh))
            continue
        
        original_pos = result[idx].copy()
        best_pos = original_pos.copy()
        best_dist = float('inf')
        
        comp = netlist.components[idx]
        zone_bounds = None
        if enforce_zones and comp.zone:
             for z in board.zones:
                 if z.name == comp.zone:
                     zone_bounds = z.bounds
                     break
        
        for spiral_step in range(200):
            angle = spiral_step * 0.5
            radius = spiral_step * 1.0
            test_x = original_pos[0] + radius * np.cos(angle)
            test_y = original_pos[1] + radius * np.sin(angle)
            test_x = np.clip(test_x, board.origin[0] + hw + min_separation, board.origin[0] + board.width - hw - min_separation)
            test_y = np.clip(test_y, board.origin[1] + hh + min_separation, board.origin[1] + board.height - hh - min_separation)
            if zone_bounds:
                test_x = np.clip(test_x, zone_bounds[0] + hw, zone_bounds[2] - hw)
                test_y = np.clip(test_y, zone_bounds[1] + hh, zone_bounds[3] - hh)
            
            test_box = (test_x - hw - min_separation/2, test_y - hh - min_separation/2, test_x + hw + min_separation/2, test_y + hh + min_separation/2)
            overlaps_any = False
            for pb in placed_boxes:
                if not (test_box[2] < pb[0] or test_box[0] > pb[2] or test_box[3] < pb[1] or test_box[1] > pb[3]):
                    overlaps_any = True
                    break
            
            if not overlaps_any:
                dist = np.sqrt((test_x - original_pos[0])**2 + (test_y - original_pos[1])**2)
                if dist < best_dist:
                    best_dist = dist
                    best_pos = np.array([test_x, test_y])
                if spiral_step == 0: break
        
        result[idx] = best_pos
        placed_boxes.append((best_pos[0] - hw, best_pos[1] - hh, best_pos[0] + hw, best_pos[1] + hh))
    
    return result


def legalize_zone_aware(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    fixed_mask: np.ndarray | None = None,
    max_iterations: int = 500,
    min_separation: float = 0.5,
) -> tuple[np.ndarray, bool]:
    """Legalize placement ensuring components stay within assigned zones."""
    result = clamp_to_zones(positions, netlist, board, fixed_mask)
    result = resolve_overlaps_priority(result, netlist, board, fixed_mask, max_iterations=max_iterations, min_separation=min_separation, enforce_zones=True)
    
    widths = np.array([c.bounds[0] for c in netlist.components])
    heights = np.array([c.bounds[1] for c in netlist.components])
    n = len(netlist.components)
    overlaps_found = False
    for i in range(n):
        for j in range(i + 1, n):
            dx = abs(result[i, 0] - result[j, 0])
            dy = abs(result[i, 1] - result[j, 1])
            if dx < (widths[i] + widths[j]) / 2 + min_separation and dy < (heights[i] + heights[j]) / 2 + min_separation:
                overlaps_found = True
                break
        if overlaps_found: break
            
    return result, not overlaps_found


def legalize_with_backtracking(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    fixed_mask: np.ndarray | None = None,
    min_separation: float = 0.5,
) -> np.ndarray:
    """Legalize placement using a backtracking search for difficult constraints."""
    n = len(netlist.components)
    widths = np.array([c.bounds[0] for c in netlist.components])
    heights = np.array([c.bounds[1] for c in netlist.components])
    area_order = sorted([i for i in range(n) if fixed_mask is None or not fixed_mask[i]], key=lambda i: widths[i] * heights[i], reverse=True)
    order = [i for i in range(n) if fixed_mask is not None and fixed_mask[i]] + area_order
    current_positions = positions.copy()
    placed_boxes = []
    
    def is_valid(idx, pos):
        hw, hh = widths[idx] / 2, heights[idx] / 2
        box = (pos[0] - hw - min_separation/2, pos[1] - hh - min_separation/2, pos[0] + hw + min_separation/2, pos[1] + hh + min_separation/2)
        if (pos[0] - hw < board.origin[0] or pos[0] + hw > board.origin[0] + board.width or pos[1] - hh < board.origin[1] or pos[1] + hh > board.origin[1] + board.height): return False
        comp = netlist.components[idx]
        if comp.zone:
            for z in board.zones:
                if z.name == comp.zone:
                    if (pos[0] - hw < z.bounds[0] or pos[0] + hw > z.bounds[2] or pos[1] - hh < z.bounds[1] or pos[1] + hh > z.bounds[3]): return False
                    break
        for pb in placed_boxes:
            if not (box[2] < pb[0] or box[0] > pb[2] or box[3] < pb[1] or box[1] > pb[3]): return False
        return True

    def solve(order_idx):
        if order_idx == len(order): return True
        idx = order[order_idx]
        if fixed_mask is not None and fixed_mask[idx]:
            placed_boxes.append((current_positions[idx, 0] - widths[idx]/2 - min_separation/2, current_positions[idx, 1] - heights[idx]/2 - min_separation/2, current_positions[idx, 0] + widths[idx]/2 + min_separation/2, current_positions[idx, 1] + heights[idx]/2 + min_separation/2))
            if solve(order_idx + 1): return True
            placed_boxes.pop(); return False
        orig_pos = current_positions[idx]
        candidates = [orig_pos]
        for step in range(1, 50):
            angle = step * 0.5; radius = step * 2.0
            candidates.append(orig_pos + [radius * np.cos(angle), radius * np.sin(angle)])
        for cand in candidates:
            hw, hh = widths[idx]/2, heights[idx]/2
            cand[0] = np.clip(cand[0], board.origin[0] + hw, board.origin[0] + board.width - hw)
            cand[1] = np.clip(cand[1], board.origin[1] + hh, board.origin[1] + board.height - hh)
            if is_valid(idx, cand):
                current_positions[idx] = cand
                placed_boxes.append((cand[0] - hw - min_separation/2, cand[1] - hh - min_separation/2, cand[0] + hw + min_separation/2, cand[1] + hh + min_separation/2))
                if solve(order_idx + 1): return True
                placed_boxes.pop()
        return False

    if solve(0): return current_positions
    return resolve_overlaps_priority(positions, netlist, board, fixed_mask, min_separation=min_separation)


def project_to_trust_region(
    positions: np.ndarray,
    anchor_positions: np.ndarray,
    max_radius: float = 2.0,
    fixed_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Project positions to stay within a trust region."""
    result = positions.copy()
    displacements = positions - anchor_positions
    distances = np.linalg.norm(displacements, axis=1)
    too_far = distances > max_radius
    if fixed_mask is not None: too_far = too_far & ~fixed_mask
    if np.any(too_far):
        scale = max_radius / distances[too_far]
        result[too_far] = anchor_positions[too_far] + displacements[too_far] * scale[:, np.newaxis]
    return result


def project_to_drc_feasible(
    state: PlacementState,
    context: LossContext,
    margin_mm: float = 0.1,
    max_iterations: int = 10,
) -> PlacementState:
    """Project placement state into DRC-feasible region (simple legalization)."""
    positions = np.array(state.positions)
    final_positions = resolve_overlaps_priority(
        positions=positions,
        netlist=context.netlist,
        board=context.board,
        fixed_mask=context.fixed_mask,
        max_iterations=max_iterations,
        min_separation=margin_mm,
    )
    return PlacementState(jnp.array(final_positions), state.rotation_logits)