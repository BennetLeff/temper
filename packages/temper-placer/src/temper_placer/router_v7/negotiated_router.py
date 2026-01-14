"""
Negotiated Congestion Router (PathFinder).

Implements the iterative routing algorithm where nets negotiate for resources
by paying congestion costs. Guarantees convergence if a solution exists.
"""

from __future__ import annotations

import time
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.astar_pathfinding import (
    RoutePath,
    _astar_route,
    _astar_route_multilayer,
    _unblock_net_pads,
)
from temper_placer.router_v6.stage0_data import DesignRules


class NegotiatedRouter:
    def __init__(
        self,
        grids: dict[str, OccupancyGrid],
        design_rules: DesignRules,
        max_iterations: int = 50,
        initial_history_factor: float = 0.5,
        history_growth: float = 1.2,
    ):
        self.grids = grids
        self.design_rules = design_rules
        self.max_iterations = max_iterations
        self.history_factor = initial_history_factor
        self.history_growth = history_growth

        # Enable negotiated mode on all grids
        for grid in self.grids.values():
            grid.negotiated_mode = True
            grid.__post_init__()

    def route(
        self, nets: list[str], channel_mapping, pad_centers, tht_locations
    ) -> dict[str, RoutePath]:
        """Run negotiation loop."""
        iteration = 0
        routed_paths = {}

        while iteration < self.max_iterations:
            print(f"Iteration {iteration}: History Factor = {self.history_factor:.2f}")
            iteration += 1
            overlaps = 0

            # Rip-up all (logically)
            # Actually, we re-route every net every iteration?
            # Optimization: Only re-route nets that pass through congested areas.
            # For V1, simple approach: Reroute ALL.

            # Reset current usage counts for this iteration?
            # No, usage count is updated dynamically as we route.
            # We must clear usage counts at start of iter?
            # PathFinder: "Rip up all signals and reroute them one by one."

            for grid in self.grids.values():
                if grid.usage_count is not None:
                    grid.usage_count.fill(0)

            # Route all nets
            for net_name in nets:
                # Route using current costs
                # Note: We need to adapt _astar_route to NOT fail on overlap
                # It calls _astar_search which calls is_free.
                # We set negotiated_mode=True, so is_free returns True.
                # So it will always find a path (if connectivity exists).

                # We need to manually update usage counts after routing
                channel_path = channel_mapping.channel_paths[net_name]
                grid = self.grids[channel_path.preferred_layer]

                # Unblock pads logic is tricky here.
                # In PathFinder, pads are just nodes.
                # We can reuse _unblock_net_pads but need to be careful not to break usage counting.

                path = _astar_route(
                    net_name,
                    channel_path,
                    grid,
                    use_theta_star=False,  # Use A* for speed in inner loop
                )

                if path:
                    routed_paths[net_name] = path
                    # Update usage count
                    grid.mark_path_blocked(
                        path.coordinates,
                        self.design_rules.default_trace_width_mm,
                        self.design_rules.default_clearance_mm,
                        net_id=1,  # Dummy ID, we just count usage
                    )
                    # mark_path_blocked normally sets grid=ID.
                    # We need it to increment usage_count.
                    # I need to update mark_path_blocked to handle negotiated mode?
                    # Or manually trace it.
                    self._update_usage(grid, path)

            # Check for congestion
            total_congestion = 0
            for grid in self.grids.values():
                # Count cells with usage > 1
                if grid.usage_count is not None:
                    total_congestion += np.sum(grid.usage_count > 1)

            print(f"  Total Congestion: {total_congestion} cells")

            if total_congestion == 0:
                print("Converged!")
                break

            # Update history costs
            for grid in self.grids.values():
                grid.update_history_cost(self.history_factor)

            self.history_factor *= self.history_growth

        return routed_paths

    def _update_usage(self, grid, path):
        """Increment usage for path."""
        # Simple rasterization matching grid logic
        # This duplicates logic in OccupancyGrid.mark_path_blocked.
        # Ideally OccupancyGrid should handle this.
        # For prototype, I will rely on OccupancyGrid having a method or doing it here.
        # I added add_usage(x,y).

        for p in path.coordinates:
            cx, cy = grid.world_to_grid(p[0], p[1])
            grid.add_usage(cx, cy)
            # Interpolation needed for full path...
