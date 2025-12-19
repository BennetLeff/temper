"""
Legalization and projection algorithms for PCB placement.

This module provides functions to project a placement state into the
feasible region defined by Design Rule Check (DRC) constraints.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import jax.numpy as jnp
from jax import Array

from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext

logger = logging.getLogger(__name__)

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
