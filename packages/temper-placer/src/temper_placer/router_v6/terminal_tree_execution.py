"""Synthetic and production execution seam for planned all-pad trees.

Called from ``run_astar_pathfinding`` when all-pad tree routing is enabled.
Each Prim-planned edge is routed through the existing A* primitive, producing
distinct branch geometry rather than one serial path.  Multi-layer grids are
supported via shared-layer selection.

U2 (2026-07-20): subtree-aware resilience — a single infeasible edge no
longer abandons the entire net.  Edges whose source terminal is actually
connected to the root (via completed edges) are attempted; edges descended
from a failed edge are skipped to avoid wasting grid budget on disconnected
branches.  ``verify_net_connectivity`` remains the sole authority for
``ROUTED`` vs ``INCOMPLETE``.
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
    """Complete legal branches or a truthful report of failed planned edges."""

    disposition: NetDisposition
    completed_edges: tuple[tuple[TerminalTreeEdge, RoutePath], ...]
    failed_edges: tuple[TerminalTreeEdge, ...] = ()


def _pick_route_layer(
    source: TreeTerminal,
    target: TreeTerminal,
    single_grid_layer: str,
) -> str | None:
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

    U2: subtree-aware resilience.  Tracks which terminals are *actually*
    connected to the root (via successfully routed edges), not just
    planned-connected.  An edge whose source is not in the connected set
    is skipped (it descended from an earlier failure).  After all edges
    are attempted, ``verify_net_connectivity`` determines the final
    disposition — the executor itself never fabricates a verdict.
    """
    grids: dict[str, OccupancyGrid] = (
        {grid.layer_name: grid} if isinstance(grid, OccupancyGrid) else grid
    )
    if not grids:
        raise ValueError("at least one occupancy grid is required")

    single_grid_layer = next(iter(grids.keys()))
    terminals: dict[PadIdentity, TreeTerminal] = {pad.identity: pad for pad in pads}
    completed: list[tuple[TerminalTreeEdge, RoutePath]] = []
    failed: list[TerminalTreeEdge] = []
    connected: set[PadIdentity] = {plan.root}

    for edge in plan.edges:
        source = terminals[edge.source]
        target = terminals[edge.target]

        # U2: skip edges whose source was never reached.
        if edge.source not in connected:
            continue

        route_layer = _pick_route_layer(source, target, single_grid_layer)
        if route_layer is None:
            failed.append(edge)
            continue

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
            failed.append(edge)
            continue

        completed.append((edge, path))
        connected.add(edge.target)
        if net_id >= 0:
            active_grid.mark_path_blocked(
                path.coordinates, trace_width, clearance, net_id
            )

    disposition = (
        NetDisposition.ROUTED
        if len(connected) == len(terminals)
        else NetDisposition.INCOMPLETE
    )
    return TerminalTreeExecution(
        disposition=disposition,
        completed_edges=tuple(completed),
        failed_edges=tuple(failed),
    )
