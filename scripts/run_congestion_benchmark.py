#!/usr/bin/env python3
"""
Experiment C1: The Congestion Benchmark.

Tests the Negotiated Congestion (PathFinder) solver on a synthetic bottleneck.
"""

import time
import numpy as np
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v7.negotiated_router import NegotiatedRouter
from temper_placer.router_v6.astar_pathfinding import _astar_route
from temper_placer.router_v6.stage0_data import DesignRules
from dataclasses import dataclass


@dataclass
class MockChannelPath:
    waypoints: list[tuple[float, float]]
    preferred_layer: str


@dataclass
class MockChannelMapping:
    channel_paths: dict


def run_experiment():
    print("Experiment C1: Congestion Benchmark")
    print("-----------------------------------")

    # 1. Setup Environment
    # 10x10 Grid.
    # Bottleneck at x=5 (width 1 cell).
    # All other x=5 cells blocked.
    grid_size = 20
    grid = np.zeros((grid_size, grid_size), dtype=np.int16)

    # Block middle column except y=10
    grid[:, 10] = -1  # Static block
    grid[10, 10] = 0  # Bridge
    grid[2, 10] = 0  # Detour (Open before init)

    occ_grid = OccupancyGrid(
        layer_name="F.Cu",
        grid=grid,
        origin=(0, 0),
        cell_size=1.0,
        width_cells=grid_size,
        height_cells=grid_size,
        static_mask=(grid == -1),
    )
    occ_grid.__post_init__()

    grids = {"F.Cu": occ_grid}

    # 2. Setup Demand
    # 5 Nets trying to cross from x=0 to x=19
    # They ALL want to go through (10, 10) because it's the only gap.
    # But Capacity is 1.
    # PathFinder should let them overlap initially, then penalize.
    # Since there is NO other path, they will stack and pay huge cost.
    # To test convergence, we need an ALTERNATIVE path.
    # Let's open another bridge at y=2, but it's longer path.
    grid[2, 10] = 0

    nets = ["Net1", "Net2", "Net3", "Net4", "Net5"]
    channel_paths = {}
    for i, net in enumerate(nets):
        # Start at (0, 10), End at (19, 10)
        # Optimal path is straight through (10, 10).
        channel_paths[net] = MockChannelPath(
            waypoints=[(0.0, 10.0), (19.0, 10.0)], preferred_layer="F.Cu"
        )

    mapping = MockChannelMapping(channel_paths)

    # 3. Run Router
    print("Running Negotiated Router...")

    rules = DesignRules(
        net_classes={},
        net_class_assignments={},
        default_clearance_mm=0.2,
        default_trace_width_mm=0.5,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
    )

    router = NegotiatedRouter(
        grids=grids,
        design_rules=rules,
        max_iterations=30,  # Increased
        initial_history_factor=0.5,
    )

    # Mock pads/tht
    routed = router.route(nets, mapping, {}, {})

    print(f"\nRouted {len(routed)} nets.")

    # Analyze usage of the two bridges
    bridge_main = occ_grid.usage_count[10, 10]
    bridge_detour = occ_grid.usage_count[2, 10]

    print(f"Main Bridge (10,10) Usage: {bridge_main}")
    print(f"Detour Bridge (2,10) Usage: {bridge_detour}")

    if bridge_main > 1:
        print("FAIL: Congestion not resolved (Main bridge overloaded)")
    elif bridge_detour == 0:
        print("FAIL: Detour not used")
    else:
        print("SUCCESS: Traffic distributed!")

    # Debug: Verify Detour Usability
    print("\nDebug: Verifying Detour Validity...")
    # Block main bridge completely
    occ_grid.grid[10, 10] = -1

    # Reset usage count logic to avoid confusion
    occ_grid.negotiated_mode = False

    # Route 1 net
    path = _astar_route(
        "DebugNet", channel_paths["Net1"], occ_grid, use_lazy_theta_star=False
    )  # Check Standard A*

    if path:
        print("Detour is reachable!")
        # Check if it used the detour
        used_detour = False
        for p in path.coordinates:
            # Check Y coordinate near 2.0
            if abs(p[1] - 2.5) < 2.0:
                used_detour = True
        if used_detour:
            print("Path confirmed through detour.")
        else:
            print("Path found but not through detour? Impossible.")
    else:
        print("Detour is UNREACHABLE. Geometry error.")


if __name__ == "__main__":
    run_experiment()
