"""
Metrics for ground plane integrity (Phase 3).

This module provides tools to analyze routing results and verify that 
power/ground planes remain continuous and unfragmented.
"""

from dataclasses import dataclass

import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.routing.maze_router import RoutePath


@dataclass
class PlaneIntegrityMetrics:
    """Integrity metrics for a single plane layer."""
    layer_idx: int
    layer_name: str
    via_count: int
    horizontal_segment_count: int # Should be zero
    via_density_max: float # Vias per square mm in densest region
    integrity_score: float # 0.0 (poor) to 1.0 (perfect)

def analyze_plane_integrity(
    results: dict[str, RoutePath],
    board: Board
) -> list[PlaneIntegrityMetrics]:
    """Analyze plane integrity across all nets.
    
    Args:
        results: Dictionary of net names to RoutePath objects
        board: Board definition with layer stackup
        
    Returns:
        List of PlaneIntegrityMetrics, one per plane layer
    """
    if not board.layer_stackup:
        return []

    plane_layers = [
        (i, layer.name)
        for i, layer in enumerate(board.layer_stackup.layers)
        if layer.layer_type == "plane"
    ]

    if not plane_layers:
        return []

    metrics_list = []

    for layer_idx, layer_name in plane_layers:
        via_locations = []
        horizontal_segments = 0

        for net_name, path in results.items():
            if not path.success:
                continue

            cells = path.cells
            for i in range(len(cells)):
                if cells[i].layer == layer_idx:
                    # Found a cell on this plane layer
                    via_locations.append((cells[i].x, cells[i].y))

                    # Check for horizontal move on this layer
                    if i < len(cells) - 1:
                        next_cell = cells[i+1]
                        if next_cell.layer == layer_idx:
                            # If it stays on the plane layer, it must be stationary (via pierce)
                            if next_cell.x != cells[i].x or next_cell.y != cells[i].y:
                                horizontal_segments += 1

        # Calculate max via density
        via_count = len(via_locations)
        max_density = 0.0
        if via_count > 0:
            # Simple grid-based density: count vias in 10x10 cell windows
            # In a real tool we'd use a sliding window or KDE, but cells work for now.
            # Assuming cell_size reflects the grid density
            coords = jnp.array(via_locations)
            # Find max via count in any 5x5 cell area
            # This is a bit slow if many vias, but okay for reporting.
            if via_count < 1000:
                for x, y in via_locations:
                    # Count neighbors within 5 cells
                    dist_sq = (coords[:, 0] - x)**2 + (coords[:, 1] - y)**2
                    count = jnp.sum(dist_sq <= 25) # 5 cell radius
                    max_density = max(max_density, float(count))
            else:
                max_density = via_count / (board.width * board.height) # Fallback

        # Compute score
        # Integrity score drops with horizontal segments and high density
        penalty = (horizontal_segments * 0.1) + (max_density * 0.01)
        score = max(0.0, 1.0 - penalty)

        metrics_list.append(PlaneIntegrityMetrics(
            layer_idx=layer_idx,
            layer_name=layer_name,
            via_count=via_count,
            horizontal_segment_count=horizontal_segments,
            via_density_max=max_density,
            integrity_score=score
        ))

    return metrics_list
