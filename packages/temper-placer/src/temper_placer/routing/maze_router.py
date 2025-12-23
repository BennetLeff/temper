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

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import heapq
import math

import jax.numpy as jnp
from jax import Array

from temper_placer.core.netlist import Component, Netlist
from temper_placer.core.board import Board

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
    ):
        """Initialize maze router.

        Args:
            grid_size: (width, height) of grid in cells
            cell_size_mm: Physical size of each cell
            num_layers: Number of routing layers
            origin: Board origin coordinates
            via_cost: Penalty cost for layer transitions
        """
        self.grid_size = grid_size
        self.cell_size = cell_size_mm
        self.num_layers = num_layers
        self.origin = origin
        self.via_cost = via_cost

        # Occupancy grid: (width, height, layers)
        # 0=free, 1=blocked, 2=routed
        self.occupancy = jnp.zeros((grid_size[0], grid_size[1], num_layers), dtype=jnp.int32)
        
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

        return cls(
            grid_size=(width_cells, height_cells),
            cell_size_mm=cell_size_mm,
            num_layers=num_layers,
            origin=board.origin,
            via_cost=via_cost,
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
            for l in range(self.num_layers):
                self.occupancy = self.occupancy.at[x_start:x_end, y_start:y_end, l].set(1)
        else:
            self.occupancy = self.occupancy.at[x_start:x_end, y_start:y_end, layer].set(1)

    def block_components(
        self,
        components: list[Component],
        positions: Array,
        margin: float = 0.5,
    ) -> None:
        """Block cells occupied by components, leaving escape routes for pins.

        This method blocks component bodies but creates escape routes from each pin
        to the nearest board edge. Without escape routes, pins would be completely
        surrounded by blocked cells and unreachable by the router.

        Args:
            components: List of components to block
            positions: (N, 2) array of component center positions
            margin: Extra margin around components in mm
        """
        # First pass: block all component bodies
        for i, comp in enumerate(components):
            cx, cy = float(positions[i, 0]), float(positions[i, 1])
            half_w = comp.bounds[0] / 2 + margin
            half_h = comp.bounds[1] / 2 + margin

            # Convert to grid coordinates
            x_min = int((cx - half_w - self.origin[0]) / self.cell_size)
            x_max = int((cx + half_w - self.origin[0]) / self.cell_size) + 1
            y_min = int((cy - half_h - self.origin[1]) / self.cell_size)
            y_max = int((cy + half_h - self.origin[1]) / self.cell_size) + 1

            width = x_max - x_min
            height = y_max - y_min

            # Block on all layers (components are obstacles on all layers)
            self.block_rect(x_min, y_min, width, height, layer=-1)

        # Second pass: create escape routes from pins
        for i, comp in enumerate(components):
            cx, cy = float(positions[i, 0]), float(positions[i, 1])
            self._create_pin_escape_routes(comp, cx, cy)

    def _create_pin_escape_routes(
        self,
        comp: Component,
        cx: float,
        cy: float,
    ) -> None:
        """Create escape routes from component pins.

        For each pin, unblocks the pin cell and creates a path outward from the
        component center. This ensures pins are reachable by the router.

        The escape route extends from the pin position outward (away from component
        center) for a few cells, creating a clear channel for routing.

        Args:
            comp: Component with pins
            cx: Component center X position
            cy: Component center Y position
        """
        for pin in comp.pins:
            # Compute absolute pin position
            pin_x = cx + pin.position[0]
            pin_y = cy + pin.position[1]

            # Convert to grid coordinates
            pin_gx, pin_gy = self._world_to_grid(pin_x, pin_y)

            # Determine escape direction (outward from component center)
            dx = pin.position[0]
            dy = pin.position[1]

            # Normalize to get primary direction
            if abs(dx) >= abs(dy):
                # Horizontal escape
                step_x = 1 if dx >= 0 else -1
                step_y = 0
            else:
                # Vertical escape
                step_x = 0
                step_y = 1 if dy >= 0 else -1

            # Create escape route: unblock pin cell and 2-3 cells in escape direction
            escape_length = max(3, int(2.0 / self.cell_size) + 1)  # At least 2mm

            for step in range(escape_length):
                gx = pin_gx + step * step_x
                gy = pin_gy + step * step_y

                # Bounds check
                if 0 <= gx < self.grid_size[0] and 0 <= gy < self.grid_size[1]:
                    # Unblock on all layers
                    for layer in range(self.num_layers):
                        self.occupancy = self.occupancy.at[gx, gy, layer].set(0)

    def _world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert world coordinates to grid coordinates."""
        gx = int((x - self.origin[0]) / self.cell_size)
        gy = int((y - self.origin[1]) / self.cell_size)
        return (
            max(0, min(gx, self.grid_size[0] - 1)),
            max(0, min(gy, self.grid_size[1] - 1)),
        )

    def _heuristic(self, a: GridCell, b: GridCell) -> float:
        """Manhattan distance heuristic for A*."""
        return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.layer - b.layer) * 2

    def _get_neighbors(self, cell: GridCell, allow_layer_change: bool = False) -> list[GridCell]:
        """Get valid neighboring cells for pathfinding."""
        neighbors: list[GridCell] = []

        # 4-connected neighbors on same layer
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = cell.x + dx, cell.y + dy
            if 0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]:
                # Check if free (0) - not blocked (1) or routed (2)
                if int(self.occupancy[nx, ny, cell.layer]) == 0:
                    neighbors.append(GridCell(nx, ny, cell.layer))

        # Layer transitions (vias)
        if allow_layer_change and self.num_layers > 1:
            for new_layer in range(self.num_layers):
                if new_layer != cell.layer:
                    if int(self.occupancy[cell.x, cell.y, new_layer]) == 0:
                        neighbors.append(GridCell(cell.x, cell.y, new_layer))

        return neighbors

    def find_path(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        layer: int = 0,
        allow_layer_change: bool = False,
    ) -> list[GridCell] | None:
        """Find path between two points using A*.

        Args:
            start: (x, y) start position in grid coordinates
            end: (x, y) end position in grid coordinates
            layer: Starting layer
            allow_layer_change: Whether to allow layer transitions

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
            for l in range(self.num_layers):
                if int(self.occupancy[end[0], end[1], l]) == 0:
                    end_cell = GridCell(end[0], end[1], l)
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

            for neighbor in self._get_neighbors(current, allow_layer_change):
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
            for l in range(self.num_layers):
                val = int(self.occupancy[gx, gy, l])
                if val == 1:  # Blocked
                    original_values.append((gx, gy, l, val))
                    self.occupancy = self.occupancy.at[gx, gy, l].set(0)

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
                from temper_placer.routing.layer_assignment import LayerAssignment, Layer

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
