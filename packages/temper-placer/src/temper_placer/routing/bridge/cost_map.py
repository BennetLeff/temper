"""
Functional geometry routines for generating routing cost fields.

This module provides vectorized JAX operations to create 2D cost maps
for the MazeRouter, allowing semantic strategies (like EDGE_HUG) to be
translated into numerical search gradients.
"""

from __future__ import annotations

import jax.numpy as jnp
from jax import Array


def generate_edge_hug_field(
    grid_size: tuple[int, int],
    cell_size_mm: float,
    target_width_mm: float = 5.0,
    peak_penalty: float = 50.0,
) -> Array:
    """
    Create a 2D cost field that prioritizes routing near the board boundary.
    
    The field looks like a "valley" along the edges.
    """
    width_cells, height_cells = grid_size
    
    # 1. Create coordinate meshes
    x = jnp.arange(width_cells)
    y = jnp.arange(height_cells)
    X, Y = jnp.meshgrid(x, y, indexing='ij')
    
    # 2. Compute distance to nearest edge (in cells)
    dist_x = jnp.minimum(X, width_cells - 1 - X)
    dist_y = jnp.minimum(Y, height_cells - 1 - Y)
    dist_edge_cells = jnp.minimum(dist_x, dist_y)
    
    # 3. Convert to mm and apply penalty
    dist_edge_mm = dist_edge_cells * cell_size_mm
    
    # We want low cost (1.0) at the edge, increasing to peak_penalty 
    # as we move inward beyond target_width_mm.
    # Logic: penalty = sigmoid-like ramp
    normalized_dist = jnp.clip(dist_edge_mm / target_width_mm, 0.0, 1.0)
    
    # Square the ramp for a smoother valley
    field = 1.0 + (normalized_dist ** 2) * peak_penalty
    
    return field


def generate_zone_avoidance_field(
    grid_size: tuple[int, int],
    cell_size_mm: float,
    bounds_mm: tuple[float, float, float, float],
    penalty: float = 100.0,
) -> Array:
    """
    Create a 2D cost field that penalizes routing inside a specific rectangle.
    """
    width_cells, height_cells = grid_size
    x_min, y_min, x_max, y_max = bounds_mm
    
    # Convert bounds to cell indices
    gx_min = int(x_min / cell_size_mm)
    gx_max = int(x_max / cell_size_mm)
    gy_min = int(y_min / cell_size_mm)
    gy_max = int(y_max / cell_size_mm)
    
    # Create mask
    x = jnp.arange(width_cells)
    y = jnp.arange(height_cells)
    X, Y = jnp.meshgrid(x, y, indexing='ij')
    
    in_zone = (X >= gx_min) & (X <= gx_max) & (Y >= gy_min) & (Y <= gy_max)
    
    # Base cost 1.0, add penalty inside zone
    return jnp.where(in_zone, 1.0 + penalty, 1.0)


def compose_cost_fields(fields: list[Array], mode: str = "add") -> Array:
    """
    Combine multiple cost fields into a single map.
    """
    if not fields:
        return jnp.array([])
        
    result = fields[0]
    for f in fields[1:]:
        if mode == "add":
            result = result + (f - 1.0) # Subtract 1.0 to keep base cost at 1.0
        elif mode == "mul":
            result = result * f
            
    return result
