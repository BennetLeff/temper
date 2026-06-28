"""Heuristic logic for routing pathfinding and net ordering (temper-16aw).

Provides different heuristic functions for maze routing:
- Manhattan distance (standard)
- Euclidean distance (smooth)
- Distance map (obstacle-aware, optimal)
- Custom heuristic support via strategy pattern
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Final

import jax.numpy as jnp
import numpy as np
from jax import Array

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component


OCTILE_DIAG: Final[float] = math.sqrt(2.0) - 1.0

_SAME_LAYER_DELTAS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 0), (0, -1), (-1, 0),
    (1, 1), (1, -1), (-1, 1), (-1, -1),
)


def octile_distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(dx, dy) + OCTILE_DIAG * min(dx, dy)


def in_bounds(x: int, y: int, width_cells: int, height_cells: int) -> bool:
    return 0 <= x < width_cells and 0 <= y < height_cells


HeuristicFunc = Callable[["GridCell", "GridCell"], float]


@dataclass(frozen=True)
class GridCell:
    """A cell in the routing grid.

    Immutable and hashable for use in pathfinding data structures.

    Attributes:
        x: Column index in grid
        y: Row index in grid
        layer: Layer index (0=L1_TOP, 1=L4_BOT for 2-layer)
    """

    x: int
    y: int
    layer: int = 0

    def __hash__(self) -> int:
        return hash((self.x, self.y, self.layer))


@dataclass
class NetMetrics:
    """Metrics for net ordering heuristic (temper-74wg.3).

    Attributes:
        net_name: Name of the net
        pin_count: Number of pins in the net
        bounding_box_area: Area of bounding box in mm²
        estimated_wirelength: Estimated wirelength in mm (half-perimeter)
        is_power: True if this is a power net
        is_ground: True if this is a ground net
    """

    net_name: str
    pin_count: int
    bounding_box_area: float
    estimated_wirelength: float
    is_power: bool
    is_ground: bool


def manhattan_heuristic(a: GridCell, b: GridCell) -> float:
    """Manhattan distance heuristic for A*.

    Returns:
        Heuristic distance (always admissible)
    """
    return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.layer - b.layer) * 2


def euclidean_heuristic(a: GridCell, b: GridCell) -> float:
    """Euclidean distance heuristic for A*.

    Returns:
        Heuristic distance
    """
    xy_dist = ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
    return xy_dist + abs(a.layer - b.layer) * 2


class HeuristicStrategy:
    """Wrapper for heuristic functions implementing the strategy pattern.

    Attributes:
        func: The heuristic function
        name: Strategy name for identification
    """

    def __init__(self, func: HeuristicFunc, name: str = "default"):
        self.func = func
        self.name = name

    def __call__(self, a: "GridCell", b: "GridCell") -> float:
        return self.func(a, b)

    def __repr__(self) -> str:
        return f"HeuristicStrategy({self.name!r})"


def create_distance_map_heuristic(dist_map: np.ndarray) -> HeuristicFunc:
    """Create a heuristic function from a precomputed distance map.

    Args:
        dist_map: 3D array of distances (same shape as grid)

    Returns:
        Heuristic function that looks up distances from the map
    """

    def heuristic(a: "GridCell", b: "GridCell") -> float:
        if 0 <= a.x < dist_map.shape[0]:
            if 0 <= a.y < dist_map.shape[1]:
                if 0 <= a.layer < dist_map.shape[2]:
                    return float(dist_map[a.x, a.y, a.layer])
        return float("inf")

    return heuristic


_HEURISTICS: dict[str, HeuristicStrategy] = {
    "manhattan": HeuristicStrategy(manhattan_heuristic, name="manhattan"),
    "euclidean": HeuristicStrategy(euclidean_heuristic, name="euclidean"),
    "default": HeuristicStrategy(manhattan_heuristic, name="manhattan"),
}


def get_heuristic(name: str) -> HeuristicStrategy:
    """Get a heuristic strategy by name.

    Args:
        name: Heuristic name ("manhattan", "euclidean", "default")

    Returns:
        HeuristicStrategy instance

    Raises:
        ValueError: If heuristic name is not recognized
    """
    if name not in _HEURISTICS:
        available = list(_HEURISTICS.keys())
        raise ValueError(f"Unknown heuristic: {name}. Available: {available}")
    return _HEURISTICS[name]


def register_heuristic(name: str, func: HeuristicFunc, overwrite: bool = False) -> None:
    """Register a custom heuristic strategy.

    Args:
        name: Strategy name
        func: Heuristic function
        overwrite: Whether to overwrite existing strategy
    """
    if name in _HEURISTICS and not overwrite:
        raise ValueError(f"Heuristic {name} already exists. Use overwrite=True to replace.")
    _HEURISTICS[name] = HeuristicStrategy(func, name=name)


def get_neighbor_cost(current: GridCell, neighbor: GridCell, via_cost: float = 1.0) -> float:
    """Get cost of moving from current to neighbor cell.

    Args:
        current: Current cell
        neighbor: Neighbor cell
        via_cost: Penalty cost for layer transitions

    Returns:
        Cost of move
    """
    base_cost = 1.0
    if current.layer != neighbor.layer:
        return base_cost + via_cost
    return base_cost


def compute_local_density(
    x: float, y: float, component_positions: Array, radius: float = 10.0
) -> float:
    """Compute component density within radius of point (temper-74wg.1).

    Args:
        x: X coordinate in mm
        y: Y coordinate in mm
        component_positions: (N, 2) array of component center positions
        radius: Search radius in mm

    Returns:
        Density from 0.0 (empty) to 1.0 (fully packed)
    """
    if component_positions is None or len(component_positions) == 0:
        return 0.0

    # Compute distances to all components
    point = jnp.array([x, y])
    distances = jnp.sqrt(jnp.sum((component_positions - point) ** 2, axis=1))
    count_within_radius = int(jnp.sum(distances <= radius))

    # Normalize by expected max components in area
    area = jnp.pi * radius**2
    avg_component_area = 100.0  # mm², typical component size
    max_components = area / avg_component_area

    return float(jnp.clip(count_within_radius / max_components, 0.0, 1.0))


def compute_escape_length(pin_x: float, pin_y: float, component_positions: Array) -> int:
    """Compute adaptive escape length based on local density (temper-74wg.1).

    Args:
        pin_x: Pin X coordinate in mm
        pin_y: Pin Y coordinate in mm
        component_positions: (N, 2) array of component center positions

    Returns:
        Escape route length in cells
    """
    density = compute_local_density(pin_x, pin_y, component_positions)
    base_length = 3

    if density < 0.3:
        # Sparse area: longer escapes for better routing options
        return base_length + 4  # 7 cells
    elif density > 0.7:
        # Dense area: shorter escapes to avoid interference
        return base_length  # 3 cells
    else:
        # Medium density
        return base_length + 2  # 5 cells


def get_primary_escape_direction(pin_offset: tuple[float, float]) -> tuple[int, int]:
    """Get primary escape direction from pin offset (temper-74wg.2).

    Args:
        pin_offset: (dx, dy) pin offset from component center

    Returns:
        (step_x, step_y) primary escape direction
    """
    dx, dy = pin_offset

    if abs(dx) >= abs(dy):
        # Horizontal escape
        return (1 if dx >= 0 else -1, 0)
    else:
        # Vertical escape
        return (0, 1 if dy >= 0 else -1)


def compute_net_metrics(
    net_name: str,
    pin_positions: list[tuple[float, float]],
) -> NetMetrics:
    """Compute metrics for a single net (temper-74wg.3).

    Args:
        net_name: Name of the net
        pin_positions: List of (x, y) pin positions in mm

    Returns:
        NetMetrics with computed values
    """
    if len(pin_positions) < 2:
        return NetMetrics(
            net_name=net_name,
            pin_count=len(pin_positions),
            bounding_box_area=0.0,
            estimated_wirelength=0.0,
            is_power=is_power_net(net_name),
            is_ground=is_ground_net(net_name),
        )

    xs = [p[0] for p in pin_positions]
    ys = [p[1] for p in pin_positions]

    # Bounding box
    bbox_width = max(xs) - min(xs)
    bbox_height = max(ys) - min(ys)
    bbox_area = bbox_width * bbox_height

    # Wirelength estimate: half-perimeter of bounding box
    wirelength = bbox_width + bbox_height

    return NetMetrics(
        net_name=net_name,
        pin_count=len(pin_positions),
        bounding_box_area=bbox_area,
        estimated_wirelength=wirelength,
        is_power=is_power_net(net_name),
        is_ground=is_ground_net(net_name),
    )


def is_power_net(net_name: str) -> bool:
    """Check if net is a power net."""
    from temper_placer.routing.net_classification import is_power_net as _is_power_net

    return _is_power_net(net_name)


def is_ground_net(net_name: str) -> bool:
    """Check if net is a ground net."""
    from temper_placer.routing.net_classification import is_ground_net as _is_ground_net

    return _is_ground_net(net_name)


def order_nets_for_routing(
    net_names: list[str],
    net_pin_positions: dict[str, list[tuple[float, float]]],
    strategy: str = "shortest_first",
) -> list[str]:
    """Order nets for routing using specified strategy (temper-74wg.3).

    Args:
        net_names: List of net names to order
        net_pin_positions: Dict mapping net names to pin positions
        strategy: Ordering strategy:
            - 'shortest_first': Route shortest nets first (by wirelength)
            - 'smallest_bbox': Route nets with smallest bounding box first
            - 'power_first': Route power/ground nets first, then by wirelength
            - 'arbitrary': No reordering (original order)

    Returns:
        Ordered list of net names
    """
    if strategy == "arbitrary":
        return net_names

    # Compute metrics for all nets
    metrics_list = [
        compute_net_metrics(name, net_pin_positions.get(name, [])) for name in net_names
    ]

    # Create (net_name, metrics) pairs
    net_metrics_pairs = list(zip(net_names, metrics_list))

    if strategy == "shortest_first":
        net_metrics_pairs.sort(key=lambda x: x[1].estimated_wirelength)
    elif strategy == "smallest_bbox":
        net_metrics_pairs.sort(key=lambda x: x[1].bounding_box_area)
    elif strategy == "power_first":
        # Separate power/ground from signal nets
        power_nets = [(n, m) for n, m in net_metrics_pairs if m.is_power or m.is_ground]
        signal_nets = [(n, m) for n, m in net_metrics_pairs if not m.is_power and not m.is_ground]

        # Sort signals by wirelength
        signal_nets.sort(key=lambda x: x[1].estimated_wirelength)

        # Power/ground first, then signals
        net_metrics_pairs = power_nets + signal_nets

    return [name for name, _ in net_metrics_pairs]


def compute_completion_rate(results: dict) -> float:
    """Compute fraction of successfully routed nets.

    Args:
        results: Dictionary mapping net names to RoutePath-like objects

    Returns:
        Completion rate from 0.0 to 1.0
    """
    if not results:
        return 1.0

    successful = sum(1 for r in results.values() if r.success)
    return successful / len(results)
