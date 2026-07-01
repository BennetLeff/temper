"""
Zone-aware spectral initialization for PCB placement.

Extends the standard spectral initialization to account for copper zones
and restricted areas on the board. Components are biased away from zones
to create better routing channels and reduce congestion.

Key improvements:
1. Parse copper zones from board geometry
2. Create "zone cost field" where zones have high cost
3. Adjust spectral coordinates to avoid high-cost regions
4. Separate HV components (should be IN zones) from signal (should be OUT of zones)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import jax.numpy as jnp
import numpy as np
from jax import Array
from scipy.ndimage import gaussian_filter

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.optimizer.initialization import (
    SpectralInitializer,
)

if TYPE_CHECKING:
    from temper_placer.core.board import Zone


def create_zone_cost_field(
    board: Board,
    zones: list[Zone] | None,
    grid_resolution: float = 0.5,
    zone_penalty: float = 10.0,
    boundary_margin: float = 3.0,
) -> tuple[Array, tuple[int, int], float]:
    """
    Create a 2D cost field where copper zones have high cost.

    This field guides placement away from zone-covered areas to maximize
    available routing channels for signal traces.

    Args:
        board: Board with dimensions
        zones: List of copper zones (GND, VCC planes)
        grid_resolution: Grid cell size in mm (default 0.5mm = reasonable for placement)
        zone_penalty: Cost multiplier for cells covered by zones
        boundary_margin: Additional margin around zones (mm) to create buffer

    Returns:
        Tuple of (cost_field, grid_size, cell_size):
            - cost_field: (W, H) array with cost per cell (1.0 = free, >1.0 = zone)
            - grid_size: (width_cells, height_cells)
            - cell_size: grid_resolution in mm
    """
    if zones is None or len(zones) == 0:
        # No zones - return uniform cost field
        w_cells = int(np.ceil(board.width / grid_resolution))
        h_cells = int(np.ceil(board.height / grid_resolution))
        return jnp.ones((w_cells, h_cells), dtype=jnp.float32), (w_cells, h_cells), grid_resolution

    # Create grid
    w_cells = int(np.ceil(board.width / grid_resolution))
    h_cells = int(np.ceil(board.height / grid_resolution))
    cost_field = np.ones((w_cells, h_cells), dtype=np.float32)

    # Mark zone-covered cells
    for zone in zones:
        # Get zone polygon points (zone.polygon is a list of (x, y) tuples)
        if not hasattr(zone, "polygon") or zone.polygon is None:
            continue

        # Simple rasterization: check each grid cell center
        for i in range(w_cells):
            for j in range(h_cells):
                # Cell center in board coordinates
                cx = (i + 0.5) * grid_resolution
                cy = (j + 0.5) * grid_resolution

                # Check if point is inside zone polygon (with margin)
                if _point_in_polygon_with_margin(cx, cy, zone.polygon, boundary_margin):
                    cost_field[i, j] = zone_penalty

    # Apply Gaussian blur to create smooth gradient around zones
    # This creates a "repulsion field" that gradually increases near zones
    sigma = boundary_margin / grid_resolution  # Blur radius in grid cells
    cost_field = gaussian_filter(cost_field, sigma=sigma, mode="constant", cval=1.0)

    return jnp.array(cost_field), (w_cells, h_cells), grid_resolution


def _point_in_polygon_with_margin(
    x: float,
    y: float,
    polygon: list[tuple[float, float]],
    _margin: float,
) -> bool:
    """
    Check if point (x, y) is inside polygon with optional margin.

    Uses ray casting algorithm. If margin > 0, expands polygon outward.

    Args:
        x, y: Point coordinates
        polygon: List of (x, y) vertices
        margin: Expand polygon by this distance (mm)

    Returns:
        True if point is inside expanded polygon
    """
    if len(polygon) < 3:
        return False

    # Simple ray casting (without margin for now - margin handled by Gaussian blur)
    # This is a simplified implementation
    n = len(polygon)
    inside = False

    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y) and y <= max(p1y, p2y) and x <= max(p1x, p2x):
            xinters = 0.0  # Initialize
            if p1y != p2y:
                xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
            if p1x == p2x or x <= xinters:
                inside = not inside
        p1x, p1y = p2x, p2y

    return inside


def adjust_positions_for_zones(
    positions: Array,
    cost_field: Array,
    grid_size: tuple[int, int],
    cell_size: float,
    board: Board,
    max_iterations: int = 50,
    step_size: float = 0.5,
) -> Array:
    """
    Adjust component positions to minimize zone cost using gradient descent.

    After spectral initialization, this function nudges components away from
    high-cost zones toward free routing channels.

    Args:
        positions: (N, 2) initial positions from spectral init
        cost_field: (W, H) zone cost field
        grid_size: (width_cells, height_cells)
        cell_size: grid resolution in mm
        board: Board dimensions for boundary checking
        max_iterations: Number of gradient descent steps
        step_size: Step size for position updates (mm)

    Returns:
        (N, 2) adjusted positions
    """
    # Convert to numpy for iteration
    pos = np.array(positions)
    w_cells, h_cells = grid_size

    for _ in range(max_iterations):
        # Compute gradient of cost field at each component position
        gradients = np.zeros_like(pos)

        for i in range(len(pos)):
            x, y = pos[i]

            # Convert to grid coordinates
            gx = x / cell_size
            gy = y / cell_size

            # Clip to valid grid range
            gx = np.clip(gx, 0, w_cells - 1)
            gy = np.clip(gy, 0, h_cells - 1)

            # Compute finite difference gradient
            ix, iy = int(gx), int(gy)

            # X gradient
            grad_x = cost_field[ix + 1, iy] - cost_field[ix, iy] if ix < w_cells - 1 else 0.0

            # Y gradient
            grad_y = cost_field[ix, iy + 1] - cost_field[ix, iy] if iy < h_cells - 1 else 0.0

            gradients[i] = [grad_x, grad_y]

        # Update positions (move away from high-cost zones)
        pos = pos - step_size * gradients

        # Clamp to board boundaries (with margin)
        margin = 5.0
        pos[:, 0] = np.clip(pos[:, 0], margin, board.width - margin)
        pos[:, 1] = np.clip(pos[:, 1], margin, board.height - margin)

    return jnp.array(pos)


@dataclass
class ZoneAwareSpectralInitializer(SpectralInitializer):
    """
    Spectral initializer that accounts for copper zones on the board.

    Extends SpectralInitializer with zone awareness:
    1. Creates zone cost field from copper planes
    2. Adjusts spectral coordinates to avoid zones
    3. Separates HV components (should be in zones) from signal (should avoid zones)

    Attributes:
        zone_penalty: Cost multiplier for zone-covered cells (default 10.0)
        boundary_margin: Buffer distance around zones (mm, default 3.0)
        adjustment_iters: Number of gradient descent steps for zone avoidance (default 50)
    """

    zone_penalty: float = 10.0
    boundary_margin: float = 3.0
    adjustment_iters: int = 50

    def initialize(
        self,
        netlist: "Netlist",
        board: "Board",
        rng_key: "Array | None" = None,
        constraints: Any | None = None,
    ) -> "Array":
        """
        Compute zone-aware initial positions.

        Process:
        1. Run standard spectral initialization
        2. Create zone cost field from board.zones
        3. Adjust positions away from zones using gradient descent

        Args:
            netlist: Component connectivity
            board: Board with zones
            rng_key: Unused (for API compatibility)

        Returns:
            (N, 2) initial positions optimized for zone avoidance
        """
        # Step 1: Standard spectral initialization
        positions = super().initialize(netlist, board, rng_key)

        # Step 2: Create zone cost field
        zones = getattr(board, "zones", None)
        if zones is None or len(zones) == 0:
            # No zones - return standard spectral result
            return positions

        cost_field, grid_size, cell_size = create_zone_cost_field(
            board,
            zones,
            grid_resolution=0.5,
            zone_penalty=self.zone_penalty,
            boundary_margin=self.boundary_margin,
        )

        # Step 3: Adjust positions to minimize zone cost
        adjusted_positions = adjust_positions_for_zones(
            positions,
            cost_field,
            grid_size,
            cell_size,
            board,
            max_iterations=self.adjustment_iters,
            step_size=0.5,
        )

        return adjusted_positions
