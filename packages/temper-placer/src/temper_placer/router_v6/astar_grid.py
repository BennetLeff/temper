"""
Router V6: Grid helpers for A* pathfinding.

Part of temper-N6-U6 decomposition.
"""

from __future__ import annotations

import numpy as np

from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D


def _build_tht_pad_locations(pcb) -> set[tuple[float, float]]:
    """
    Build set of THT pad locations from parsed PCB data.

    Iterates through components and pins, checking pin.is_pth to find
    through-hole pads that can serve as layer transition points.

    Args:
        pcb: ParsedPCB object with components

    Returns:
        Set of (x, y) positions where THT pads exist (absolute coordinates)
    """

    from temper_placer.core.pin_geometry import pin_world_position

    tht_locations: set[tuple[float, float]] = set()

    if not hasattr(pcb, "components"):
        return tht_locations

    for comp in pcb.components:
        for pin in comp.pins:
            if getattr(pin, "is_pth", False):
                abs_pos = pin_world_position(pin, comp)
                pos = (round(abs_pos[0], 1), round(abs_pos[1], 1))
                tht_locations.add(pos)

    return tht_locations


def _extract_pad_centers_per_net(pcb) -> dict[str, list[tuple[float, float, float, str]]]:
    """
    Extract pad center coordinates, radius, and layer for each net.

    Returns dictionary mapping net_name -> list of (x, y, radius, layer) coordinates.
    radius is approximated as max(width, height) / 2.
    """
    from temper_placer.core.pin_geometry import (
        pin_world_layer,
        pin_world_position,
        pin_world_radius,
    )

    pad_info: dict[str, list[tuple[float, float, float, str]]] = {}

    if not hasattr(pcb, "components"):
        return pad_info

    for comp in pcb.components:
        if not comp.initial_position or not hasattr(comp, "pins"):
            continue

        for pin in comp.pins:
            if not pin.net:
                continue

            abs_pos = pin_world_position(pin, comp)
            radius = pin_world_radius(pin) or 0.5
            layer = pin_world_layer(pin)

            if pin.net not in pad_info:
                pad_info[pin.net] = []
            pad_info[pin.net].append((abs_pos[0], abs_pos[1], radius, layer))

    return pad_info


def _unblock_net_pads(
    net_name: str,
    pad_info: dict,
    grids: dict,
    inflation_mm: float = 0.0,
    escape_vias_map: dict[str, list[tuple[float, float, float]]] | None = None,
) -> list[tuple]:
    """
    Temporarily unblock pads for the given net.
    Returns restoration data: list of (grid, [(x, y, old_val)]).
    """
    restoration_data = []

    # Helper to unblock a circular region on given grids
    def unblock_circle(cx_world, cy_world, radius_mm, target_grids):
        for grid in target_grids:
            # Expansion MUST include inflation to bridge the 'moat'
            expansion = int(np.ceil((radius_mm + inflation_mm) / grid.cell_size)) + 1
            gx, gy = grid.world_to_grid(cx_world, cy_world)

            x_start = max(0, gx - expansion)
            x_end = min(grid.width_cells, gx + expansion + 1)
            y_start = max(0, gy - expansion)
            y_end = min(grid.height_cells, gy + expansion + 1)

            saved_cells = []
            effective_unblock_radius = radius_mm + inflation_mm - 0.01

            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    val = grid.grid[y, x]
                    if val == -1:  # Only unblock static obstacles
                        wx, wy = grid.grid_to_world(x, y)
                        dist = ((wx - cx_world) ** 2 + (wy - cy_world) ** 2) ** 0.5
                        if dist <= effective_unblock_radius:
                            saved_cells.append((x, y, val))
                            grid.grid[y, x] = 0

            if saved_cells:
                restoration_data.append((grid, saved_cells))

    if pad_info and net_name in pad_info:
        pads = pad_info[net_name]
        for px, py, radius, layer in pads:
            # Determine target grids
            target_grids = []
            if layer in ["All", "all"] or "*.Cu" in layer or "Through" in layer:
                target_grids = list(grids.values())
            elif layer in grids:
                target_grids = [grids[layer]]

            unblock_circle(px, py, radius, target_grids)

    # Also unblock escape vias (which are effectively THT pads for this net)
    if escape_vias_map and net_name in escape_vias_map:
        for vx, vy, diameter in escape_vias_map[net_name]:
            # Escape vias span ALL layers
            target_grids = list(grids.values())
            unblock_circle(vx, vy, diameter / 2.0, target_grids)

    return restoration_data


def _restore_net_pads(restoration_data):
    """Restore grid state after routing."""
    for grid, cells in restoration_data:
        for x, y, val in cells:
            # Only restore if it's still 0 (free).
            # If it's > 0, the router claimed it, so we leave it.
            if grid.grid[y, x] == 0:
                grid.grid[y, x] = val


