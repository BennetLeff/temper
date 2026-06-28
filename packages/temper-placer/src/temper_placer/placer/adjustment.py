"""
Placement adjustments based on routing feedback.

This module provides functions to move components away from congested areas
detected during the routability feedback loop.
"""

from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.router_v6.congestion import CongestionResult


def adjust_for_congestion(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    congestion: CongestionResult,
    push_strength: float = 2.0,
) -> np.ndarray:
    """
    Adjust component positions by pushing them away from congestion hotspots.
    
    Args:
        positions: (N, 2) component positions.
        netlist: Netlist.
        board: Board geometry.
        congestion: Result of congestion analysis.
        push_strength: Distance to push in mm.
        
    Returns:
        (N, 2) adjusted positions.
    """
    if not congestion.bottlenecks:
        return positions.copy()
        
    result = positions.copy()
    
    # 1. Identify components near each bottleneck
    for bottleneck in congestion.bottlenecks:
        if bottleneck.overflow <= 0:
            continue
            
        bx, by = bottleneck.to_coordinates(
            congestion.grid.cell_size_mm, 
            congestion.grid.origin
        )
        
        # 2. Push components away from (bx, by)
        for i in range(len(netlist.components)):
            if netlist.components[i].fixed:
                continue
                
            px, py = result[i]
            dx, dy = px - bx, py - by
            dist = np.sqrt(dx**2 + dy**2)
            
            # Influence radius: say 10mm
            influence_radius = 10.0
            if dist < influence_radius:
                if dist < 1e-3: # At the exact spot
                    # Random push
                    angle = np.random.uniform(0, 2*np.pi)
                    result[i] += [push_strength * np.cos(angle), push_strength * np.sin(angle)]
                else:
                    # Normalized push
                    force = push_strength * (1.0 - dist / influence_radius)
                    result[i] += [force * dx / dist, force * dy / dist]
                    
    return result
