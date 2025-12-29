"""
Routing congestion feedback loss for placement-routing loop.

This module provides losses that penalize placement in congested areas
based on routing results, enabling the placement↔routing feedback loop
described in the architecture doc.

Key Functions:
- compute_congestion_heatmap: Convert routing conflicts to spatial cost map
- RoutingCongestionLoss: Placement penalty near conflict zones
"""

import jax.numpy as jnp
from jax import Array
from dataclasses import dataclass


@dataclass
class ConflictLocation:
    """A routing conflict at a specific location."""
    x: float
    y: float
    layer: int
    nets: list[str]


def compute_congestion_heatmap(
    conflicts: list[ConflictLocation],
    grid_size: tuple[int, int],
    cell_size_mm: float = 1.0,
    origin: tuple[float, float] = (0.0, 0.0),
    blur_sigma: float = 5.0,
) -> Array:
    """Convert routing conflicts to a spatial congestion heatmap.
    
    The heatmap is a 2D array where higher values indicate more congestion.
    Conflicts are weighted by the number of nets involved (squared).
    
    Args:
        conflicts: List of conflict locations from router
        grid_size: (width, height) in grid cells
        cell_size_mm: Size of each grid cell in mm
        origin: (x, y) world coordinate of grid origin
        blur_sigma: Gaussian blur sigma for spreading influence
    
    Returns:
        2D JAX array of congestion costs
    """
    heatmap = jnp.zeros(grid_size, dtype=jnp.float32)
    
    for conflict in conflicts:
        # Convert world to grid coordinates
        gx = int((conflict.x - origin[0]) / cell_size_mm)
        gy = int((conflict.y - origin[1]) / cell_size_mm)
        
        # Clamp to valid range
        gx = max(0, min(grid_size[0] - 1, gx))
        gy = max(0, min(grid_size[1] - 1, gy))
        
        # Weight by number of conflicting nets (squared for severity)
        weight = len(conflict.nets) ** 2
        heatmap = heatmap.at[gx, gy].add(weight)
    
    # Apply Gaussian blur to spread influence
    if blur_sigma > 0:
        heatmap = _gaussian_blur_2d(heatmap, blur_sigma)
    
    return heatmap


def _gaussian_blur_2d(arr: Array, sigma: float) -> Array:
    """Apply approximate Gaussian blur using box blur (JAX-compatible).
    
    Uses 3 iterations of box blur to approximate Gaussian.
    """
    kernel_size = max(1, int(sigma * 2))
    result = arr
    
    # Simple box blur approximation (3 passes = approximate Gaussian)
    for _ in range(3):
        # Horizontal blur
        padded = jnp.pad(result, ((kernel_size, kernel_size), (0, 0)), mode='edge')
        result = jnp.zeros_like(arr)
        for i in range(2 * kernel_size + 1):
            result = result + padded[i:i + arr.shape[0], :]
        result = result / (2 * kernel_size + 1)
        
        # Vertical blur  
        padded = jnp.pad(result, ((0, 0), (kernel_size, kernel_size)), mode='edge')
        result = jnp.zeros_like(arr)
        for i in range(2 * kernel_size + 1):
            result = result + padded[:, i:i + arr.shape[1]]
        result = result / (2 * kernel_size + 1)
    
    return result


def routing_congestion_loss(
    positions: Array,
    congestion_heatmap: Array,
    cell_size_mm: float = 1.0,
    origin: tuple[float, float] = (0.0, 0.0),
) -> float:
    """Compute placement penalty based on routing congestion.
    
    Components placed in congested areas incur higher cost,
    encouraging the optimizer to spread them apart.
    
    Args:
        positions: (N, 2) array of component positions
        congestion_heatmap: 2D array from compute_congestion_heatmap
        cell_size_mm: Size of each grid cell in mm
        origin: (x, y) world coordinate of grid origin
    
    Returns:
        Total congestion cost for all components
    """
    total_cost = 0.0
    grid_w, grid_h = congestion_heatmap.shape
    
    for pos in positions:
        # Convert to grid coordinates
        gx = jnp.clip(((pos[0] - origin[0]) / cell_size_mm).astype(jnp.int32), 0, grid_w - 1)
        gy = jnp.clip(((pos[1] - origin[1]) / cell_size_mm).astype(jnp.int32), 0, grid_h - 1)
        
        # Look up congestion cost at this position
        total_cost = total_cost + congestion_heatmap[gx, gy]
    
    return total_cost


class RoutingCongestionLoss:
    """Loss function that penalizes placement in congested areas.
    
    This enables the placement↔routing feedback loop by incorporating
    routing results into placement optimization.
    
    Usage:
        # After routing
        conflicts = router.get_conflict_locations()
        heatmap = compute_congestion_heatmap(conflicts, grid_size)
        
        # During next placement iteration
        loss = RoutingCongestionLoss(heatmap, weight=10.0)
        cost = loss(positions)
    """
    
    def __init__(
        self,
        congestion_heatmap: Array,
        weight: float = 10.0,
        cell_size_mm: float = 1.0,
        origin: tuple[float, float] = (0.0, 0.0),
    ):
        self.heatmap = congestion_heatmap
        self.weight = weight
        self.cell_size = cell_size_mm
        self.origin = origin
    
    def __call__(self, positions: Array) -> float:
        """Compute weighted congestion loss for given positions."""
        cost = routing_congestion_loss(
            positions,
            self.heatmap,
            self.cell_size,
            self.origin,
        )
        return self.weight * cost
    
    @classmethod
    def from_router_results(
        cls,
        conflict_locations: list[dict],
        grid_size: tuple[int, int],
        cell_size_mm: float = 1.0,
        origin: tuple[float, float] = (0.0, 0.0),
        weight: float = 10.0,
        blur_sigma: float = 5.0,
    ) -> "RoutingCongestionLoss":
        """Create loss from router's get_conflict_locations() output.
        
        Args:
            conflict_locations: List of dicts with 'x', 'y', 'layer', 'nets'
            grid_size: (width, height) in grid cells
            cell_size_mm: Grid cell size in mm
            origin: World coordinate of grid origin
            weight: Loss function weight
            blur_sigma: Blur sigma for spreading congestion influence
        """
        conflicts = [
            ConflictLocation(
                x=loc['x'],
                y=loc['y'], 
                layer=loc['layer'],
                nets=loc['nets'],
            )
            for loc in conflict_locations
        ]
        
        heatmap = compute_congestion_heatmap(
            conflicts,
            grid_size,
            cell_size_mm,
            origin,
            blur_sigma,
        )
        
        return cls(heatmap, weight, cell_size_mm, origin)
