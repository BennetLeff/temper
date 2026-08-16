"""
Router V6 Stage 4.1: Map Topology to Channels

Maps abstract topology graph to concrete routing channels.
Part of temper-qic1 (Stage 4 - Geometric Realization)

Phase E batch E4 (Rust Orchestration Engine plan 2026-08-09-001): the
orchestration — ``map_topology_to_channels`` / ``_map_net_to_channels`` /
``_extract_waypoints`` / ``_parse_channel_coordinate`` /
``_skeleton_nodes_in_coordinate_order`` / ``_assign_layer`` /
``_ssot_layer_for_net`` / ``_validated_two_pad_terminals`` /
``expand_channel_path_terminals`` / ``fallback_channel_path`` — moved to
``temper-orchestration``'s ``channel_mapping.rs``.  This module keeps its
full public API as a thin FFI delegation: the shim marshals the topology /
skeleton into plain tuples and wraps the Rust results back into the
``ChannelPath`` / ``ChannelMapping`` dataclasses (unchanged).  The leaf
kernels the orchestration drives (``_calculate_path_length`` /
``_nearest_skeleton_node`` / ``_is_near_skeleton`` /
``_nearest_terminal_order``) stay single-source in ``temper-geometry``.
The oracle is pinned verbatim as
``tests/router_v6/_channel_ops_py_oracle.py`` (content-hash registered in
``scripts/oracle_hashes.json``).
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg
import temper_orchestration as _to

from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.terminal_extraction import ParsedTerminal
from temper_placer.router_v6.terminal_tree import TerminalTreePlan
from temper_placer.router_v6.topology_extraction import NetTopology, TopologyGraph


def _flatten(points: list[tuple[float, float]]) -> list[float]:
    out = []
    for x, y in points:
        out.append(x)
        out.append(y)
    return out


@dataclass
class ChannelPath:
    """A path through routing channels."""

    net_name: str
    channel_sequence: list[str]  # Ordered list of channel IDs
    waypoints: list[tuple[float, float]]  # (x, y) coordinates along path
    total_length: float  # Total path length in mm
    preferred_layer: str = "F.Cu"  # Layer assignment for multi-layer routing
    terminal_tree: TerminalTreePlan | None = None
    terminals: tuple[ParsedTerminal, ...] = ()


# Map Layer enum (L1_TOP .. L4_BOT) → KiCad copper layer name (F.Cu .. B.Cu).
# Inner layers (In1.Cu / In2.Cu) are reference/power planes, not A* routing
# grids; nets assigned to them fall through to the heuristic.
_LAYER_ENUM_TO_KICAD: dict[int, str] = {
    1: "F.Cu",  # L1_TOP
    4: "B.Cu",  # L4_BOT
}


def _path_tuple(channel_path: ChannelPath) -> tuple:
    return (
        channel_path.net_name,
        list(channel_path.channel_sequence),
        list(channel_path.waypoints),
        channel_path.total_length,
        channel_path.preferred_layer,
    )


def expand_channel_path_terminals(
    channel_path: ChannelPath,
    pads: list[tuple[float, float]],
    *,
    enable_all_pad_tree: bool = False,
) -> ChannelPath:
    """Append physical terminals missing from a SAT/channel waypoint path.

    SAT waypoints remain in their original order, preserving their channel
    guidance.  For a multi-pad net, absent pad centres are appended in a
    stable order so the existing incremental A* chain must reach every
    conductive terminal.

    A 2-pad net is always validated against its own true pad positions
    (regardless of ``enable_all_pad_tree``) -- see
    ``_validated_two_pad_terminals`` -- and corrected if its SAT-derived
    endpoint(s) do not resolve to this net's own pads. This closes a
    measured Stage 3 defect (docs/evidence/2026-08-08-nlayer-via-astar-spike.md
    §2.4): the channel/topology extraction can hand this function a 2-pad
    net whose endpoint waypoint is not this net's pad at all but a
    physically adjacent pad of a *different* net, which Stage 4 A* would
    then treat as a required terminal and route real copper to.
    """
    if len(pads) == 2:
        result = _to.run_validated_two_pad_terminals(_path_tuple(channel_path), pads)
        if result is None:
            return channel_path
        corrected, total_length = result
        return ChannelPath(
            net_name=channel_path.net_name,
            channel_sequence=list(channel_path.channel_sequence),
            waypoints=corrected,
            total_length=total_length,
            preferred_layer=channel_path.preferred_layer,
            terminal_tree=channel_path.terminal_tree,
            terminals=channel_path.terminals,
        )
    if not enable_all_pad_tree or len(pads) <= 2:
        return channel_path
    result = _to.run_expand_all_pad_tree(_path_tuple(channel_path), pads)
    if result is None:
        return channel_path
    waypoints, total_length = result
    return ChannelPath(
        net_name=channel_path.net_name,
        channel_sequence=list(channel_path.channel_sequence),
        waypoints=waypoints,
        total_length=total_length,
        preferred_layer=channel_path.preferred_layer,
    )


def _assign_layer(
    net_name: str,
    layer_constraints: dict | None = None,
) -> str:
    """Assign net to preferred routing *working* layer for the N-layer A*
    driver's Tier 1 search and mid-route continuity anchoring.

    Resolution order (``assign_layer_impl`` in
    ``temper-orchestration/src/channel_mapping.rs``):
    1. Single-layer mode overrides everything -> F.Cu.
    2. SSOT ``layer_constraints`` (from ``layer_assignments_from_netclass``)
       when available and the net's class is *explicit* (not a catch-all
       Default) -- applied **unconditionally**, with no check against the
       net's own pad layer or the heuristic below. (This docstring
       previously described a now-removed "divergence guard" that applied
       the SSOT layer only when it agreed with the heuristic; that guard
       does not exist in this function today -- see
       ``docs/evidence/2026-08-14-router-pad-layer-landing-fix.md`` §1 for
       why it was removed and what removing it actually cost, and
       ``docs/evidence/2026-08-14-router-primary-grid-selection-fix.md``
       for how the N-layer A* driver copes with the resulting SSOT/pad
       disagreement without restoring it.)
    3. Heuristic: power / ground / HV -> B.Cu; signal -> F.Cu.

    This function does NOT itself reconcile the SSOT layer against where a
    net's own footprints are actually placed -- ``_astar_nlayer.py``'s
    ``_land_route_on_pad_layers`` (post-route landing-via correction) and
    ``run_astar_pathfinding_nlayer``'s ``pad_layer_start``/``pad_layer_end``
    (route-boundary anchor selection) are what make the disagreement safe
    to route through, downstream of this net-wide single-layer choice.
    """
    return _to.run_assign_layer(net_name, layer_constraints)


def fallback_channel_path(
    net_name: str,
    pads: list[tuple[float, float]],
    layer_constraints: dict | None = None,
    *,
    enable_all_pad_tree: bool = False,
) -> ChannelPath:
    """Direct-A*-attempt fallback for a net without a SAT channel
    assignment.  Two-pad nets retain their historical endpoint order; a
    multi-pad net retains every terminal in deterministic coordinate order so
    A* can construct a connected incremental path rather than silently
    dropping middle pads.
    """
    waypoints, preferred_layer = _to.run_fallback_channel_path(
        net_name,
        pads,
        layer_constraints,
        enable_all_pad_tree,
    )
    return ChannelPath(
        net_name=net_name,
        channel_sequence=[],
        waypoints=waypoints,
        total_length=0.0,
        preferred_layer=preferred_layer,
    )


@dataclass
class ChannelMapping:
    """Mapping of nets to channel paths."""

    channel_paths: dict[str, ChannelPath]  # net_name -> ChannelPath

    @property
    def mapped_net_count(self) -> int:
        """Number of nets with channel mappings."""
        return len(self.channel_paths)

    def get_path(self, net_name: str) -> ChannelPath | None:
        """Get channel path for a specific net."""
        return self.channel_paths.get(net_name)


def map_topology_to_channels(
    topology: TopologyGraph | None,
    skeleton: ChannelSkeleton,
    layer_constraints: dict | None = None,
) -> ChannelMapping:
    """Map abstract topology graph to concrete routing channels.

    Uses the SAT solver's output as the primary routing path.  A* on
    the occupancy grid is the fallback for nets the solver didn't assign
    (handled by the pipeline, not this function).

    Args:
        topology: Topological routing graph, or ``None`` when SAT is
            bypassed (Stage 3 skipped).
        skeleton: Channel skeleton.
        layer_constraints: Optional per-net ``LayerAssignment`` dict from
            ``layer_assignments_from_netclass`` (W2 U2 / R2).  When
            supplied, the SSOT ``layer`` field overrides the heuristic
            in ``_assign_layer`` for nets whose target layer is a
            routable outer copper layer (F.Cu / B.Cu).

    Returns:
        ChannelMapping
    """
    nets = []
    net_names = list(topology.net_topologies.keys()) if topology is not None else []
    for net_name in net_names:
        net_topology = topology.get_topology(net_name) if topology is not None else None
        uses_channels = list(net_topology.uses_channels)
        # The path-graph node fallback strings (`str(node)`) and its
        # exception swallowing stay Python (CPython str semantics); the
        # decision control flow is the Rust orchestration.
        path_graph_nodes = None
        if (
            net_topology.path_graph is not None
            and net_topology.path_graph.number_of_edges() > 0
        ):
            try:
                nodes = list(net_topology.path_graph.nodes())
                if nodes:
                    path_graph_nodes = [str(node) for node in nodes]
            except Exception:
                pass
        nets.append((net_name, uses_channels, path_graph_nodes))

    skeleton_nodes = list(skeleton.graph.nodes)
    results = _to.run_channel_mapping(nets, skeleton_nodes, layer_constraints)

    channel_paths = {}
    for (net_name, channel_sequence, waypoints, total_length, preferred_layer) in results:
        channel_paths[net_name] = ChannelPath(
            net_name=net_name,
            channel_sequence=channel_sequence,
            waypoints=waypoints,
            total_length=total_length,
            preferred_layer=preferred_layer,
        )

    return ChannelMapping(channel_paths=channel_paths)


def _calculate_path_length(waypoints: list[tuple[float, float]]) -> float:
    """
    Calculate total path length from waypoints.

    Args:
        waypoints: List of (x, y) coordinates

    Returns:
        Total length in mm

    Wave 4: computed in ``temper-geometry`` (``channel_mapping.rs``), which
    reproduces the reference's naive ``+=`` fold of ``(dx**2 + dy**2) ** 0.5``
    segment lengths (host-libm ``pow``) bit-exactly.
    """
    return _tg.channel_path_length_py(_flatten(waypoints))


def _nearest_skeleton_node(
    coord: tuple[float, float],
    skeleton: ChannelSkeleton,
) -> tuple[float, float] | None:
    """Return the skeleton node closest to ``coord``, or ``None`` if empty.

    Ties are broken by the node's own coordinate, so the result depends only on
    the node *set* and ``coord`` -- never on iteration or insertion order.

    Wave 4: computed in ``temper-geometry`` (``channel_mapping.rs``), which
    reproduces the reference's ``min`` over the ``((n - coord)**2, n)`` key
    bit-exactly.  The argmin is unique for distinct nodes, so converting the
    node view to a list cannot change the result.
    """
    nodes = list(skeleton.graph.nodes)
    return _tg.nearest_skeleton_node_py(coord[0], coord[1], _flatten(nodes))


def _is_near_skeleton(
    coord: tuple[float, float],
    skeleton: ChannelSkeleton,
    tolerance: float = 5.0,
) -> bool:
    """Check if a coordinate is near any skeleton node.

    Wave 4: computed in ``temper-geometry`` (``channel_mapping.rs``), a
    per-node ``dx*dx + dy*dy <= tolerance*tolerance`` existential scan.
    """
    nodes = list(skeleton.graph.nodes)
    return _tg.is_near_skeleton_py(coord[0], coord[1], _flatten(nodes), tolerance)


def _nearest_terminal_order(
    start: tuple[float, float], pads: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Deterministically extend an existing copper component one pad at a time.

    Wave 4: computed in ``temper-geometry`` (``channel_mapping.rs``), which
    reproduces the reference's greedy nearest-by-Manhattan ordering over the
    de-duplicated ``set(pads)`` bit-exactly.
    """
    return _tg.nearest_terminal_order_py(start[0], start[1], _flatten(pads))
