"""
Unified routing API that integrates maze router and push-shove router.

This module provides a high-level routing interface that:
1. Tries maze router first (fast, grid-based)
2. Falls back to push-shove router if maze router fails
3. Provides configuration for routing strategy selection
4. Maintains compatibility with existing routing infrastructure

Example usage:
    >>> from temper_placer.routing.unified_router import UnifiedRouter, RoutingStrategy
    >>>
    >>> router = UnifiedRouter.from_board(board, strategy=RoutingStrategy.AUTO)
    >>> results = router.route_all_nets(netlist, positions, net_order, assignments)
    >>> print(f"Completion rate: {router.get_completion_rate(results):.1%}")
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.routing.maze_router import MazeRouter, RoutePath
from temper_placer.routing import push_shove as ps

if TYPE_CHECKING:
    from temper_placer.routing.layer_assignment import LayerAssignment


class RoutingStrategy(Enum):
    """Routing strategy selection."""

    MAZE_ONLY = "maze_only"  # Only use maze router
    PUSH_SHOVE_ONLY = "push_shove_only"  # Only use push-shove router
    AUTO = "auto"  # Try maze first, fallback to push-shove
    HYBRID = "hybrid"  # Use both and pick best result


@dataclass
class RoutingConfig:
    """Configuration for unified routing.

    Attributes:
        strategy: Routing strategy to use
        maze_cell_size: Grid cell size for maze router (mm)
        push_shove_max_iterations: Max iterations for push-shove
        push_shove_num_samples: Samples per segment for collision detection
        enable_via: Whether to allow layer transitions
        prefer_push_shove_for_dense: Use push-shove for high-congestion areas
    """

    strategy: RoutingStrategy = RoutingStrategy.AUTO
    maze_cell_size: float = 1.0
    push_shove_max_iterations: int = 10
    push_shove_num_samples: int = 20
    enable_via: bool = True
    prefer_push_shove_for_dense: bool = False


@dataclass
class UnifiedRoutePath:
    """Unified routing result that includes method used.

    Attributes:
        net: Net name
        success: Whether routing succeeded
        cells: Grid cells (if using maze router)
        path: Continuous path (if using push-shove)
        length: Path length
        via_count: Number of vias/layer transitions
        method: Which router was used ('maze' or 'push-shove')
        failure_reason: Why routing failed (if unsuccessful)
    """

    net: str
    success: bool
    cells: list | None = None  # For maze router
    path: ps.Path | None = None  # For push-shove router
    length: float = 0.0
    via_count: int = 0
    method: str = "unknown"
    failure_reason: str | None = None

    def __post_init__(self):
        if self.cells is None:
            self.cells = []


class UnifiedRouter:
    """Unified router that integrates maze and push-shove routing.

    This router provides a single interface that can use either:
    - Maze router (fast, grid-based, good for sparse layouts)
    - Push-shove router (precise, SDF-based, good for dense layouts)
    - Automatic fallback (tries maze first, then push-shove)

    Attributes:
        board: PCB board specification
        config: Routing configuration
        maze_router: Maze router instance
        push_shove_grid: Push-shove grid state
    """

    def __init__(self, board: Board, config: RoutingConfig | None = None):
        """Initialize unified router.

        Args:
            board: PCB board specification
            config: Routing configuration (uses defaults if None)
        """
        self.board = board
        self.config = config or RoutingConfig()

        # Initialize maze router
        self.maze_router = MazeRouter.from_board(board, cell_size_mm=self.config.maze_cell_size)

        # Initialize push-shove grid (lazily created on first use)
        self.push_shove_grid: ps.Grid | None = None
        self._routed_paths: list[ps.Path] = []

    @classmethod
    def from_board(
        cls, board: Board, strategy: RoutingStrategy = RoutingStrategy.AUTO, **config_kwargs
    ) -> "UnifiedRouter":
        """Create router from board with optional configuration.

        Args:
            board: PCB board specification
            strategy: Routing strategy
            **config_kwargs: Additional configuration parameters

        Returns:
            Configured unified router
        """
        config = RoutingConfig(strategy=strategy, **config_kwargs)
        return cls(board, config)

    def _init_push_shove_grid(self):
        """Initialize push-shove grid if not already created."""
        if self.push_shove_grid is None:
            # Convert board dimensions to grid cells
            grid_width = int(self.board.width / self.config.maze_cell_size)
            grid_height = int(self.board.height / self.config.maze_cell_size)
            num_layers = 2  # TODO: Get from board spec

            self.push_shove_grid = ps.Grid(width=grid_width, height=grid_height, layers=num_layers)

    def _maze_route_net(
        self, net_name: str, pin_positions: list[tuple[float, float]], assignment: "LayerAssignment"
    ) -> UnifiedRoutePath:
        """Route net using maze router.

        Args:
            net_name: Net name
            pin_positions: Pin positions in world coordinates
            assignment: Layer assignment

        Returns:
            Unified route path result
        """
        result = self.maze_router.route_net(net_name, pin_positions, assignment)

        return UnifiedRoutePath(
            net=net_name,
            success=result.success,
            cells=result.cells,
            length=result.length,
            via_count=result.via_count,
            method="maze",
            failure_reason=result.failure_reason,
        )

    def _push_shove_route_net(
        self, net_name: str, pin_positions: list[tuple[float, float]], assignment: "LayerAssignment"
    ) -> UnifiedRoutePath:
        """Route net using push-shove router.

        Args:
            net_name: Net name
            pin_positions: Pin positions in world coordinates
            assignment: Layer assignment

        Returns:
            Unified route path result
        """
        self._init_push_shove_grid()

        # For now, fall back to maze router pathfinding to find initial path
        # Then use push-shove if there are conflicts
        # TODO: Implement pure push-shove pathfinding

        from temper_placer.routing.layer_assignment import Layer

        if len(pin_positions) < 2:
            return UnifiedRoutePath(net=net_name, success=True, method="push-shove")

        # Use maze router to find initial path
        layer = 0 if assignment.primary_layer == Layer.L1_TOP else 1
        allow_via = len(assignment.allowed_layers) > 1

        grid_pins = [self.maze_router._world_to_grid(x, y) for x, y in pin_positions]
        start_grid = grid_pins[0]
        end_grid = grid_pins[1]  # Simple 2-pin for now

        # Find path on push-shove grid
        start_cell = ps.GridCell(start_grid[0], start_grid[1], layer)
        end_cell = ps.GridCell(end_grid[0], end_grid[1], layer)

        path_result = ps.find_path(
            self.push_shove_grid, start_cell, end_cell, allow_layer_change=allow_via
        )

        if not path_result.success:
            return UnifiedRoutePath(
                net=net_name, success=False, method="push-shove", failure_reason="No path found"
            )

        # Convert grid path to continuous path
        # TODO: Implement proper grid-to-path conversion
        # For now, create a simple path
        segments = []
        for i in range(len(path_result.path) - 1):
            cell1 = path_result.path[i]
            cell2 = path_result.path[i + 1]

            # Convert grid to world coordinates
            x1 = cell1.x * self.config.maze_cell_size
            y1 = cell1.y * self.config.maze_cell_size
            x2 = cell2.x * self.config.maze_cell_size
            y2 = cell2.y * self.config.maze_cell_size

            segments.append(ps.Segment(start=(x1, y1), end=(x2, y2)))

        path = ps.Path(
            segments=tuple(segments),
            width=0.2,  # TODO: Get from net class
            clearance=0.2,  # TODO: Get from design rules
            net=net_name,
        )

        # Check for collisions with existing paths
        collisions = []
        for existing_path in self._routed_paths:
            if ps.detect_collision(
                path, existing_path, num_samples=self.config.push_shove_num_samples
            ):
                collisions.append(existing_path)

        # If collisions, try to shove
        if collisions:
            shove_result = ps.shove_paths(
                collisions,
                path,
                board_bounds=(self.board.width, self.board.height),
                max_iterations=self.config.push_shove_max_iterations,
            )

            if not shove_result.success:
                return UnifiedRoutePath(
                    net=net_name,
                    success=False,
                    method="push-shove",
                    failure_reason="Could not shove conflicting paths",
                )

            # Update existing paths
            for i, old_path in enumerate(collisions):
                idx = self._routed_paths.index(old_path)
                self._routed_paths[idx] = shove_result.paths[i]

        # Add successfully routed path
        self._routed_paths.append(path)

        # Count vias
        via_count = sum(
            1
            for i in range(len(path_result.path) - 1)
            if path_result.path[i].layer != path_result.path[i + 1].layer
        )

        return UnifiedRoutePath(
            net=net_name,
            success=True,
            path=path,
            length=path_result.cost,
            via_count=via_count,
            method="push-shove",
        )

    def route_net(
        self, net_name: str, pin_positions: list[tuple[float, float]], assignment: "LayerAssignment"
    ) -> UnifiedRoutePath:
        """Route a single net using configured strategy.

        Args:
            net_name: Net name
            pin_positions: Pin positions in world coordinates
            assignment: Layer assignment

        Returns:
            Unified routing result
        """
        if self.config.strategy == RoutingStrategy.MAZE_ONLY:
            return self._maze_route_net(net_name, pin_positions, assignment)

        elif self.config.strategy == RoutingStrategy.PUSH_SHOVE_ONLY:
            return self._push_shove_route_net(net_name, pin_positions, assignment)

        elif self.config.strategy == RoutingStrategy.AUTO:
            # Try maze first
            result = self._maze_route_net(net_name, pin_positions, assignment)

            if result.success:
                return result

            # Fallback to push-shove
            ps_result = self._push_shove_route_net(net_name, pin_positions, assignment)
            return ps_result

        elif self.config.strategy == RoutingStrategy.HYBRID:
            # Try both and pick best
            maze_result = self._maze_route_net(net_name, pin_positions, assignment)
            ps_result = self._push_shove_route_net(net_name, pin_positions, assignment)

            # Pick based on success and path length
            if maze_result.success and ps_result.success:
                return maze_result if maze_result.length <= ps_result.length else ps_result
            elif maze_result.success:
                return maze_result
            elif ps_result.success:
                return ps_result
            else:
                return maze_result  # Return maze result with failure reason

        else:
            raise ValueError(f"Unknown routing strategy: {self.config.strategy}")

    def route_all_nets(
        self,
        netlist: Netlist,
        positions: Array,
        net_order: list[str],
        assignments: dict[str, "LayerAssignment"],
    ) -> dict[str, UnifiedRoutePath]:
        """Route all nets in priority order.

        Args:
            netlist: Circuit netlist
            positions: Component positions
            net_order: Net routing order (priority)
            assignments: Layer assignments per net

        Returns:
            Dictionary of net name -> routing result
        """
        # Block components in both routers
        self.maze_router.block_components(netlist.components, positions)

        # Route each net
        results = {}
        for net_name in net_order:
            net = next((n for n in netlist.nets if n.name == net_name), None)
            if net is None:
                continue

            # Get pin positions
            pin_positions = []
            for comp_ref, pin_name in net.pins:
                comp = next((c for c in netlist.components if c.ref == comp_ref), None)
                if comp is None:
                    continue

                pin = comp.get_pin(pin_name)
                if pin is None:
                    continue

                comp_idx = netlist.components.index(comp)
                comp_pos = positions[comp_idx]

                pin_world = (
                    float(comp_pos[0]) + pin.position[0],
                    float(comp_pos[1]) + pin.position[1],
                )
                pin_positions.append(pin_world)

            if len(pin_positions) < 2:
                results[net_name] = UnifiedRoutePath(net=net_name, success=True, method="skip")
                continue

            assignment = assignments.get(net_name)
            if assignment is None:
                continue

            result = self.route_net(net_name, pin_positions, assignment)
            results[net_name] = result

        return results

    def get_completion_rate(self, results: dict[str, UnifiedRoutePath]) -> float:
        """Calculate routing completion rate.

        Args:
            results: Routing results

        Returns:
            Completion rate (0.0 to 1.0)
        """
        if not results:
            return 0.0

        successful = sum(1 for r in results.values() if r.success)
        return successful / len(results)

    def get_statistics(self, results: dict[str, UnifiedRoutePath]) -> dict:
        """Get routing statistics.

        Args:
            results: Routing results

        Returns:
            Dictionary of statistics
        """
        total = len(results)
        successful = sum(1 for r in results.values() if r.success)
        maze_count = sum(1 for r in results.values() if r.method == "maze")
        push_shove_count = sum(1 for r in results.values() if r.method == "push-shove")

        total_length = sum(r.length for r in results.values() if r.success)
        total_vias = sum(r.via_count for r in results.values() if r.success)

        return {
            "total_nets": total,
            "successful": successful,
            "failed": total - successful,
            "completion_rate": successful / total if total > 0 else 0.0,
            "maze_routed": maze_count,
            "push_shove_routed": push_shove_count,
            "total_length": total_length,
            "total_vias": total_vias,
            "avg_length": total_length / successful if successful > 0 else 0.0,
            "avg_vias": total_vias / successful if successful > 0 else 0.0,
        }
