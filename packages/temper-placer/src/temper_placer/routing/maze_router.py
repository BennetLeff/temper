"""
Simplified maze router for PCB routing verification (temper-wna.4).

This module implements A* pathfinding on a grid to verify routing feasibility.
It is used to VERIFY that paths exist, not for production-quality routing.
The router helps detect placements that cannot be routed.

Features:
- Grid-based occupancy map
- A* pathfinding for single nets
- Sequential routing in priority order
- Via support for layer transitions

Example usage:
    >>> from temper_placer.routing.maze_router import MazeRouter
    >>> from temper_placer.core.board import Board
    >>>
    >>> router = MazeRouter.from_board(board, cell_size_mm=1.0)
    >>> router.block_components(netlist.components, positions)
    >>> result = router.route_net("NET_A", pin_positions, assignment)
    >>> if result.success:
    ...     print(f"Routed {len(result.cells)} cells")
"""

import heapq
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist

if TYPE_CHECKING:
    from temper_placer.routing.layer_assignment import LayerAssignment


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
class RoutingStats:
    """Statistics collected during routing."""

    total_time_ms: float = 0.0
    nets_routed: int = 0
    nets_failed: int = 0
    avg_time_per_net_ms: float = 0.0
    max_time_per_net_ms: float = 0.0
    total_astar_iterations: int = 0
    avg_iterations_per_path: float = 0.0


@dataclass
class RoutePath:
    """Result of routing a single net.

    Attributes:
        net: Net name
        cells: Ordered list of grid cells forming the path
        length: Total path length in cells
        via_count: Number of layer transitions
        success: True if routing succeeded
        failure_reason: Description of why routing failed (if not successful)
    """

    net: str
    cells: list[GridCell]
    length: float
    via_count: int
    success: bool
    failure_reason: str | None = None


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