def _is_at_tht_pad(
    position: tuple[float, float],
    tht_locations: set[tuple[float, float]],
    tolerance: float = 1.0,
) -> bool:
    """
    Check if position is at a THT pad.

    Args:
        position: (x, y) position to check
        tht_locations: Pre-built set of THT pad positions
        tolerance: Position matching tolerance in mm

    Returns:
        True if position is within tolerance of a THT pad
    """
    if not tht_locations:
        return False

    x, y = position
    for tht_x, tht_y in tht_locations:
        dist = ((x - tht_x) ** 2 + (y - tht_y) ** 2) ** 0.5
        if dist <= tolerance:
            return True

    return False


def _find_access_node(
    grid,
    pin_pos: tuple[float, float],
    net_id: int,
    search_radius_cells: int = 3,
) -> tuple[int, int] | None:
    """
    Find best grid access node for an off-grid pin position.

    Searches neighborhood for the closest grid point that is either free (0)
    or owned by the net (net_id).

    Args:
        grid: Occupancy grid
        pin_pos: (x, y) world coordinates of pin center
        net_id: Net ID (to allow passing through own obstacles)
        search_radius_cells: Radius to search around snapped grid point

    Returns:
        (x_grid, y_grid) of best access node, or None if no valid node found.
    """
    px, py = pin_pos
    cx, cy = grid.world_to_grid(px, py)

    best_node = None
    min_dist = float("inf")

    # Iterate neighborhood
    for dy in range(-search_radius_cells, search_radius_cells + 1):
        for dx in range(-search_radius_cells, search_radius_cells + 1):
            gx, gy = cx + dx, cy + dy

            if not (0 <= gx < grid.width_cells and 0 <= gy < grid.height_cells):
                continue

            # Check if grid point is free or owned by net
            # Note: We rely on _unblock_net_pads having cleared the area around the pin
            val = grid.grid[gy, gx]
            if val != 0 and val != net_id:
                continue

            # Calculate distance to exact pin position
            wx, wy = grid.grid_to_world(gx, gy)
            dist = ((wx - px) ** 2 + (wy - py) ** 2) ** 0.5

            if dist < min_dist:
                min_dist = dist
                best_node = (gx, gy)

    return best_node


def _identify_blocking_nets(channel_path, grids: list) -> set[int]:
    """Identify net IDs blocking the straight-line paths across all specified layers."""
    blockers = set()
    waypoints = channel_path.waypoints

    for i in range(len(waypoints) - 1):
        p1 = waypoints[i]
        p2 = waypoints[i + 1]

        # Check if segment is blocked on ANY of the grids
        for grid in grids:
            segment_blockers = grid.get_blocking_nets(p1, p2)
            blockers.update(segment_blockers)

    return blockers


def _mark_route_blocked(
    route_path: RoutePath | RoutePath3D,
    grids: dict,
    trace_width: float,
    clearance: float,
    net_id: int,
) -> None:
    """Mark a path blocked on its respective layer grids."""
    if isinstance(route_path, RoutePath3D):
        # Mark each segment on its specific layer
        for i in range(len(route_path.segments) - 1):
            p1 = route_path.segments[i]
            p2 = route_path.segments[i + 1]

            # Use layer from segment if it matches, otherwise fallback
            layer = p1[2]
            if layer in grids:
                grids[layer].mark_segment_blocked(
                    (p1[0], p1[1]), (p2[0], p2[1]), trace_width, clearance, net_id
                )

        # Mark vias on ALL layers (assuming they span the stackup for now)
        for vx, vy in route_path.via_positions:
            for grid in grids.values():
                grid.mark_via_blocked(vx, vy, 0.6, clearance, net_id)  # 0.6mm via dia
    else:
        # Legacy single-layer behavior
        if route_path.layer_name in grids:
            grids[route_path.layer_name].mark_path_blocked(
                route_path.coordinates, trace_width, clearance, net_id
            )


def _unmark_route_blocked(
    route_path: RoutePath | RoutePath3D,
    grids: dict,
    trace_width: float,
    clearance: float,
    net_id: int,
) -> None:
    """Unmark a path from its respective layer grids."""
    if isinstance(route_path, RoutePath3D):
        for i in range(len(route_path.segments) - 1):
            p1 = route_path.segments[i]
            p2 = route_path.segments[i + 1]
            layer = p1[2]
            if layer in grids:
                grids[layer].unmark_segment_blocked(
                    (p1[0], p1[1]), (p2[0], p2[1]), trace_width, clearance, net_id
                )

        # Unmark vias from all layers
        # (Assuming mark_via_blocked simply overwrites cells,
        # so we rely on net_id check inside unmark_point)
        for vx, vy in route_path.via_positions:
            for grid in grids.values():
                grid.unmark_path([(vx, vy), (vx, vy)], 0.6, clearance, net_id)
    else:
        if route_path.layer_name in grids:
            grids[route_path.layer_name].unmark_path(
                route_path.coordinates, trace_width, clearance, net_id
            )
