"""Synthetic-only execution seam for planned all-pad trees.

This is intentionally not called by the Router V6 pipeline.  It establishes
that a :mod:`terminal_tree` plan can be run through the existing legal A*
primitive while preserving each branch as distinct geometry.  Flattening a
tree into one serial path would fabricate inter-branch copper, so callers get
``(edge, RoutePath)`` pairs instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.astar_core import RoutePath
from temper_placer.router_v6.astar_pathfinding import _astar_route
from temper_placer.router_v6.channel_mapping import ChannelPath
from temper_placer.router_v6.connectivity import CopperPad, NetDisposition, PadIdentity
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge, TerminalTreePlan


@dataclass(frozen=True)
class TerminalTreeExecution:
    """Complete legal branches or a truthful first failed planned edge."""

    disposition: NetDisposition
    completed_edges: tuple[tuple[TerminalTreeEdge, RoutePath], ...]
    failed_edge: TerminalTreeEdge | None


def execute_terminal_tree(
    plan: TerminalTreePlan,
    pads: list[CopperPad] | tuple[CopperPad, ...],
    grid: OccupancyGrid,
    *,
    max_iter: int = 1_000_000,
) -> TerminalTreeExecution:
    """Execute plan edges through A* without direct/forced fallback geometry.

    Future pipeline code must reserve accepted edge copper and use it as the
    next component's legal attachment surface.  This spike does not mutate
    occupancy or production state; it only proves the edge contract.
    """
    terminals: dict[PadIdentity, CopperPad] = {pad.identity: pad for pad in pads}
    completed: list[tuple[TerminalTreeEdge, RoutePath]] = []
    for edge in plan.edges:
        source = terminals[edge.source].center
        target = terminals[edge.target].center
        path, _fallback_count = _astar_route(
            edge.source.net,
            ChannelPath(
                net_name=edge.source.net,
                channel_sequence=[],
                waypoints=[(source.x, source.y), (target.x, target.y)],
                total_length=0.0,
                preferred_layer=grid.layer_name,
            ),
            grid,
            max_iter=max_iter,
            allow_forced_segments=False,
        )
        if path is None or path.forced_segment_count:
            return TerminalTreeExecution(
                disposition=NetDisposition.INCOMPLETE,
                completed_edges=tuple(completed),
                failed_edge=edge,
            )
        completed.append((edge, path))
    return TerminalTreeExecution(
        disposition=NetDisposition.ROUTED,
        completed_edges=tuple(completed),
        failed_edge=None,
    )
