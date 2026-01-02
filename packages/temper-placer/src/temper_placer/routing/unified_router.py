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

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Netlist
from temper_placer.routing import push_shove as ps
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.current_capacity_strategy import (
    CurrentCapacityStrategy,
    select_current_capacity_strategy,
    get_strategy_description,
)


def _euclidean_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Compute Euclidean distance between two points."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _order_pins_nearest_neighbor(pins: list[tuple[float, float]]) -> list[int]:
    """
    Order pins by nearest-neighbor traversal to minimize total wirelength.

    Starts from the first pin and greedily visits the nearest unvisited pin.

    Args:
        pins: List of (x, y) pin positions

    Returns:
        List of indices in optimal visiting order
    """
    n = len(pins)
    if n <= 2:
        return list(range(n))

    visited = [False] * n
    order = [0]  # Start from first pin
    visited[0] = True

    for _ in range(n - 1):
        current = order[-1]
        best_next = -1
        best_dist = float("inf")

        for j in range(n):
            if not visited[j]:
                dist = _euclidean_distance(pins[current], pins[j])
                if dist < best_dist:
                    best_dist = dist
                    best_next = j

        if best_next >= 0:
            order.append(best_next)
            visited[best_next] = True

    return order

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
        design_rules: Design rules with net class specifications
        maze_router: Maze router instance
        push_shove_grid: Push-shove grid state
        hypergraph: Physics-Aware Hypergraph (for strategy inference)
    """

    def __init__(
        self,
        board: Board,
        config: RoutingConfig | None = None,
        design_rules: DesignRules | None = None,
        hypergraph: "PhysicsHypergraph | None" = None,
    ):
        """Initialize unified router.

        Args:
            board: PCB board specification
            config: Routing configuration (uses defaults if None)
            design_rules: Design rules with net class specs (uses defaults if None)
            hypergraph: Physics-Aware Hypergraph for semantic routing.
        """
        self.board = board
        self.config = config or RoutingConfig()
        self.design_rules = design_rules or DesignRules()
        self.hypergraph = hypergraph

        # Initialize maze router
        self.maze_router = MazeRouter.from_board(board, cell_size_mm=self.config.maze_cell_size)

        # Initialize push-shove grid (lazily created on first use)
        self.push_shove_grid: ps.Grid | None = None
        self._routed_paths: list[ps.Path] = []

        # Cache for net class lookups
        self._net_class_cache: dict[str, str | None] = {}

    @classmethod
    def from_board(
        cls,
        board: Board,
        strategy: RoutingStrategy = RoutingStrategy.AUTO,
        design_rules: DesignRules | None = None,
        hypergraph: "PhysicsHypergraph | None" = None,
        **config_kwargs,
    ) -> "UnifiedRouter":
        """Create router from board with optional configuration.

        Args:
            board: PCB board specification
            strategy: Routing strategy
            design_rules: Design rules with net class specs
            hypergraph: Physics-Aware Hypergraph.
            **config_kwargs: Additional configuration parameters

        Returns:
            Configured unified router
        """
        config = RoutingConfig(strategy=strategy, **config_kwargs)
        return cls(board, config, design_rules, hypergraph)

    def _init_push_shove_grid(self):
        """Initialize push-shove grid if not already created."""
        if self.push_shove_grid is None:
            # Convert board dimensions to grid cells
            grid_width = int(self.board.width / self.config.maze_cell_size)
            grid_height = int(self.board.height / self.config.maze_cell_size)
            num_layers = 2  # TODO: Get from board spec

            self.push_shove_grid = ps.Grid(width=grid_width, height=grid_height, layers=num_layers)

    def _maze_route_net(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
        cost_map: Array | None = None,
    ) -> UnifiedRoutePath:
        """Route net using maze router.

        Args:
            net_name: Net name
            pin_positions: Pin positions in world coordinates
            assignment: Layer assignment
            cost_map: Optional semantic cost map.

        Returns:
            Unified route path result
        """
        result = self.maze_router.route_net(net_name, pin_positions, assignment, cost_map=cost_map)

        return UnifiedRoutePath(
            net=net_name,
            success=result.success,
            cells=result.cells,
            length=result.length,
            via_count=result.via_count,
            method="maze",
            failure_reason=result.failure_reason,
        )

    def _route_two_pins_push_shove(
        self,
        net_name: str,
        start_pos: tuple[float, float],
        end_pos: tuple[float, float],
        assignment: "LayerAssignment",
        trace_width: float = 0.2,
        trace_clearance: float = 0.2,
    ) -> tuple[list[ps.Segment], int, str | None]:
        """
        Route between two pins using push-shove pathfinding.

        Args:
            net_name: Net name
            start_pos: Start position in world coordinates
            end_pos: End position in world coordinates
            assignment: Layer assignment
            trace_width: Trace width in mm
            trace_clearance: Trace clearance in mm

        Returns:
            (segments, via_count, failure_reason)
            failure_reason is None on success
        """
        from temper_placer.routing.layer_assignment import Layer

        layer = 0 if assignment.primary_layer == Layer.L1_TOP else 1
        allow_via = len(assignment.allowed_layers) > 1

        start_grid = self.maze_router._world_to_grid(start_pos[0], start_pos[1])
        end_grid = self.maze_router._world_to_grid(end_pos[0], end_pos[1])

        start_cell = ps.GridCell(start_grid[0], start_grid[1], layer)
        end_cell = ps.GridCell(end_grid[0], end_grid[1], layer)

        path_result = ps.find_path(
            self.push_shove_grid, start_cell, end_cell, allow_layer_change=allow_via
        )

        if not path_result.success:
            return [], 0, "No path found"

        # Convert grid path to segments
        segments = []
        for i in range(len(path_result.path) - 1):
            cell1 = path_result.path[i]
            cell2 = path_result.path[i + 1]

            x1 = cell1.x * self.config.maze_cell_size
            y1 = cell1.y * self.config.maze_cell_size
            x2 = cell2.x * self.config.maze_cell_size
            y2 = cell2.y * self.config.maze_cell_size

            segments.append(ps.Segment(start=(x1, y1), end=(x2, y2)))

        # Count vias
        via_count = sum(
            1
            for i in range(len(path_result.path) - 1)
            if path_result.path[i].layer != path_result.path[i + 1].layer
        )

        return segments, via_count, None

    def _get_net_rules(self, net_name: str, net_class: str | None = None) -> NetClassRules:
        """Get routing rules for a net.

        Args:
            net_name: Net name
            net_class: Optional net class (if known from netlist)

        Returns:
            NetClassRules for this net
        """
        return self.design_rules.get_rules_for_net(net_name, net_class)

    def _push_shove_route_net(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
        net_class: str | None = None,
    ) -> UnifiedRoutePath:
        """Route net using push-shove router with multi-pin support.

        For multi-pin nets, uses chain topology with nearest-neighbor ordering
        to minimize total wirelength. Uses design rules for trace parameters.

        Args:
            net_name: Net name
            pin_positions: Pin positions in world coordinates
            assignment: Layer assignment
            net_class: Optional net class for design rule lookup

        Returns:
            Unified route path result
        """
        self._init_push_shove_grid()

        if len(pin_positions) < 2:
            return UnifiedRoutePath(net=net_name, success=True, method="push-shove")

        # Get routing rules for this net
        rules = self._get_net_rules(net_name, net_class)

        # Order pins using nearest-neighbor heuristic for better wirelength
        pin_order = _order_pins_nearest_neighbor(pin_positions)
        ordered_pins = [pin_positions[i] for i in pin_order]

        # Route chain: pin0 -> pin1 -> pin2 -> ... -> pinN
        all_segments: list[ps.Segment] = []
        total_vias = 0
        total_length = 0.0

        for i in range(len(ordered_pins) - 1):
            start_pos = ordered_pins[i]
            end_pos = ordered_pins[i + 1]

            segments, via_count, failure_reason = self._route_two_pins_push_shove(
                net_name,
                start_pos,
                end_pos,
                assignment,
                trace_width=rules.trace_width,
                trace_clearance=rules.clearance,
            )

            if failure_reason is not None:
                return UnifiedRoutePath(
                    net=net_name,
                    success=False,
                    method="push-shove",
                    failure_reason=f"Failed segment {i} ({pin_order[i]}->{pin_order[i+1]}): {failure_reason}",
                )

            all_segments.extend(segments)
            total_vias += via_count
            total_length += _euclidean_distance(start_pos, end_pos)

        if not all_segments:
            return UnifiedRoutePath(
                net=net_name,
                success=False,
                method="push-shove",
                failure_reason="No segments created",
            )

        # Create combined path using net class rules for trace parameters
        path = ps.Path(
            segments=tuple(all_segments),
            width=rules.trace_width,
            clearance=rules.clearance,
            net=net_name,
        )

        # Check for collisions with existing paths
        collisions = []
        for existing_path in self._routed_paths:
            if ps.detect_collision(
                path, existing_path, samples_per_mm=2.0 # Updated to use adaptive signature
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
            for j, old_path in enumerate(collisions):
                idx = self._routed_paths.index(old_path)
                self._routed_paths[idx] = shove_result.paths[j]

        # Add successfully routed path
        self._routed_paths.append(path)

        return UnifiedRoutePath(
            net=net_name,
            success=True,
            path=path,
            length=total_length,
            via_count=total_vias,
            method="push-shove",
        )

    def route_net(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
        cost_map: Array | None = None,
        zones: list = None,  # NEW: Zone list for current capacity strategy
    ) -> UnifiedRoutePath:
        """Route a single net using configured strategy.

        Args:
            net_name: Net name
            pin_positions: Pin positions in world coordinates
            assignment: Layer assignment
            cost_map: Optional semantic cost map.
            zones: List of zones for current capacity strategy selection

        Returns:
            Unified routing result
        """
        # Current Capacity Strategy Selection (Phase 2/3 - temper-au2n/mm7z)
        # Determines routing method based on current requirements
        if zones is not None:
            try:
                capacity_strategy = select_current_capacity_strategy(
                    net_name, self.design_rules, zones
                )
                
                if capacity_strategy == CurrentCapacityStrategy.PLANE_VIA_ONLY:
                    # Phase 3 (temper-mm7z): Use PlaneConnectionRouter for high-current nets
                    from temper_placer.routing.plane_connection import PlaneConnectionRouter
                    
                    plane_router = PlaneConnectionRouter(
                        design_rules=self.design_rules,
                        cell_size_mm=self.config.maze_cell_size,
                    )
                    
                    connections = plane_router.route_net_to_plane(
                        net_name=net_name,
                        pin_positions=pin_positions,
                        zones=zones,
                    )
                    
                    # Check if all connections succeeded
                    all_success = all(c.success for c in connections)
                    if not all_success:
                        failures = [c for c in connections if not c.success]
                        failure_reasons = "; ".join(c.failure_reason for c in failures if c.failure_reason)
                        return UnifiedRoutePath(
                            net=net_name,
                            success=False,
                            method="plane_connection",
                            failure_reason=f"Plane connection failed: {failure_reasons}",
                        )
                    
                    # Success: Return plane connection result
                    # Via count is total vias across all connections
                    total_vias = sum(len(c.via_positions) for c in connections)
                    
                    return UnifiedRoutePath(
                        net=net_name,
                        success=True,
                        method="plane_connection",
                        via_count=total_vias,
                        length=0.0,  # No traced length (plane carries current)
                    )
                    
            except RuntimeError as e:
                # High-current net without zone - should have been caught in config validation
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Current capacity validation failed for '{net_name}': {e}")
                return UnifiedRoutePath(
                    net=net_name,
                    success=False,
                    method="error",
                    failure_reason=str(e),
                )
        
        # Standard routing strategy dispatch (existing logic)
        if self.config.strategy == RoutingStrategy.MAZE_ONLY:
            return self._maze_route_net(net_name, pin_positions, assignment, cost_map=cost_map)

        elif self.config.strategy == RoutingStrategy.PUSH_SHOVE_ONLY:
            return self._push_shove_route_net(net_name, pin_positions, assignment)

        elif self.config.strategy == RoutingStrategy.AUTO:
            # Try maze first
            result = self._maze_route_net(net_name, pin_positions, assignment, cost_map=cost_map)

            if result.success:
                return result

            # Fallback to push-shove
            ps_result = self._push_shove_route_net(net_name, pin_positions, assignment)
            return ps_result

        elif self.config.strategy == RoutingStrategy.HYBRID:
            # Try both and pick best
            maze_result = self._maze_route_net(net_name, pin_positions, assignment, cost_map=cost_map)
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
        from temper_placer.routing.bridge.api import get_routing_context, get_cost_map_for_net
        from temper_placer.routing.bridge.types import RoutingStrategy as BridgeStrategy

        # 1. Infer Routing Context if Hypergraph available
        context = None
        if self.hypergraph is not None:
            context = get_routing_context(self.hypergraph, positions, self.board, netlist)

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

            # 2. Apply Semantic Strategy
            cost_map = None
            if context:
                # Check for Flood Fill (skip routing)
                if context.get_strategy(net_name) == BridgeStrategy.FLOOD_FILL:
                    results[net_name] = UnifiedRoutePath(
                        net=net_name, success=True, method="deferred", failure_reason="Flood Fill"
                    )
                    continue
                
                # Get dynamic cost map
                cost_map = get_cost_map_for_net(
                    grid_size=self.maze_router.grid_size,
                    cell_size_mm=self.maze_router.cell_size,
                    context=context,
                    net_id=net_name
                )

            result = self.route_net(net_name, pin_positions, assignment, cost_map=cost_map)
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
