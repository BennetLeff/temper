"""
Placement adjustments based on routing feedback.
"""

from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.routing.congestion import CongestionResult


def adjust_for_congestion(
    positions: np.ndarray,
    netlist: Netlist,
    board: Board,
    congestion: CongestionResult,
    push_strength: float = 2.0,
) -> np.ndarray:
    """Adjust component positions by pushing them away from congestion hotspots."""
    if not congestion.bottlenecks: return positions.copy()
    result = positions.copy()
    for bottleneck in congestion.bottlenecks:
        if bottleneck.overflow <= 0: continue
        bx, by = bottleneck.to_coordinates(congestion.grid.cell_size_mm, congestion.grid.origin)
        for i in range(len(netlist.components)):
            if netlist.components[i].fixed: continue
            px, py = result[i]
            dx, dy = px - bx, py - by
            dist = np.sqrt(dx**2 + dy**2)
            influence_radius = 10.0
            if dist < influence_radius:
                if dist < 1e-3:
                    angle = np.random.uniform(0, 2*np.pi)
                    result[i] += [push_strength * np.cos(angle), push_strength * np.sin(angle)]
                else:
                    force = push_strength * (1.0 - dist / influence_radius)
                    result[i] += [force * dx / dist, force * dy / dist]
    return result
