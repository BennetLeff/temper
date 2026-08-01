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

from dataclasses import dataclass, field

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

#: ``failure_reasons`` prefix for an edge whose terminals share no conductive
#: layer at all — a genuine geometry gap that needs a via-aware transition.
NO_SHARED_LAYER = "no_shared_layer"

#: ``failure_reasons`` prefix for an edge whose terminals *do* share a
#: conductive layer, but the router was handed no occupancy grid for it.
#: This is a router configuration gap, not a board geometry one, and it is
#: reported separately so it can never be mistaken for congestion.
NO_ROUTABLE_LAYER = "no_routable_layer"


@dataclass(frozen=True)
class TerminalTreeExecution:
    """Complete legal branches or a truthful report of failed planned edges."""

    disposition: NetDisposition
    completed_edges: tuple[tuple[TerminalTreeEdge, RoutePath], ...]
    failed_edges: tuple[TerminalTreeEdge, ...] = ()
    #: Per-edge diagnostic for everything in ``failed_edges``.  Edges that
    #: failed inside A* carry no entry; layer-selection failures always do,
    #: so an unroutable-layer edge is never indistinguishable from a
    #: congested one.
    failure_reasons: dict[TerminalTreeEdge, str] = field(default_factory=dict)


def _shared_pad_layers(
    source: TreeTerminal,
    target: TreeTerminal,
    single_grid_layer: str,
) -> tuple[str, ...]:
    """Conductive layers both terminals sit on, in preference order.

    Source declaration order wins (a PTH pad listing ``("F.Cu", "B.Cu")``
    prefers ``F.Cu``); any remaining shared layers follow in sorted order so
    the result is deterministic.  Terminals that declare no layers at all
    (synthetic fixtures) fall back to the single-grid layer, preserving the
    executor's original single-grid behaviour.
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
        return ()
    ordered = [candidate for candidate in (src or ()) if candidate in shared]
    ordered.extend(sorted(shared.difference(ordered)))
    return tuple(ordered)


def _pick_route_layer(
    source: TreeTerminal,
    target: TreeTerminal,
    single_grid_layer: str,
    routable_layers: frozenset[str],
) -> str | None:
    """Return a layer both terminals sit on *that the router can route on*.

    ``routable_layers`` is the set of layers with an occupancy grid.  Without
    that intersection the executor would hand ``grids[...]`` a layer it was
    never given — the ``KeyError: 'F.Cu'`` this guard exists to prevent, which
    fires whenever a board's outer layers are classified as poured planes
    (``_parse_board.py``) so only inner layers get routing spaces, while SMD
    terminals still, correctly, declare their physical outer pad layer.

    Filtering here can only ever reject an edge whose shared layers have *no*
    occupancy grid — the router cannot route those under any policy.  It never
    rejects work that some other layer choice could have completed, so it
    cannot silently lower completion.  Routing such an edge on an arbitrary
    grid-backed layer instead was measured and rejected: it raises reported
    completion while leaving copper that does not touch the pads (see
    ``docs/evidence/2026-07-28-tree-executor-grid-layer-mismatch.md``).
    """
    for candidate in _shared_pad_layers(source, target, single_grid_layer):
        if candidate in routable_layers:
            return candidate
    return None


def _describe_layer_failure(
    source: TreeTerminal,
    target: TreeTerminal,
    single_grid_layer: str,
    routable_layers: frozenset[str],
) -> str:
    """Name the layers involved so a rejected edge is never a bare failure.

    Distinguishes the two causes: terminals that share no layer at all
    (``NO_SHARED_LAYER`` — needs via-aware transitions) from terminals that
    share one the router holds no occupancy grid for (``NO_ROUTABLE_LAYER``
    — needs the grid, or an explicit layer-transition policy).
    """
    shared = _shared_pad_layers(source, target, single_grid_layer)
    grids_text = sorted(routable_layers)
    if not shared:
        return (
            f"{NO_SHARED_LAYER}: source={list(getattr(source, 'layer_names', ()) or ())} "
            f"target={list(getattr(target, 'layer_names', ()) or ())} "
            f"grids={grids_text}"
        )
    return (
        f"{NO_ROUTABLE_LAYER}: pads share {list(shared)} but no occupancy grid "
        f"exists for any of them; grids={grids_text}"
    )


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
    routable_layers = frozenset(grids)
    terminals: dict[PadIdentity, TreeTerminal] = {pad.identity: pad for pad in pads}
    completed: list[tuple[TerminalTreeEdge, RoutePath]] = []
    failed: list[TerminalTreeEdge] = []
    failure_reasons: dict[TerminalTreeEdge, str] = {}
    connected: set[PadIdentity] = {plan.root}

    for edge in plan.edges:
        source = terminals[edge.source]
        target = terminals[edge.target]

        # U2: skip edges whose source was never reached.
        if edge.source not in connected:
            continue

        route_layer = _pick_route_layer(source, target, single_grid_layer, routable_layers)
        if route_layer is None:
            failed.append(edge)
            failure_reasons[edge] = _describe_layer_failure(
                source, target, single_grid_layer, routable_layers
            )
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
            active_grid.mark_path_blocked(path.coordinates, trace_width, clearance, net_id)

    disposition = (
        NetDisposition.ROUTED if len(connected) == len(terminals) else NetDisposition.INCOMPLETE
    )
    return TerminalTreeExecution(
        disposition=disposition,
        completed_edges=tuple(completed),
        failed_edges=tuple(failed),
        failure_reasons=failure_reasons,
    )
