# mypy: ignore-errors
"""Router V6: A* search execution and segment-level search strategies.

The search core: dispatching a single segment search, the coarse-to-fine
corridor strategy, and the two-layer / multilayer / rip-up-and-reroute
route builders. Callers hand these a grid and waypoints and get back a
path or an honest refusal; none of them own net selection or
result aggregation, which live in _astar_reconstruct.py.

Split out of _astar_reconstruct.py, which had grown past its size cap.
"""

from __future__ import annotations

from temper_placer.router_v6._astar_theta_star import (
    _astar_search_lazy_theta_star,
    _astar_search_theta_star,
)
from temper_placer.router_v6.astar_core import (
    RoutePath,
    RoutePath3D,
    _astar_search,
    _route_segment_3d,
    append_exact_terminal_point,
    append_grid_path_point,
    grid_quantization_tolerance,
)
from temper_placer.router_v6.astar_grid import _identify_blocking_nets
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules

# U2 (docs/plans/2026-07-18-003-*): explicit iteration bound for the
# third-tier ``_route_segment_3d`` fallback call in
# ``_astar_route_multilayer``. Passed explicitly (rather than relying
# solely on ``_route_segment_3d``'s own default) so the bound used at
# this specific call site is visible and independently tunable here.
# See astar_core.py's ``_ROUTE_SEGMENT_3D_DEFAULT_MAX_ITER`` docstring
# for the reasoning behind this order of magnitude.
_SEGMENT_3D_FALLBACK_MAX_ITER = 200_000
# Experimental all-terminal trees may invoke the 3D fallback once per edge.
# Keep that expensive retry bounded until production evidence justifies a
# larger search budget; two-pad routing deliberately retains the value above.
_TREE_SEGMENT_3D_FALLBACK_MAX_ITER = 10_000
_MAX_REROUTE_ATTEMPTS_PER_NET = 2


def _has_safe_partial_geometry(path: RoutePath | RoutePath3D) -> bool:
    """A partial result must contain actual A* geometry, never a forced edge."""
    points = path.segments if isinstance(path, RoutePath3D) else path.coordinates
    return len(points) >= 2 and path.path_length > 0.0


def _in_bounds(grid: OccupancyGrid, point: tuple[int, int]) -> bool:
    return 0 <= point[0] < grid.width_cells and 0 <= point[1] < grid.height_cells


def _dispatch_search(
    grid,
    start,
    goal,
    use_theta_star: bool,
    use_lazy_theta_star: bool,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_congestion_derivative: bool = True,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    net_id: int = -1,
):
    if use_lazy_theta_star:
        return _astar_search_lazy_theta_star(
            grid,
            start,
            goal,
            net_id=net_id,
            max_iter=max_iter,
            enable_congestion_derivative=enable_congestion_derivative,
        )
    if use_theta_star:
        return _astar_search_theta_star(
            grid,
            start,
            goal,
            net_id=net_id,
            max_iter=max_iter,
            enable_congestion_derivative=enable_congestion_derivative,
        )
    # 2D plain A*.  Delegate to the Rust-backed kernel
    # (astar_core_numba._astar_search_numba, cleanup C1).  Falls through
    # to the pure-Python _astar_search when the extension is missing.
    if net_id >= 0:
        # The Rust kernel consumes a binary validity tensor and cannot
        # distinguish committed copper belonging to this net.  Tree edges use
        # the reference search so same-net attachment remains legal.
        return _astar_search(start, goal, grid, net_id=net_id)

    from temper_placer.router_v6.astar_core_numba import (
        _astar_search_numba,
    )

    # U7 / R11: thread the optional congestion tensor through.  The
    # kernel reads it as a flat float32 array per expansion.
    kwargs = {"max_iterations": max_iter}
    if thermal_flat is not None:
        kwargs["thermal_flat"] = thermal_flat
        kwargs["thermal_weight"] = thermal_weight
    if congestion_tensor is not None:
        kwargs["congestion_flat"] = congestion_tensor.array.reshape(-1)
        kwargs["congestion_weight"] = congestion_tensor.weight
        kwargs["max_congestion_cost"] = congestion_tensor.max_cost
    return _astar_search_numba(start, goal, grid, **kwargs)