class MazeRouter:
    """Grid-based maze router using A* pathfinding.

    The router maintains an occupancy grid where:
    - 0 = free (available for routing)
    - 1 = blocked (component or obstacle)
    - 2 = routed (used by a previous net)

    Attributes:
        grid_size: (width, height) in cells
        cell_size: Size of each cell in mm
        num_layers: Number of routing layers
        occupancy: 3D array of occupancy values (width, height, layers)
        origin: Board origin coordinates
        stats: Collected routing statistics
    """

    def __init__(
        self,
        grid_size: tuple[int, int],
        cell_size_mm: float = 1.0,
        num_layers: int = 1,
        origin: tuple[float, float] = (0.0, 0.0),
        via_cost: float = 1.0,
        layer_stackup: "LayerStackup | None" = None,
    ):
        """Initialize maze router.

        Args:
            grid_size: (width, height) of grid in cells
            cell_size_mm: Physical size of each cell
            num_layers: Number of routing layers
            origin: Board origin coordinates
            via_cost: Penalty cost for layer transitions
            layer_stackup: PCB layer stackup (optional, defaults to 4-layer)
        """
        self.grid_size = grid_size
        self.cell_size = cell_size_mm
        self.num_layers = num_layers
        self.origin = origin
        self.via_cost = via_cost

        # Layer stackup for layer-aware routing
        if layer_stackup is None:
            from temper_placer.core.board import LayerStackup
            self.layer_stackup = LayerStackup.default_4layer()
        else:
            self.layer_stackup = layer_stackup

        # Occupancy grid: (width, height, layers)
        # 0=free, 1=blocked, 2=routed
        self.occupancy = jnp.zeros((grid_size[0], grid_size[1], num_layers), dtype=jnp.int32)

        # Component positions for density computation (temper-74wg.1)
        self._component_positions: Array | None = None

        # Statistics
        self.stats = RoutingStats()

    @classmethod
    def from_board(
        cls,
        board: Board,
        cell_size_mm: float = 1.0,
        num_layers: int = 1,
        via_cost: float = 1.0,
    ) -> "MazeRouter":
        """Create router from board specification.

        Args:
            board: Board with dimensions
            cell_size_mm: Grid cell size
            num_layers: Number of routing layers
            via_cost: Penalty cost for layer transitions

        Returns:
            Initialized MazeRouter
        """
        width_cells = int(math.ceil(board.width / cell_size_mm))
        height_cells = int(math.ceil(board.height / cell_size_mm))

        # Use board's layer stackup if available
        layer_stackup = getattr(board, 'layer_stackup', None)

        return cls(
            grid_size=(width_cells, height_cells),
            cell_size_mm=cell_size_mm,
            num_layers=num_layers,
            origin=board.origin,
            via_cost=via_cost,
            layer_stackup=layer_stackup,
        )

    def _get_neighbor_cost(self, current: GridCell, neighbor: GridCell) -> float:
        """Get cost of moving from current to neighbor cell."""
        base_cost = 1.0
        if current.layer != neighbor.layer:
            return base_cost + self.via_cost
        return base_cost

    def block_rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        layer: int = 0,
    ) -> None:
        """Mark a rectangular area as blocked.

        Args:
            x: Left column of rectangle
            y: Top row of rectangle
            width: Width in cells
            height: Height in cells
            layer: Layer to block (or all if -1)
        """
        x_end = min(x + width, self.grid_size[0])
        y_end = min(y + height, self.grid_size[1])
        x_start = max(0, x)
        y_start = max(0, y)

        if layer == -1:
            # Block all layers
            for layer_idx in range(self.num_layers):
                self.occupancy = self.occupancy.at[x_start:x_end, y_start:y_end, layer_idx].set(1)
        else:
            self.occupancy = self.occupancy.at[x_start:x_end, y_start:y_end, layer].set(1)

    def block_components(
        self,
        components: list[Component],
        positions: Array,
        margin: float = 0.5,
        layer_specific: bool = False,
        escape_length: int | None = None,
    ) -> None:
        """Block cells occupied by components, leaving escape routes for pins.

        This method blocks component bodies but creates escape routes from each pin
        to the nearest board edge. Without escape routes, pins would be completely
        surrounded by blocked cells and unreachable by the router.

        Args:
            components: List of components to block
            positions: (N, 2) array of component center positions
            margin: Extra margin around components in mm
            layer_specific: If True, block only the component's layer (assumed L1_TOP/0)
            escape_length: Length of escape routes in cells. If None, calculated based on cell size.
        """
        if margin < 0:
            raise ValueError("margin must be non-negative")

        # Store component positions for density computation (temper-74wg.1)
        self._component_positions = positions

        # First pass: block all component bodies
        for i, comp in enumerate(components):
            cx, cy = float(positions[i, 0]), float(positions[i, 1])
            half_w = comp.bounds[0] / 2 + margin
            half_h = comp.bounds[1] / 2 + margin

            # Convert to grid coordinates (using round to block cells whose centers are covered)
            x_min = int(round((cx - half_w - self.origin[0]) / self.cell_size))
            x_max = int(round((cx + half_w - self.origin[0]) / self.cell_size))
            y_min = int(round((cy - half_h - self.origin[1]) / self.cell_size))
            y_max = int(round((cy + half_h - self.origin[1]) / self.cell_size))

            width = x_max - x_min
            height = y_max - y_min

            # Determine layer to block
            # For now, if layer_specific is True, we assume components are on layer 0
            block_layer = 0 if layer_specific else -1

            self.block_rect(x_min, y_min, width, height, layer=block_layer)

        # Second pass: create escape routes from pins
        for i, comp in enumerate(components):
            cx, cy = float(positions[i, 0]), float(positions[i, 1])
            self._create_pin_escape_routes(comp, cx, cy, escape_length)

    def _compute_local_density(self, x: float, y: float, radius: float = 10.0) -> float:
        """Compute component density within radius of point (temper-74wg.1).
        
        Args:
            x: X coordinate in mm
            y: Y coordinate in mm
            radius: Search radius in mm
        
        Returns:
            Density from 0.0 (empty) to 1.0 (fully packed)
        """
        if self._component_positions is None or len(self._component_positions) == 0:
            return 0.0

        # Compute distances to all components
        point = jnp.array([x, y])
        distances = jnp.sqrt(jnp.sum((self._component_positions - point)**2, axis=1))
        count_within_radius = int(jnp.sum(distances <= radius))

        # Normalize by expected max components in area
        area = jnp.pi * radius**2
        avg_component_area = 100.0  # mm², typical component size
        max_components = area / avg_component_area

        return float(jnp.clip(count_within_radius / max_components, 0.0, 1.0))

    def _compute_escape_length(self, pin_x: float, pin_y: float) -> int:
        """Compute adaptive escape length based on local density (temper-74wg.1).
        
        Args:
            pin_x: Pin X coordinate in mm
            pin_y: Pin Y coordinate in mm
        
        Returns:
            Escape route length in cells
        """
        density = self._compute_local_density(pin_x, pin_y)
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

    def _get_primary_escape_direction(self, pin_offset: tuple[float, float]) -> tuple[int, int]:
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

    def _try_escape_route(
        self,
        pin_x: float,
        pin_y: float,
        step_x: int,
        step_y: int,
        escape_length: int,
    ) -> bool:
        """Try to create escape route in given direction (temper-74wg.2).
        
        Args:
            pin_x: Pin X coordinate in mm
            pin_y: Pin Y coordinate in mm
            step_x: X step direction (-1, 0, or 1)
            step_y: Y step direction (-1, 0, or 1)
            escape_length: Length of escape route in cells
        
        Returns:
            True if route was successfully created, False if out of bounds
        """
        pin_gx, pin_gy = self._world_to_grid(pin_x, pin_y)

        # Check if route is viable (within bounds)
        # NOTE: We don't check if cells are blocked because block_components()
        # runs first and blocks component bodies. We need to unblock the escape
        # path to create a corridor from the pin to the board routing area.
        for step in range(escape_length):
            check_gx = pin_gx + step * step_x
            check_gy = pin_gy + step * step_y

            # Bounds check only - don't check blocking status
            if not (0 <= check_gx < self.grid_size[0] and 0 <= check_gy < self.grid_size[1]):
                return False

        # Route is viable, unblock it (this carves through blocked component body)
        for step in range(escape_length):
            unblock_gx = pin_gx + step * step_x
            unblock_gy = pin_gy + step * step_y

            for layer in range(self.num_layers):
                self.occupancy = self.occupancy.at[unblock_gx, unblock_gy, layer].set(0)

        return True

    def _create_pin_escape_routes(
        self,
        comp: Component,
        cx: float,
        cy: float,
        escape_length: int | None = None,
    ) -> None:
        """Create escape routes from component pins with multi-direction support.

        For each pin, tries to create an escape route in the primary direction
        (outward from component center). If blocked, tries perpendicular directions.
        This handles corner pins that may be blocked on their primary escape.

        Args:
            comp: Component with pins
            cx: Component center X position
            cy: Component center Y position
            escape_length: Optional explicit length for escape routes
        """
        for pin in comp.pins:
            # Compute absolute pin position
            pin_x = cx + pin.position[0]
            pin_y = cy + pin.position[1]

            # Compute adaptive escape length (temper-74wg.1)
            if escape_length is not None:
                escape_len = escape_length
            else:
                escape_len = self._compute_escape_length(pin_x, pin_y)

            # Get primary escape direction (temper-74wg.2)
            primary_x, primary_y = self._get_primary_escape_direction(pin.position)

            # Try directions: primary, then perpendiculars (temper-74wg.2)
            directions = [
                (primary_x, primary_y),  # Primary
                (primary_y, -primary_x),  # 90° clockwise
                (-primary_y, primary_x),  # 90° counter-clockwise
            ]

            # Try each direction until one succeeds
            for step_x, step_y in directions:
                if self._try_escape_route(pin_x, pin_y, step_x, step_y, escape_len):
                    break  # Success, move to next pin

    def _world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert world coordinates to grid coordinates.
        
        Uses rounding to ensure cells at boundaries are handled consistently.
        This prevents floating-point precision issues where coordinates very
        close to cell boundaries might map to unexpected cells.
        """
        gx = int(round((x - self.origin[0]) / self.cell_size))
        gy = int(round((y - self.origin[1]) / self.cell_size))
        return (
            max(0, min(gx, self.grid_size[0] - 1)),
            max(0, min(gy, self.grid_size[1] - 1)),
        )

    def _heuristic(self, a: GridCell, b: GridCell) -> float:
        """Manhattan distance heuristic for A*."""
        return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.layer - b.layer) * 2

    def _get_neighbors(
        self,
        cell: GridCell,
        allow_layer_change: bool = False,
        allowed_layers: list[int] | None = None,
    ) -> list[GridCell]:
        """Get valid neighboring cells for pathfinding.
        
        Args:
            cell: Current cell
            allow_layer_change: Whether to allow layer transitions (vias)
            allowed_layers: List of layer indices that can be used (None = all layers)
        
        Returns:
            List of valid neighbor cells
        """
        neighbors: list[GridCell] = []

        # Determine which layers are allowed
        if allowed_layers is None:
            allowed_layers = list(range(self.num_layers))

        # 4-connected neighbors on same layer
        # Prohibit horizontal routing on plane layers (via-only policy)
        if not self.layer_stackup.is_plane_layer(cell.layer):
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cell.x + dx, cell.y + dy
                # Check if free (0) - not blocked (1) or routed (2)
                if (
                    0 <= nx < self.grid_size[0]
                    and 0 <= ny < self.grid_size[1]
                    and cell.layer in allowed_layers  # Check current layer is allowed
                    and int(self.occupancy[nx, ny, cell.layer]) == 0
                ):
                    neighbors.append(GridCell(nx, ny, cell.layer))

        # Layer transitions (vias)
        if allow_layer_change and self.num_layers > 1:
            for new_layer in allowed_layers:  # Only consider allowed layers
                if new_layer != cell.layer and int(self.occupancy[cell.x, cell.y, new_layer]) == 0:
                    neighbors.append(GridCell(cell.x, cell.y, new_layer))

        return neighbors

    def find_path(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        layer: int = 0,
        allow_layer_change: bool = False,
        allowed_layers: list[int] | None = None,
    ) -> list[GridCell] | None:
        """Find path between two points using A*.

        Args:
            start: (x, y) start position in grid coordinates
            end: (x, y) end position in grid coordinates
            layer: Starting layer
            allow_layer_change: Whether to allow layer transitions
            allowed_layers: List of layer indices that can be used (None = all layers)

        Returns:
            List of GridCells forming the path, or None if no path exists
        """
        start_cell = GridCell(start[0], start[1], layer)
        end_cell = GridCell(end[0], end[1], layer)

        # Check if start/end are valid
        if int(self.occupancy[start[0], start[1], layer]) != 0:
            return None
        if int(self.occupancy[end[0], end[1], layer]) != 0:
            # Try other layers for end point
            found_end = False
            for layer_idx in range(self.num_layers):
                if int(self.occupancy[end[0], end[1], layer_idx]) == 0:
                    end_cell = GridCell(end[0], end[1], layer_idx)
                    found_end = True
                    break
            if not found_end:
                return None

        # A* algorithm
        open_set: list[tuple[float, int, GridCell]] = []  # (f_score, counter, cell)
        counter = 0  # Tiebreaker for heap
        heapq.heappush(open_set, (0, counter, start_cell))

        came_from: dict[GridCell, GridCell] = {}
        g_score: dict[GridCell, float] = {start_cell: 0}
        f_score: dict[GridCell, float] = {start_cell: self._heuristic(start_cell, end_cell)}

        visited: set[GridCell] = set()

        while open_set:
            _, _, current = heapq.heappop(open_set)

            # Count iterations for stats
            self.stats.total_astar_iterations += 1

            if current in visited:
                continue
            visited.add(current)

            if current.x == end_cell.x and current.y == end_cell.y:
                # Reconstruct path
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path

            for neighbor in self._get_neighbors(current, allow_layer_change, allowed_layers):
                if neighbor in visited:
                    continue

                # Use dynamic neighbor cost (includes via penalty)
                move_cost = self._get_neighbor_cost(current, neighbor)
                tentative_g = g_score[current] + move_cost

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + self._heuristic(neighbor, end_cell)
                    f_score[neighbor] = f
                    counter += 1
                    heapq.heappush(open_set, (f, counter, neighbor))

        return None  # No path found

    def route_net(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
    ) -> RoutePath:
        """Route a single net between its pins.

        For multi-pin nets, uses a simple star topology (first pin to all others).

        Args:
            net_name: Name of the net
            pin_positions: List of (x, y) pin positions in world coordinates
            assignment: Layer assignment for this net

        Returns:
            RoutePath with routing result
        """
        from temper_placer.routing.layer_assignment import Layer

        if len(pin_positions) < 2:
            return RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=True,
            )

        # Determine layer index
        layer = 0 if assignment.primary_layer == Layer.L1_TOP else 1
        if layer >= self.num_layers:
            layer = 0

        # Check if layer changes are allowed
        allow_via = len(assignment.allowed_layers) > 1

        # Convert pin positions to grid coordinates
        grid_pins = [self._world_to_grid(x, y) for x, y in pin_positions]

        # Temporarily unblock pin positions (pins are routing targets even if
        # inside component footprint)
        original_values: list[tuple[int, int, int, int]] = []
        for gx, gy in grid_pins:
            for layer_idx in range(self.num_layers):
                val = int(self.occupancy[gx, gy, layer_idx])
                if val == 1:  # Blocked
                    original_values.append((gx, gy, layer_idx, val))
                    self.occupancy = self.occupancy.at[gx, gy, layer_idx].set(0)

        # Route from first pin to all others (star topology)
        all_cells: list[GridCell] = []
        total_vias = 0
        start_grid = grid_pins[0]

        for i in range(1, len(grid_pins)):
            end_grid = grid_pins[i]

            path = self.find_path(start_grid, end_grid, layer, allow_via)

            if path is None:
                return RoutePath(
                    net=net_name,
                    cells=all_cells,
                    length=float(len(all_cells)),
                    via_count=total_vias,
                    success=False,
                    failure_reason=f"No path from {start_grid} to {end_grid}",
                )

            # Count vias in this segment
            for j in range(1, len(path)):
                if path[j].layer != path[j - 1].layer:
                    total_vias += 1

            # Add path cells (skip duplicate start point after first segment)
            if all_cells:
                path = path[1:]  # Skip start point
            all_cells.extend(path)

            # Mark cells as routed
            for cell in path:
                if int(self.occupancy[cell.x, cell.y, cell.layer]) == 0:
                    self.occupancy = self.occupancy.at[cell.x, cell.y, cell.layer].set(2)

        return RoutePath(
            net=net_name,
            cells=all_cells,
            length=float(len(all_cells)),
            via_count=total_vias,
            success=True,
        )

    def route_all_nets(
        self,
        netlist: Netlist,
        positions: Array,
        net_order: list[str],
        assignments: dict[str, "LayerAssignment"],
    ) -> dict[str, RoutePath]:
        """Route all nets in priority order.

        Args:
            netlist: Netlist with components and nets
            positions: (N, 2) array of component positions
            net_order: List of net names in routing order
            assignments: Layer assignments for each net

        Returns:
            Dictionary mapping net names to RoutePath results
        """
        start_time = time.perf_counter()
        results: dict[str, RoutePath] = {}
        times_per_net: list[float] = []

        # Build component index
        comp_by_ref = {c.ref: (i, c) for i, c in enumerate(netlist.components)}

        # Build net lookup
        net_by_name = {n.name: n for n in netlist.nets}

        for net_name in net_order:
            if net_name not in net_by_name:
                continue

            net_start = time.perf_counter()
            net = net_by_name[net_name]

            # Collect pin positions
            pin_positions: list[tuple[float, float]] = []
            for pin_ref in net.pins:
                comp_ref, pin_name = pin_ref
                if comp_ref not in comp_by_ref:
                    continue

                comp_idx, comp = comp_by_ref[comp_ref]
                cx, cy = float(positions[comp_idx, 0]), float(positions[comp_idx, 1])

                # Find pin offset
                for pin in comp.pins:
                    if pin.name == pin_name or pin.number == pin_name:
                        px = cx + pin.position[0]
                        py = cy + pin.position[1]
                        pin_positions.append((px, py))
                        break

            # Get assignment
            assignment = assignments.get(net_name)
            if assignment is None:
                from temper_placer.routing.layer_assignment import Layer, LayerAssignment

                assignment = LayerAssignment(
                    net=net_name,
                    primary_layer=Layer.L4_BOT,
                    allowed_layers={Layer.L4_BOT},
                    vias_required=False,
                    reason="Default",
                )

            # Route the net
            result = self.route_net(net_name, pin_positions, assignment)
            results[net_name] = result

            net_end = time.perf_counter()
            times_per_net.append((net_end - net_start) * 1000.0) # ms

        # Update stats
        total_time = (time.perf_counter() - start_time) * 1000.0
        self.stats.total_time_ms = total_time
        self.stats.nets_routed = sum(1 for r in results.values() if r.success)
        self.stats.nets_failed = len(results) - self.stats.nets_routed

        if times_per_net:
            self.stats.avg_time_per_net_ms = sum(times_per_net) / len(times_per_net)
            self.stats.max_time_per_net_ms = max(times_per_net)

        if self.stats.nets_routed > 0:
            self.stats.avg_iterations_per_path = (
                self.stats.total_astar_iterations / self.stats.nets_routed
            )

        return results


def compute_completion_rate(results: dict[str, RoutePath]) -> float:
    """Compute fraction of successfully routed nets.

    Args:
        results: Dictionary of routing results

    Returns:
        Completion rate from 0.0 to 1.0
    """
    if not results:
        return 1.0

    successful = sum(1 for r in results.values() if r.success)
    return successful / len(results)


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
            is_power=_is_power_net(net_name),
            is_ground=_is_ground_net(net_name),
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
        is_power=_is_power_net(net_name),
        is_ground=_is_ground_net(net_name),
    )


def _is_power_net(net_name: str) -> bool:
    """Check if net is a power net."""
    power_names = ['VCC', 'VDD', '3V3', '5V', '12V', 'VBUS', 'VBAT', 'V+']
    return any(name in net_name.upper() for name in power_names)


def _is_ground_net(net_name: str) -> bool:
    """Check if net is a ground net."""
    ground_names = ['GND', 'VSS', 'AGND', 'DGND', 'PGND', 'V-']
    return any(name in net_name.upper() for name in ground_names)


def order_nets_for_routing(
    net_names: list[str],
    net_pin_positions: dict[str, list[tuple[float, float]]],
    strategy: str = 'shortest_first',
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
    if strategy == 'arbitrary':
        return net_names

    # Compute metrics for all nets
    metrics_list = [
        compute_net_metrics(name, net_pin_positions.get(name, []))
        for name in net_names
    ]

    # Create (net_name, metrics) pairs
    net_metrics_pairs = list(zip(net_names, metrics_list))

    if strategy == 'shortest_first':
        net_metrics_pairs.sort(key=lambda x: x[1].estimated_wirelength)
    elif strategy == 'smallest_bbox':
        net_metrics_pairs.sort(key=lambda x: x[1].bounding_box_area)
    elif strategy == 'power_first':
        # Separate power/ground from signal nets
        power_nets = [(n, m) for n, m in net_metrics_pairs if m.is_power or m.is_ground]
        signal_nets = [(n, m) for n, m in net_metrics_pairs if not m.is_power and not m.is_ground]

        # Sort signals by wirelength
        signal_nets.sort(key=lambda x: x[1].estimated_wirelength)

        # Power/ground first, then signals
        net_metrics_pairs = power_nets + signal_nets

    return [name for name, _ in net_metrics_pairs]
