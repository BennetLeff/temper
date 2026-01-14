#!/usr/bin/env python3
"""
Debug Differential Pair Routing.

Isolates the USB_D+/- routing problem to identify why it fails.
"""

import sys
import math
from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.obstacle_map import build_obstacle_map
from temper_placer.router_v6.occupancy_grid import build_occupancy_grid
from temper_placer.router_v6.routing_space import compute_routing_space
from temper_placer.router_v7.diff_pair_router import DiffPairRouter
from temper_placer.router_v6.astar_pathfinding import _extract_pad_centers_per_net


def main():
    pcb_path = Path("pcb/temper.kicad_pcb")
    print(f"Loading {pcb_path}...")
    pcb = parse_kicad_pcb_v6(pcb_path)

    # 1. Build Grid (F.Cu)
    print("Building Grid...")
    # Use simple bounds for speed
    all_x = [c.initial_position[0] for c in pcb.components if c.initial_position]
    all_y = [c.initial_position[1] for c in pcb.components if c.initial_position]
    bounds = (min(all_x) - 5, min(all_y) - 5, max(all_x) + 5, max(all_y) + 5)

    # Obstacles
    escape_vias = []

    # Exclude BOTH nets
    print("Building Obstacles (Excluding USB_D+, USB_D-)...")
    obstacles = build_obstacle_map(pcb, escape_vias, exclude_nets=["USB_D+", "USB_D-"])
    fcu_obs = obstacles.get("F.Cu")

    # Routing Space
    # Create RoutingSpace object manually to avoid full pipeline overhead
    # Need to import Polygon
    from shapely.geometry import Polygon, MultiPolygon

    if not fcu_obs:
        fcu_obs = MultiPolygon()

    # RoutingSpace constructor: layer_name, available_area, total_area, obstacle_area, routing_area, obstacles
    from temper_placer.router_v6.routing_space import RoutingSpace

    # Mock available area as box minus obstacles
    from shapely.geometry import box

    board_poly = box(*bounds)
    avail = board_poly.difference(fcu_obs)

    rs = RoutingSpace("F.Cu", avail, 0, 0, 0, obstacles=fcu_obs)

    # Occupancy Grid
    # base_inflation = width/2 + clearance = 0.1 + 0.2 = 0.3
    # Use 0.1mm cell size
    # We must ensure resolution matches pipeline
    grid = build_occupancy_grid(rs, inflation_mm=0.3)
    grid.negotiated_mode = False  # Strict

    # 2. Extract Pads
    pad_centers = _extract_pad_centers_per_net(pcb)
    p_pads = pad_centers.get("USB_D+", [])
    n_pads = pad_centers.get("USB_D-", [])

    print(f"USB_D+: {len(p_pads)} pads")
    print(f"USB_D-: {len(n_pads)} pads")

    if len(p_pads) != 2:
        print("Error: Net doesn't have 2 pads")
        return

    # 3. Match Pads
    p1, p2 = p_pads[0], p_pads[1]
    n1, n2 = n_pads[0], n_pads[1]

    # Dist p1-n1
    d11 = (p1[0] - n1[0]) ** 2 + (p1[1] - n1[1]) ** 2
    d12 = (p1[0] - n2[0]) ** 2 + (p1[1] - n2[1]) ** 2

    if d11 < d12:
        start_p, start_n = p1, n1
        end_p, end_n = p2, n2
    else:
        start_p, start_n = p1, n2
        end_p, end_n = p2, n1

    print(f"Start P: ({start_p[0]:.2f}, {start_p[1]:.2f})")
    print(f"Start N: ({start_n[0]:.2f}, {start_n[1]:.2f})")
    print(f"End P: ({end_p[0]:.2f}, {end_p[1]:.2f})")
    print(f"End N: ({end_n[0]:.2f}, {end_n[1]:.2f})")

    # 4. Check Validity at Start
    router = DiffPairRouter(grid)

    width = 0.2
    gap = 0.2

    # Test Fanout routing
    print("Attempting Route...")
    result = router.route_pair_with_fanout(
        (start_p[0], start_p[1]),
        (start_n[0], start_n[1]),
        (end_p[0], end_p[1]),
        (end_n[0], end_n[1]),
        width,
        gap,
    )

    if result:
        print("SUCCESS!")
    else:
        print("FAILED.")

        # Diagnostics
        # Check if Start points are blocked
        sp_x, sp_y = grid.world_to_grid(start_p[0], start_p[1])
        sn_x, sn_y = grid.world_to_grid(start_n[0], start_n[1])
        print(f"Grid at Start P: {grid.grid[sp_y, sp_x]}")
        print(f"Grid at Start N: {grid.grid[sp_y, sp_x]}")  # Should be 0 if free

        # If -1, it's blocked.
        # If blocked, it's because pads are treated as obstacles!


if __name__ == "__main__":
    main()
