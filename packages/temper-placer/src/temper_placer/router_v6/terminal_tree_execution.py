"""Synthetic and production execution seam for planned all-pad trees.

Called from ``run_astar_pathfinding`` when all-pad tree routing is enabled.
Each Prim-planned edge is routed through the existing A* primitive, producing
distinct branch geometry rather than one serial path.  Multi-layer grids are
supported via shared-layer selection.
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.astar_core import RoutePath

# NOTE(circular): terminal_tree_execution imports _astar_route (private) from
# astar_pathfinding, and astar_pathfinding imports execute_terminal_tree lazily.
# The bidirectional coupling can be resolved by promoting _astar_route to public
# or accepting execute_terminal_tree as a callable parameter (temper-APC1-U2).
from temper_placer.router_v6.astar_pathfinding import _astar_route
from temper_placer.router_v6.channel_mapping import ChannelPath
from temper_placer.router_v6.connectivity import NetDisposition, PadIdentity
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge, TerminalTreePlan, TreeTerminal


@dataclass(frozen=True)
class TerminalTreeExecution:
    """Complete legal branches or a truthful first failed planned edge."""

    disposition: NetDisposition
    completed_edges: tuple[tuple[TerminalTreeEdge, RoutePath], ...]
    failed_edge: TerminalTreeEdge | None


def _pick_route_layer(
    source: TreeTerminal,
    target: TreeTerminal,
    single_grid_layer: str,
) -> str | None:
    """Return the preferred shared layer name for a tree edge, or ``None``.

    Layer selection prioritises the *source* terminal's declared order:
    the first declared layer that both terminals share wins.  When neither
    terminal declares layers (legacy single-grid callers), ``single_grid_layer``
    is used directly.
    """
    src = getattr(source, "layer_names", None)
    tgt = getattr(target, "layer_names", None)
    if src is None and tgt is None:
        shared = {single_grid_layer}
    else:
        src_set = set(src or ()) or {single_grid_layer}
        tgt_set = set(tgt or ()) or {single_grid_layer}
        shared = src_set & tgt_set
    if not shared:
        return None
    # Prefer the source's first declared layer; fall back to the
    # alphabetically-first shared layer when neither declares.
    if src:
        for candidate in src:
            if candidate in shared:
                return candidate
    return sorted(shared)[0]


def execute_terminal_tree(
    plan: TerminalTreePlan,
    pads: list[TreeTerminal] | tuple[TreeTerminal, ...],
    grid: OccupancyGrid | dict[str, OccupancyGrid],
    *,
    max_iter: int = 1_000_000,
    net_id: int = -1,
    trace_width: float = 0.0,
    clearance: float = 0.0,
) -> TerminalTreeExecution:
    """Execute plan edges through A* without direct/forced fallback geometry.

    Accepts either a single ``OccupancyGrid`` (backward-compatible, 2D only)
    or a ``dict[str, OccupancyGrid]`` for multi-layer routing.  With a dict,
    each edge picks the first shared layer between source and target terminals;
    edges with no shared layer fail immediately.

    With a positive ``net_id``, each accepted edge is immediately reserved.
    The scoped 2D A* ownership predicate then permits that same ID while
    continuing to reject all other occupied cells.  The default leaves the
    synthetic seam non-mutating for backwards-compatible unit tests.
    """
    grids: dict[str, OccupancyGrid] = (
        {grid.layer_name: grid} if isinstance(grid, OccupancyGrid) else grid
    )
    if not grids:
        raise ValueError("at least one occupancy grid is required")

    single_grid_layer = next(iter(grids.keys()))
    terminals: dict[PadIdentity, TreeTerminal] = {pad.identity: pad for pad in pads}
    completed: list[tuple[TerminalTreeEdge, RoutePath]] = []

    for edge in plan.edges:
        source = terminals[edge.source]
        target = terminals[edge.target]
        route_layer = _pick_route_layer(source, target, single_grid_layer)
        if route_layer is None:
            return TerminalTreeExecution(
                disposition=NetDisposition.INCOMPLETE,
                completed_edges=tuple(completed),
                failed_edge=edge,
            )
        active_grid = grids[route_layer]

        path, _fallback_count = _astar_route(
            edge.source.net,
            ChannelPath(
                net_name=edge.source.net,
                channel_sequence=[],
                waypoints=[
                    (source.center.x, source.center.y),
                    (target.center.x, target.center.y),
                ],
                total_length=0.0,
                preferred_layer=route_layer,
            ),
            active_grid,
            max_iter=max_iter,
            allow_forced_segments=False,
            net_id=net_id,
        )
        if path is None or path.forced_segment_count:
            return TerminalTreeExecution(
                disposition=NetDisposition.INCOMPLETE,
                completed_edges=tuple(completed),
                failed_edge=edge,
            )
        completed.append((edge, path))
        if net_id >= 0:
            active_grid.mark_path_blocked(
                path.coordinates, trace_width, clearance, net_id
            )
    return TerminalTreeExecution(
        disposition=NetDisposition.ROUTED,
        completed_edges=tuple(completed),
        failed_edge=None,
    )
