"""Cell difficulty calculation for maze routing.

Provides functions for computing routing difficulty based on:
- Proximity to blocked cells (components, keepouts)
- Component density in the area

These metrics help the router prioritize easier paths and avoid congested areas.
"""

import numpy as np

from temper_placer.routing.grid import GridCell


def compute_proximity_difficulty(
    cell: GridCell,
    occupancy: np.ndarray,
    grid_size: tuple[int, int],
    penalty_per_blocked_neighbor: float = 0.5,
) -> float:
    """Compute difficulty based on proximity to blocked cells.

    Cells adjacent to blocked areas (components, keepouts) are harder
    to route through because they have less margin for error.

    Args:
        cell: The cell to compute difficulty for
        occupancy: 3D numpy array of occupancy values (-1=blocked, 0=free, 2=routed)
        grid_size: Tuple of (width, height) for bounds checking
        penalty_per_blocked_neighbor: Difficulty penalty for each blocked neighbor

    Returns:
        Difficulty score (0.0 = easy, higher = harder)
    """
    difficulty = 0.0

    # Check cardinal neighbors for blocked cells
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nx, ny = cell.x + dx, cell.y + dy
        if 0 <= nx < grid_size[0] and 0 <= ny < grid_size[1]:
            if int(occupancy[nx, ny, cell.layer]) == -1:
                difficulty += penalty_per_blocked_neighbor

    return difficulty


def compute_density_difficulty(
    cell: GridCell,
    density_map: np.ndarray | None,
    weight: float = 1.0,
) -> float:
    """Compute difficulty based on component density.

    High-density areas (many components nearby) are harder to route
    through due to limited free space for traces.

    Args:
        cell: The cell to compute difficulty for
        density_map: 3D numpy array of density values (0.0 to 1.0), or None
        weight: Multiplier for density contribution

    Returns:
        Difficulty score from density (0.0 to 1.0, scaled by weight)
    """
    if density_map is None:
        return 0.0

    density = float(density_map[cell.x, cell.y, cell.layer])
    return density * weight


def get_cell_difficulty(
    cell: GridCell,
    density_map: np.ndarray | None,
    occupancy: np.ndarray,
    grid_size: tuple[int, int],
    proximity_weight: float = 0.5,
    density_weight: float = 1.0,
) -> float:
    """Compute total difficulty for a cell.

    Combines proximity and density difficulties into a single score.

    Args:
        cell: The cell to compute difficulty for
        density_map: Pre-computed 3D density map, or None for density=0
        occupancy: 3D numpy array of occupancy values
        grid_size: Tuple of (width, height) for bounds checking
        proximity_weight: Weight for proximity difficulty contribution
        density_weight: Weight for density difficulty contribution

    Returns:
        Total difficulty score (higher = harder to route)
    """
    proximity = compute_proximity_difficulty(
        cell, occupancy, grid_size, penalty_per_blocked_neighbor=proximity_weight
    )

    density = compute_density_difficulty(cell, density_map, weight=density_weight)

    return proximity + density


def compute_density_map(
    positions: np.ndarray,
    grid_size: tuple[int, int],
    cell_size: float,
    origin: tuple[float, float],
    radius_mm: float = 10.0,
    num_layers: int = 1,
) -> np.ndarray:
    """Pre-compute component density for all grid cells.

    This converts cell difficulty from O(VisitedCells * NumComponents)
    to O(1) array lookup. Uses vectorized NumPy operations for speed.

    Args:
        positions: (N, 2) array of component positions in world coordinates
        grid_size: Tuple of (width, height) for the grid
        cell_size: Size of each grid cell in mm
        origin: (x, y) origin of the grid in world coordinates
        radius_mm: Radius in mm for density calculation
        num_layers: Number of layers in the board

    Returns:
        3D numpy array of shape (grid_size[0], grid_size[1], num_layers)
        with density values in range [0.0, 1.0]
    """
    if positions is None or len(positions) == 0:
        return np.zeros(grid_size + (num_layers,), dtype=np.float32)

    radius_cells_sq = (radius_mm / cell_size) ** 2

    # Create meshgrid of world coordinates
    x_coords = np.arange(grid_size[0]) * cell_size + origin[0]
    y_coords = np.arange(grid_size[1]) * cell_size + origin[1]
    X, Y = np.meshgrid(x_coords, y_coords, indexing="ij")  # (W, H)

    comp_array = np.asarray(positions)  # (N, 2)
    cx = comp_array[:, 0]
    cy = comp_array[:, 1]

    density_map_2d = np.zeros(grid_size, dtype=np.float32)

    # Loop over components (N) and vectorize over grid (W*H)
    # This is memory efficient and much faster than nested loops
    for i in range(len(cx)):
        dists_sq = (X - cx[i]) ** 2 + (Y - cy[i]) ** 2
        density_map_2d += (dists_sq <= radius_cells_sq).astype(np.float32)

    # Normalize and clip
    # Density is normalized by expected count in a circle of radius_mm
    normalization = np.pi * radius_mm**2 / 100.0
    density_map_2d = np.clip(density_map_2d / normalization, 0.0, 1.0)

    # Expand to 3D by repeating across layers
    density_map_3d = np.repeat(density_map_2d[:, :, np.newaxis], num_layers, axis=2)

    return density_map_3d


def compute_local_density(
    x: float,
    y: float,
    positions: np.ndarray,
    radius: float = 10.0,
) -> float:
    """Compute density at a single point (world coordinates).

    This is a fallback for when the density map hasn't been pre-computed.
    Uses JAX for vectorized computation.

    Args:
        x: World X coordinate
        y: World Y coordinate
        positions: (N, 2) array of component positions
        radius: Radius in mm for density calculation

    Returns:
        Density value in range [0.0, 1.0]
    """
    import jax.numpy as jnp

    if positions is None or not len(positions):
        return 0.0

    point = jnp.array([x, y])
    distances = jnp.sqrt(jnp.sum((positions - point) ** 2, axis=1))
    count = int(jnp.sum(distances <= radius))
    normalization = np.pi * radius**2 / 100.0
    return float(jnp.clip(count / normalization, 0.0, 1.0))