def _segment_search(
    grid: OccupancyGrid,
    start_world: tuple[float, float],
    goal_world: tuple[float, float],
    use_theta_star: bool,
    use_lazy_theta_star: bool,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    enable_congestion_derivative: bool = True,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    net_id: int = -1,
) -> tuple[list | None, OccupancyGrid, int]:
    """Run A* between two world-coordinate waypoints on ``grid``.

    Returns ``(path, grid, fallback_count)`` where ``path`` is a list
    of grid cells or ``None``, ``grid`` is the grid searched, and
    ``fallback_count`` is 1 if coarse-to-fine fell back to unrestricted
    A* (0 otherwise).
    """
    start = grid.world_to_grid(*start_world)
    goal = grid.world_to_grid(*goal_world)
    if not _in_bounds(grid, start) or not _in_bounds(grid, goal):
        return None, grid, 0

    if enable_coarse_to_fine and net_id < 0:
        return _segment_search_coarse_to_fine(
            grid,
            start,
            goal,
            use_theta_star,
            use_lazy_theta_star,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            congestion_tensor=congestion_tensor,
            max_iter=max_iter,
            enable_congestion_derivative=enable_congestion_derivative,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
        )

    path = _dispatch_search(
        grid,
        start,
        goal,
        use_theta_star,
        use_lazy_theta_star,
        congestion_tensor=congestion_tensor,
        max_iter=max_iter,
        enable_congestion_derivative=enable_congestion_derivative,
        thermal_flat=thermal_flat,
        thermal_weight=thermal_weight,
        net_id=net_id,
    )
    return path, grid, 0


