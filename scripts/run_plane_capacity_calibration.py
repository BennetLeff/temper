#!/usr/bin/env python3
"""
Experiment P2: Power Plane Capacity Calibration.

Measures the impact of power plane coverage on signal routing success.
Validates the trade-off between Power Integrity (more plane) and Signal Integrity (more channels).
"""

import random
import numpy as np
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.astar_pathfinding import (
    _astar_route,
    RoutePath,
    _astar_route_multilayer,
)
from dataclasses import dataclass


@dataclass
class MockChannelPath:
    waypoints: list[tuple[float, float]]
    preferred_layer: str


def run_trial(fill_ratio: float, n_nets: int) -> float:
    width = 5.0  # Reduced width to force congestion
    height = 10.0
    resolution = 0.1
    w_cells = int(width / resolution)
    h_cells = int(height / resolution)

    # 1. Create Grids
    grid_f = OccupancyGrid(
        "F.Cu", np.zeros((h_cells, w_cells), dtype=np.int16), (0, 0), resolution, w_cells, h_cells
    )
    grid_b = OccupancyGrid(
        "B.Cu", np.zeros((h_cells, w_cells), dtype=np.int16), (0, 0), resolution, w_cells, h_cells
    )
    grid_f.__post_init__()
    grid_b.__post_init__()
    all_grids = {"F.Cu": grid_f, "B.Cu": grid_b}

    # 2. Generate Plane on B.Cu
    # Simple model: Randomly block (1 - fill_ratio) of the board?
    # No, planes are usually contiguous.
    # We simulate a plane by marking everything as BLOCKED (-1) except cutouts?
    # Or marking Plane as VALID for GND but BLOCKED for Signals?
    # For Signal Routing, a GND Plane is an OBSTACLE unless we route *on* the plane?
    # Wait, if B.Cu is a GND Plane, signals CANNOT route on B.Cu.
    # So B.Cu capacity becomes 0 for signals.
    # But usually we allow signals to cut the plane (Swiss Cheese).
    # So we model the plane as "Filled Area" = Blocked for Signals.

    # Let's generate random "Swiss Cheese" holes.
    # Fill Ratio 0.8 means 80% is blocked.
    n_holes = int((1.0 - fill_ratio) * 50)  # arbitrary number of holes

    # Initialize B.Cu as full blocked
    if fill_ratio > 0:
        grid_b.grid.fill(-1)  # Plane covers everything

        # Punch holes
        if fill_ratio < 1.0:
            for _ in range(n_holes):
                # Random rect hole
                hx = random.randint(0, w_cells - 10)
                hy = random.randint(0, h_cells - 10)
                w = random.randint(5, 20)
                h = random.randint(2, 5)
                grid_b.grid[hy : hy + h, hx : hx + w] = 0  # Open for routing

    # 3. Route Nets (Layer Switching Allowed)
    # Start on F.Cu, End on F.Cu.
    # But F.Cu might get congested, forcing switch to B.Cu.
    # If B.Cu is filled, they can't switch.

    # THT everywhere
    tht_locs = set()
    for x in np.arange(0, width, 1.0):
        for y in np.arange(0, height, 1.0):
            tht_locs.add((x, y))

    success = 0
    pitch = height / (n_nets + 1)

    for i in range(n_nets):
        y = (i + 1) * pitch
        start = (0.5, y)
        end = (width - 0.5, y)
        channel_path = MockChannelPath([start, end], "F.Cu")

        # Route
        path = _astar_route_multilayer(
            f"Net{i}",
            channel_path,
            grid_f,
            grid_b,
            tht_locs,
            use_lazy_theta_star=False,  # Strict A*
        )

        if path and path.forced_segment_count == 0:
            success += 1
            # Mark usage
            from temper_placer.router_v6.occupancy_grid import mark_path_blocked_3d

            mark_path_blocked_3d(all_grids, path.segments, 0.2, 0.2, i + 1)

    return success / n_nets


def main():
    print("Experiment P2: Plane Capacity Calibration")
    print("-----------------------------------------")
    print(f"{'Plane Fill %':<15} | {'Nets':<5} | {'Success':<8}")
    print("-" * 40)

    # Route 20 nets (High demand for 20x10mm board on 1 layer?)
    # 20 nets * 0.4mm = 8mm width. Board height 10mm.
    # Fits on F.Cu alone? Yes, efficiency ~0.8.
    # So we need MORE nets to force layer usage.
    # Let's try N=30. Height 10mm. 30*0.4 = 12mm. > 10mm.
    # Must use B.Cu.

    n_nets = 30  # Requires > 2.5x F.Cu capacity

    for fill in [0.0, 0.2, 0.5, 0.8, 0.9, 1.0]:
        rates = [run_trial(fill, n_nets) for _ in range(3)]
        avg = sum(rates) / len(rates)
        print(f"{fill * 100:>3.0f}%            | {n_nets:<5} | {avg * 100:.0f}%")


if __name__ == "__main__":
    main()