def _segment_search_coarse_to_fine(
    grid: OccupancyGrid,
    start: tuple[int, int],
    goal: tuple[int, int],
    use_theta_star: bool,
    use_lazy_theta_star: bool,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_congestion_derivative: bool = True,
    thermal_flat=None,
    thermal_weight: float = 0.0,
) -> tuple[list | None, OccupancyGrid, int]:
    """Coarse-to-fine corridor routing.

    1. Downsample grid to coarse resolution.
    2. Run plain A* on coarse grid.
    3. Extract corridor mask from coarse path.
    4. Run constrained fine A* within corridor.
    5. Fall back to unrestricted A* on any failure.
    """
    from temper_placer.router_v6.astar_core_numba import _astar_search_numba
    from temper_placer.router_v6.corridor import extract_corridor_mask
    from temper_placer.router_v6.neighbor_validity import (
        build_neighbor_validity_tensor_2d,
    )

    coarse_grid = grid.downsample(factor=coarse_factor)

    coarse_start = (start[0] // coarse_factor, start[1] // coarse_factor)
    coarse_goal = (goal[0] // coarse_factor, goal[1] // coarse_factor)

    coarse_path = _astar_search_numba(coarse_start, coarse_goal, coarse_grid)

    if coarse_path is not None:
        corridor_mask = extract_corridor_mask(
            coarse_path,
            coarse_factor=coarse_factor,
            buffer_cells=corridor_buffer_cells,
            fine_rows=grid.height_cells,
            fine_cols=grid.width_cells,
        )
        if corridor_mask[start[1], start[0]] and corridor_mask[goal[1], goal[0]]:
            neighbor_tensor = build_neighbor_validity_tensor_2d(grid, corridor_mask=corridor_mask)
            fine_path = _astar_search_numba(
                start,
                goal,
                grid,
                neighbor_tensor=neighbor_tensor,
                max_iterations=max_iter,
            )
            if fine_path is not None:
                return fine_path, grid, 0

    path = _dispatch_search(
        grid,
        start,
        goal,
        use_theta_star,
        use_lazy_theta_star,
        congestion_tensor=congestion_tensor,
        max_iter=max_iter,
        enable_congestion_derivative=enable_congestion_derivative,
        thermal_flat=thermal_flat,
        thermal_weight=thermal_weight,
    )
    return path, grid, 1


def _astar_route(
    net_name: str,
    channel_path,
    grid: OccupancyGrid,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
    max_iter: int = 1_000_000,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    allow_forced_segments: bool = True,
    net_id: int = -1,
) -> tuple[RoutePath | None, int]:
    """
    Route a single net using A* or Theta* pathfinding.

    Returns:
        (RoutePath or None, coarse_to_fine_fallback_count)
    """
    waypoints = channel_path.waypoints
    if len(waypoints) < 2:
        return None, 0

    detailed_coords: list[tuple[float, float]] = []
    forced_segments = 0
    failed_waypoint_indices: list[int] = []
    fallback_count = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        grid_path, _, fb = _segment_search(
            grid,
            start_world,
            goal_world,
            use_theta_star,
            use_lazy_theta_star,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
            net_id=net_id,
        )
        fallback_count += fb

        if grid_path:
            tolerance = grid_quantization_tolerance(grid.cell_size)
            if i == 0:
                detailed_coords.append(start_world)
            for grid_cell in grid_path:
                world_coord = grid.grid_to_world(grid_cell[0], grid_cell[1])
                append_grid_path_point(detailed_coords, world_coord, tolerance)
            # A multi-terminal fallback is a serial incremental tree; every
            # target must be an actual path node, not merely the next search
            # start coordinate. Snap onto the exact terminal rather than
            # duplicating it next to the last (approximate) grid-cell
            # center -- see astar_core.append_exact_terminal_point.
            append_exact_terminal_point(detailed_coords, goal_world, tolerance)
        else:
            if not allow_forced_segments:
                failed_waypoint_indices.append(i + 1)
                path_length = sum(
                    ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
                    for p1, p2 in zip(detailed_coords, detailed_coords[1:])
                )
                return RoutePath(
                    net_name=net_name,
                    coordinates=detailed_coords,
                    layer_name=grid.layer_name,
                    path_length=path_length,
                    forced_segment_count=1,
                    failed_waypoint_indices=failed_waypoint_indices,
                ), fallback_count
            if i == 0:
                detailed_coords.append(start_world)
            detailed_coords.append(goal_world)
            forced_segments += 1
            failed_waypoint_indices.append(i + 1)

    if not detailed_coords:
        detailed_coords = list(waypoints)
        forced_segments = len(waypoints) - 1

    path_length = sum(
        ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        for p1, p2 in zip(detailed_coords, detailed_coords[1:])
    )

    return RoutePath(
        net_name=net_name,
        coordinates=detailed_coords,
        layer_name=grid.layer_name,
        path_length=path_length,
        forced_segment_count=forced_segments,
        failed_waypoint_indices=failed_waypoint_indices,
    ), fallback_count


def _astar_route_multilayer(
    net_name: str,
    channel_path,
    primary_grid: OccupancyGrid,
    alternate_grid: OccupancyGrid | None,
    tht_locations: set[tuple[float, float]] | None,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    enable_congestion_derivative: bool = True,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    net_id: int = 0,
    design_rules: DesignRules | None = None,
    allow_forced_segments: bool = True,
    segment_3d_fallback_max_iter: int = _SEGMENT_3D_FALLBACK_MAX_ITER,
) -> tuple[RoutePath3D | None, int]:
    """
    Route a single net with per-segment layer switching at THT pads.

    For each waypoint pair:
    1. Try routing on primary grid
    2. If it fails AND waypoints are at THT pads, try alternate grid
    3. U2: if that also fails (or is unavailable), try ``_route_segment_3d``
       (the 3D via-aware A* search) as a last-resort fallback tier --
       see docs/plans/2026-07-18-003-feat-via-aware-layer-transitions-plan.md
    4. Stitch segments together

    Args:
        net_id: Real net id (>0) for the net being routed, used only by
            the U2 fallback tier below so any via it places is actually
            blocked against later nets via ``mark_via_blocked()``.
            Defaults to 0 (no via-blocking protection) for backward
            compatibility with any caller that doesn't have a net id
            available yet -- production callers should always pass a
            real net_id.
        design_rules: Per-netclass rules used only by the 3D fallback to
            reserve each candidate via at its resolved diameter and clearance.

    Returns:
        (RoutePath3D or None, coarse_to_fine_fallback_count)
    """
    waypoints = channel_path.waypoints
    if len(waypoints) < 2:
        return None, 0

    detailed_segments: list[tuple[float, float, str]] = []
    via_positions: list[tuple[float, float]] = []
    forced_segments = 0
    failed_waypoint_indices: list[int] = []
    fallback_count = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        segment_path, grid_to_use, fb = _segment_search(
            primary_grid,
            start_world,
            goal_world,
            use_theta_star,
            use_lazy_theta_star,
            congestion_tensor=congestion_tensor,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            enable_congestion_derivative=enable_congestion_derivative,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
        )
        fallback_count += fb

        # The alternate-grid route is a genuine B.Cu detour, not an implicit
        # layer change.  Preserve the established route-search tier, while
        # spelling out F.Cu -> B.Cu at its start and B.Cu -> F.Cu at its end
        # so ``via_positions`` and the writer have a physically connected
        # path to emit.  The historical code returned only B.Cu points here,
        # relying on the presence of any THT pad elsewhere on the board.
        if not segment_path and alternate_grid and tht_locations:
            alt_start = alternate_grid.world_to_grid(*start_world)
            alt_goal = alternate_grid.world_to_grid(*goal_world)
            if _in_bounds(alternate_grid, alt_start) and _in_bounds(alternate_grid, alt_goal):
                alternate_path, _unused_grid, fb2 = _segment_search(
                    alternate_grid,
                    start_world,
                    goal_world,
                    use_theta_star,
                    use_lazy_theta_star,
                    congestion_tensor=congestion_tensor,
                    max_iter=max_iter,
                    enable_coarse_to_fine=enable_coarse_to_fine,
                    coarse_factor=coarse_factor,
                    corridor_buffer_cells=corridor_buffer_cells,
                    enable_congestion_derivative=enable_congestion_derivative,
                    thermal_flat=thermal_flat,
                    thermal_weight=thermal_weight,
                )
                fallback_count += fb2
                if alternate_path:
                    primary_layer = primary_grid.layer_name
                    alternate_layer = alternate_grid.layer_name
                    alt_tolerance = grid_quantization_tolerance(alternate_grid.cell_size)
                    if i == 0:
                        detailed_segments.append((start_world[0], start_world[1], primary_layer))
                    # Real via (layer change at identical x, y) -- never
                    # merged, append_grid_path_point/append_exact_terminal_point
                    # only merge same-layer points.
                    detailed_segments.append((start_world[0], start_world[1], alternate_layer))
                    for node in alternate_path:
                        if hasattr(node, "layer_name"):
                            wx, wy = alternate_grid.grid_to_world(node.x, node.y)
                            append_grid_path_point(
                                detailed_segments, (wx, wy, node.layer_name), alt_tolerance
                            )
                        else:
                            wx, wy = alternate_grid.grid_to_world(node[0], node[1])
                            append_grid_path_point(
                                detailed_segments, (wx, wy, alternate_layer), alt_tolerance
                            )
                    append_exact_terminal_point(
                        detailed_segments, (goal_world[0], goal_world[1], alternate_layer), alt_tolerance
                    )
                    detailed_segments.append((goal_world[0], goal_world[1], primary_layer))
                    via_positions.extend((start_world, goal_world))
                    continue

        if segment_path:
            layer_name = grid_to_use.layer_name
            tolerance = grid_quantization_tolerance(grid_to_use.cell_size)
            if i == 0:
                detailed_segments.append((start_world[0], start_world[1], layer_name))

            for node in segment_path:
                if hasattr(node, "layer_name"):
                    wx, wy = grid_to_use.grid_to_world(node.x, node.y)
                    append_grid_path_point(detailed_segments, (wx, wy, node.layer_name), tolerance)
                else:
                    wx, wy = grid_to_use.grid_to_world(node[0], node[1])
                    append_grid_path_point(detailed_segments, (wx, wy, layer_name), tolerance)

            # Preserve every terminal explicitly.  Without this, consecutive
            # grid paths can stop at adjacent cell centres and silently omit
            # an intermediate pad from the emitted copper chain. Snap onto
            # the exact terminal instead of duplicating it next to the
            # last (approximate) grid-cell center -- that duplication is
            # what generated a spurious acid-trap-shaped vertex at nearly
            # every waypoint; see astar_core.append_exact_terminal_point
            # and docs/evidence/2026-07-27-acid-trap-elimination.md.
            append_exact_terminal_point(detailed_segments, (goal_world[0], goal_world[1], layer_name), tolerance)
            continue

        # U2 (docs/plans/2026-07-18-003-*): via-aware fallback tier. Both
        # the primary-grid attempt and the explicitly anchored alternate-grid
        # retry above have failed, so use the existing property-tested 3D A*
        # implementation as a last resort.  It records and blocks each
        # actual via.
        # (``_route_segment_3d``) as a last resort before giving up and
        # forcing a direct (unrouted) segment. This is additive: it only
        # runs when ``segment_path`` is still falsy at this point, so
        # segments that already succeeded on the primary/alternate grid
        # never reach this branch (see
        # test_astar_route_multilayer_via_fallback.py's regression test).
        grids_3d: dict[str, OccupancyGrid] = {primary_grid.layer_name: primary_grid}
        if alternate_grid is not None:
            grids_3d[alternate_grid.layer_name] = alternate_grid

        # Both endpoints are nominally on the primary grid's layer --
        # matching the "Fallback: add direct segment" branch below and
        # the primary-grid search attempt above. The 3D search is free
        # to detour through any other layer in ``grids_3d`` internally
        # (and back) to escape local congestion; a real via is recorded
        # (and grid-blocked, given a real net_id) for every such detour.
        fallback_layer = primary_grid.layer_name
        net_rules = design_rules.get_rules_for_net(net_name) if design_rules else None
        result_3d = _route_segment_3d(
            start_world,
            goal_world,
            fallback_layer,
            fallback_layer,
            grids_3d,
            via_cost=10.0,
            via_diameter=net_rules.via_diameter_mm if net_rules else 0.6,
            clearance=net_rules.clearance_mm if net_rules else 0.2,
            net_id=net_id,
            max_iter=segment_3d_fallback_max_iter,
        )

        if result_3d is not None:
            world_path_3d, via_positions_3d = result_3d
            via_positions.extend(via_positions_3d)
            if i == 0:
                detailed_segments.append(world_path_3d[0])
            detailed_segments.extend(world_path_3d[1:])
            continue

        if not allow_forced_segments:
            failed_waypoint_indices.append(i + 1)
            path_length = sum(
                ((s2[0] - s1[0]) ** 2 + (s2[1] - s1[1]) ** 2) ** 0.5
                for s1, s2 in zip(detailed_segments, detailed_segments[1:])
            )
            return RoutePath3D(
                net_name=net_name,
                segments=detailed_segments,
                via_positions=via_positions,
                path_length=path_length,
                via_count=len(via_positions),
                forced_segment_count=1,
                failed_waypoint_indices=failed_waypoint_indices,
            ), fallback_count

        # Legacy two-pad compatibility fallback: add a direct segment.
        forced_segments += 1
        failed_waypoint_indices.append(i + 1)
        if i == 0:
            detailed_segments.append((start_world[0], start_world[1], primary_grid.layer_name))
        detailed_segments.append((goal_world[0], goal_world[1], primary_grid.layer_name))

    path_length = sum(
        ((s2[0] - s1[0]) ** 2 + (s2[1] - s1[1]) ** 2) ** 0.5
        for s1, s2 in zip(detailed_segments, detailed_segments[1:])
    )

    return RoutePath3D(
        net_name=net_name,
        segments=detailed_segments,
        via_positions=via_positions,
        path_length=path_length,
        via_count=len(via_positions),
        forced_segment_count=forced_segments,
        failed_waypoint_indices=failed_waypoint_indices,
    ), fallback_count


def _astar_route_with_ripup(
    net_name: str,
    channel_path,
    grid: OccupancyGrid,
    _design_rules: DesignRules,
    net_ids: dict[str, int],
    alternate_grid: OccupancyGrid | None = None,
    tht_locations: set[tuple[float, float]] | None = None,
    all_grids: dict[str, OccupancyGrid] | None = None,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    allow_forced_segments: bool = True,
    segment_3d_fallback_max_iter: int = _SEGMENT_3D_FALLBACK_MAX_ITER,
) -> tuple[RoutePath | RoutePath3D | None, list[int], int]:
    """
    Route a net, potentially ripping up blocking nets.

    If alternate_grid and components are provided, uses multilayer routing
    with layer switching at any pad (THT preferred when available).

    Returns:
        (RoutePath, list_of_net_ids_to_rip, coarse_to_fine_fallback_count)
    """
    # Try multilayer routing if alternate grid available.  The
    # ``tht_locations`` gate is no longer required: layer switching at
    # SMD pads is enabled when an alternate grid exists.  When THT pads
    # are present they remain the preferred layer-switch site (handled
    # inside ``_astar_route_multilayer``).
    path: RoutePath | RoutePath3D | None
    fallback_count = 0
    if alternate_grid:
        # U2: real net_id, threaded through to the ``_route_segment_3d``
        # fallback tier so any via it places is actually blocked via
        # ``mark_via_blocked()`` (which requires net_id > 0). Falls back
        # to 0 (no protection) only if the net isn't in the id map, which
        # should not happen for any net reaching this call site.
        net_id = net_ids.get(net_name, 0)
        path, fb = _astar_route_multilayer(
            net_name,
            channel_path,
            grid,
            alternate_grid,
            tht_locations,
            use_theta_star,
            use_lazy_theta_star,
            congestion_tensor=congestion_tensor,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
            net_id=net_id,
            design_rules=_design_rules,
            allow_forced_segments=allow_forced_segments,
            segment_3d_fallback_max_iter=segment_3d_fallback_max_iter,
        )
        fallback_count += fb
    else:
        path, fb = _astar_route(
            net_name,
            channel_path,
            grid,
            use_theta_star,
            use_lazy_theta_star,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
            allow_forced_segments=allow_forced_segments,
        )
        fallback_count += fb

    if path and path.forced_segment_count == 0:
        return path, [], fallback_count

    # Identify blockers if forced
    if path and path.forced_segment_count > 0:
        # Check ALL grids for blockers if available, otherwise just current grid
        target_grids = list(all_grids.values()) if all_grids else [grid]
        blockers = _identify_blocking_nets(channel_path, target_grids)
        if blockers:
            return path, list(blockers), fallback_count

    return path, [], fallback_count
