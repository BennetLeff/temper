"""
Router V6 Stage 4.1: Map Topology to Channels

Maps abstract topology graph to concrete routing channels.
Part of temper-qic1 (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.net_classification import (
    get_single_layer_mode,
    is_ground_net,
    is_hv_net,
    is_power_net,
)
from temper_placer.router_v6.terminal_extraction import ParsedTerminal
from temper_placer.router_v6.terminal_tree import TerminalTreePlan
from temper_placer.router_v6.topology_extraction import NetTopology, TopologyGraph


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


# L2_GND (2) / L3_PWR (3) are intentionally NOT mapped — they are
# inner plane layers, not routing grids.
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
        return _validated_two_pad_terminals(channel_path, pads)
    if not enable_all_pad_tree or len(pads) <= 2:
        return channel_path
    existing = set(channel_path.waypoints)
    missing = [pad for pad in pads if pad not in existing]
    if not missing:
        return channel_path
    attachment_point = channel_path.waypoints[-1] if channel_path.waypoints else min(missing)
    ordered_missing = _nearest_terminal_order(attachment_point, missing)
    return ChannelPath(
        net_name=channel_path.net_name,
        channel_sequence=list(channel_path.channel_sequence),
        waypoints=[*channel_path.waypoints, *ordered_missing],
        total_length=_calculate_path_length([*channel_path.waypoints, *missing]),
        preferred_layer=channel_path.preferred_layer,
    )


def _validated_two_pad_terminals(
    channel_path: ChannelPath,
    pads: list[tuple[float, float]],
) -> ChannelPath:
    """Validate/correct a 2-pad net's path endpoints against its own pads.

    ``channel_path.waypoints`` for a SAT/channel-derived path is untrusted
    input: Stage 4's A* treats *every* waypoint as a required terminal it
    must reach (``_route_segment_3d`` / ``_astar_route_multilayer`` search a
    segment to each consecutive waypoint pair in turn -- see
    ``_astar_search.py``), so an unverified endpoint becomes real copper.
    Measured on ``pcb/temper.kicad_pcb`` (docs/evidence/
    2026-08-08-nlayer-via-astar-spike.md §2.4): a 2-pad net's endpoint can
    coincide exactly with a *different* net's pad (a physically adjacent
    pad on the same footprint), not this net's own. On a mains-connected
    board with an SELV/HV isolation requirement, copper that bridges the
    wrong two nets is a safety defect, not merely a completion bug -- so
    this is corrected unconditionally, not just under a feature flag.

    **Why snap to the pad rather than fail the net closed:** ``pads`` is
    this net's own two true pad positions -- the exact same
    ``_net_pad_positions`` values the caller already trusts for pad
    unblocking, already in hand, already authoritative. There are only ever
    two candidates and both are known exactly, so correcting a bad endpoint
    is not a guess the way picking an arbitrary nearby pad would be.
    Declining the net instead would discard real, achievable completion for
    no correctness benefit. (Failing closed remains the right call when the
    correct terminal is *not* known -- it is not here.)

    The two true pads are assigned to the path's first/last waypoint by
    whichever pairing (identity or swap) minimizes total displacement, so an
    already-correct endpoint is left untouched (zero-cost identity mapping)
    and only a wrong one moves. Interior waypoints -- channel-skeleton
    routing guidance, not terminals -- are never touched. A path with fewer
    than 2 waypoints has no real geometry to preserve, so it is replaced
    outright by the two true pads.
    """
    waypoints = channel_path.waypoints
    pad_a, pad_b = pads[0], pads[1]

    if len(waypoints) < 2:
        corrected = [pad_a, pad_b]
    else:
        first, last = waypoints[0], waypoints[-1]

        def _dist(p: tuple[float, float], q: tuple[float, float]) -> float:
            return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5

        identity_cost = _dist(first, pad_a) + _dist(last, pad_b)
        swap_cost = _dist(first, pad_b) + _dist(last, pad_a)
        new_first, new_last = (pad_a, pad_b) if identity_cost <= swap_cost else (pad_b, pad_a)
        corrected = [new_first, *waypoints[1:-1], new_last]

    if corrected == waypoints:
        return channel_path

    return ChannelPath(
        net_name=channel_path.net_name,
        channel_sequence=list(channel_path.channel_sequence),
        waypoints=corrected,
        total_length=_calculate_path_length(corrected),
        preferred_layer=channel_path.preferred_layer,
        terminal_tree=channel_path.terminal_tree,
        terminals=channel_path.terminals,
    )


def _ssot_layer_for_net(
    net_name: str,
    layer_constraints: dict | None,
) -> str | None:
    """Return the SSOT layer name if the net has an *explicit* netclass
    (not the Default catch-all) and the layer is routable.  Returns
    ``None`` when the heuristic should be used instead.
    """
    if layer_constraints is None:
        return None

    assignment = layer_constraints.get(net_name)
    if assignment is None:
        return None

    # The reason field now carries "netclass=<Name> SSOT layer=<layer>"
    # (layer_assignment.py:332).  If the class is "Default", the net has
    # no explicit netclass — fall through to the heuristic to preserve
    # the W1 100%-completion baseline.
    reason = getattr(assignment, "reason", "")
    if "netclass=Default" in reason:
        return None

    # Explicit netclass — use the SSOT layer if routable.
    primary = getattr(assignment, "primary_layer", None)
    if primary is not None:
        val = primary.value if hasattr(primary, "value") else int(primary)
        return _LAYER_ENUM_TO_KICAD.get(val)
    # Shim for bare-string callers.
    if isinstance(assignment, str) and assignment in {"F.Cu", "B.Cu"}:
        return assignment
    return None


def _assign_layer(
    net_name: str,
    layer_constraints: dict | None = None,
) -> str:
    """Assign net to preferred routing layer.

    Resolution order:
    1. SSOT ``layer_constraints`` (from
       ``layer_assignments_from_netclass``) when available, the net's
       class is *explicit* (not a catch-all Default), and the resolved
       layer is routable (F.Cu / B.Cu).  **Completion-preserving:** the
       SSOT layer is only applied when it does not differ from the
       heuristic layer — nets whose heuristic says F.Cu (signal / SMD
       pads) are never forced to B.Cu, and vice versa.  This avoids
       unconnected pads when A* routes on a layer where the pads don't
       exist.
    2. Heuristic: power / ground / HV → B.Cu; signal → F.Cu.
    3. Single-layer mode overrides everything → F.Cu.
    """
    if get_single_layer_mode():
        return "F.Cu"

    # Compute the heuristic first so we can gate SSOT on it.
    heuristic = (
        "B.Cu"
        if is_power_net(net_name) or is_ground_net(net_name) or is_hv_net(net_name)
        else "F.Cu"
    )

    # W2 U2 / R2 / U7: SSOT-driven layer assignment from the netclass YAML.
    # When the net has an explicit netclass with a routable SSOT layer,
    # apply it.  The divergence guard (ssot == heuristic) is removed;
    # via-aware transitions (U1-U6) provide legal layer changes, and
    # the fallback tier handles unreachable terminals gracefully.
    ssot = _ssot_layer_for_net(net_name, layer_constraints)
    if ssot is not None:
        return ssot

    return heuristic


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
    if len(pads) == 2:
        waypoints = pads
    elif enable_all_pad_tree:
        waypoints = sorted(pads)
    else:
        waypoints = [pads[0], pads[-1]]
    return ChannelPath(
        net_name=net_name,
        channel_sequence=[],
        waypoints=waypoints,
        total_length=0.0,
        preferred_layer=_assign_layer(net_name, layer_constraints=layer_constraints),
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
    channel_paths = {}

    # Infer net names from topology.  When topology is None
    # (Stage 3 bypassed), the caller's A* fallback handles routing.
    net_names = list(topology.net_topologies.keys()) if topology is not None else []

    for net_name in net_names:
        net_topology = topology.get_topology(net_name) if topology is not None else None

        channel_path = _map_net_to_channels(
            net_name,
            net_topology,
            skeleton,
            layer_constraints=layer_constraints,
        )
        if channel_path:
            channel_paths[net_name] = channel_path

    return ChannelMapping(channel_paths=channel_paths)


def _map_net_to_channels(
    net_name: str,
    net_topology: NetTopology | None,
    skeleton: ChannelSkeleton,
    layer_constraints: dict | None = None,
) -> ChannelPath | None:
    """Map a single net's topology to channel sequence.

    Uses the SAT solver's output as the primary routing path.  The
    Dijkstra-based skeleton pathfinder was removed (2026-06-28) — the
    SAT solver now produces correct, capacity-constrained channel
    assignments, and Dijkstra was a workaround for the old mock solver.

    Args:
        net_name: Net name
        net_topology: Net's topological routing (can be None)
        skeleton: Channel skeleton graph
        layer_constraints: Optional per-net LayerAssignment dict (W2 U2).

    Returns:
        ChannelPath or None if mapping fails
    """
    channel_sequence: list[str] = []

    # 1. Use SAT solver topology as primary routing path.
    if net_topology:
        channel_sequence = list(net_topology.uses_channels)

        if (
            not channel_sequence
            and net_topology.path_graph is not None
            and net_topology.path_graph.number_of_edges() > 0
        ):
            try:
                nodes = list(net_topology.path_graph.nodes())
                if nodes:
                    channel_sequence = [str(node) for node in nodes]
            except Exception:
                pass

    # If still no sequence, we can't route
    if not channel_sequence:
        return None

    # Generate waypoints from skeleton
    waypoints = _extract_waypoints(channel_sequence, skeleton)

    # Calculate total length
    total_length = _calculate_path_length(waypoints)

    if channel_sequence or waypoints:
        return ChannelPath(
            net_name=net_name,
            channel_sequence=channel_sequence,
            waypoints=waypoints,
            total_length=total_length,
            preferred_layer=_assign_layer(
                net_name,
                layer_constraints=layer_constraints,
            ),
        )

    return None


def _extract_waypoints(
    channel_sequence: list[str],
    skeleton: ChannelSkeleton,
) -> list[tuple[float, float]]:
    """
    Extract waypoints from channel sequence using skeleton graph.

    Args:
        channel_sequence: List of channel IDs
        skeleton: Channel skeleton

    Returns:
        List of (x, y) waypoints
    """
    waypoints = []

    # If no channels specified, generate path through skeleton
    if not channel_sequence:
        if skeleton.graph.number_of_nodes() > 0:
            # Use skeleton nodes directly
            nodes = list(skeleton.graph.nodes())
            # Find a reasonable path through the skeleton
            if len(nodes) >= 2:
                try:
                    # Try to find a path from one end to another
                    # Use the nodes with degree 1 (endpoints) or just use first/last
                    endpoints = [n for n in nodes if skeleton.graph.degree(n) == 1]
                    if len(endpoints) >= 2:
                        # Find path between endpoints
                        path = nx.shortest_path(skeleton.graph, endpoints[0], endpoints[1])
                        return path
                    else:
                        # Use first and last nodes
                        path = nx.shortest_path(skeleton.graph, nodes[0], nodes[-1])
                        return path
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    # No path found, return subset of nodes
                    return nodes[: min(5, len(nodes))]
        return []

    import re

    # Try to parse channel IDs as coordinates
    for channel_id in channel_sequence:
        # Check for multiple coordinates in ID (Edge ID)
        # Format: ..._(x1, y1)_(x2, y2)
        coord_matches = re.findall(r"\(([^)]+)\)", channel_id)
        if len(coord_matches) >= 2:
            # Edge with start/end points
            found_edge_points = False
            for match in coord_matches:
                try:
                    parts = match.split(",")
                    if len(parts) == 2:
                        x = float(parts[0].strip())
                        y = float(parts[1].strip())
                        waypoints.append((x, y))
                        found_edge_points = True
                except ValueError:
                    pass
            if found_edge_points:
                continue

        # Fallback to single coordinate parsing
        coord = _parse_channel_coordinate(channel_id, skeleton)
        if coord:
            waypoints.append(coord)

    # If we successfully extracted waypoints, return them
    if waypoints:
        return waypoints

    # Fallback: use skeleton to generate path.
    #
    # Determinism: `list(graph.nodes())` is networkx *insertion* order, i.e.
    # whichever nodes `extract_channel_skeleton` happened to emit first while
    # walking the Voronoi output. Slicing that is not a property of the board
    # geometry -- permuting node/edge insertion order on an otherwise identical
    # 40-node graph changed this return value in 16/16 trials
    # (docs/evidence/2026-08-04-networkx-path-order-spike.md §6, hazard H2).
    # Coordinate order is used instead: it is a function of the geometry alone,
    # and it is this module's own existing convention for the same problem
    # (`fallback_channel_path` -> `sorted(pads)`, "deterministic coordinate
    # order"; `expand_channel_path_terminals` -> `min(missing)`).
    if skeleton.graph.number_of_nodes() > 0:
        nodes = _skeleton_nodes_in_coordinate_order(skeleton)
        return nodes[: min(len(channel_sequence) + 1, len(nodes))]

    return []


def _skeleton_nodes_in_coordinate_order(
    skeleton: ChannelSkeleton,
) -> list[tuple[float, float]]:
    """Return the skeleton's nodes in ascending ``(x, y)`` order.

    Skeleton nodes *are* coordinates (``ChannelSkeleton.graph``: "Nodes are
    (x, y) positions"), so lexicographic tuple order is a total order derived
    from the board geometry rather than from how the graph was built. Callers
    that select nodes by position must use this instead of
    ``list(graph.nodes())``, which yields networkx insertion order.
    """
    return sorted(skeleton.graph.nodes())


def _nearest_skeleton_node(
    coord: tuple[float, float],
    skeleton: ChannelSkeleton,
) -> tuple[float, float] | None:
    """Return the skeleton node closest to ``coord``, or ``None`` if empty.

    Ties are broken by the node's own coordinate, so the result depends only on
    the node *set* and ``coord`` -- never on iteration or insertion order.
    """
    nodes = skeleton.graph.nodes()
    if not nodes:
        return None
    return min(
        nodes,
        key=lambda n: ((n[0] - coord[0]) ** 2 + (n[1] - coord[1]) ** 2, n),
    )


def _is_near_skeleton(
    coord: tuple[float, float],
    skeleton: ChannelSkeleton,
    tolerance: float = 5.0,
) -> bool:
    """Check if a coordinate is near any skeleton node."""
    if skeleton.graph.number_of_nodes() == 0:
        return False
    for node in skeleton.graph.nodes():
        dx = node[0] - coord[0]
        dy = node[1] - coord[1]
        if (dx * dx + dy * dy) <= tolerance * tolerance:
            return True
    return False


def _parse_channel_coordinate(
    channel_id: str,
    skeleton: ChannelSkeleton,
) -> tuple[float, float] | None:
    """
    Try to parse a channel ID into a coordinate.

    Attempts multiple strategies:
    1. Parse as "x_y" format (e.g., "10.5_20.3")
    2. Parse as "(x, y)" format
    3. Snap a parsed-but-off-skeleton coordinate to the nearest skeleton node

    A channel ID carrying no parseable coordinate yields ``None``: there is no
    position to report, and this function's contract is to *parse* one, not to
    invent one.

    Args:
        channel_id: Channel identifier
        skeleton: Channel skeleton

    Returns:
        (x, y) coordinate or None
    """
    # Strategy 1: Parse "x_y" format
    parsed: tuple[float, float] | None = None
    if "_" in channel_id:
        parts = channel_id.split("_")
        # Try last two parts as coordinates
        if len(parts) >= 2:
            try:
                x = float(parts[-2])
                y = float(parts[-1])
                # Verify this coordinate is near a skeleton node
                parsed = (x, y)
                if _is_near_skeleton(parsed, skeleton, tolerance=5.0):
                    return parsed
            except ValueError:
                pass

    # Strategy 2: Parse "(x, y)" or "x,y" format
    clean_id = channel_id.strip("()")
    if "," in clean_id:
        parts = clean_id.split(",")
        if len(parts) == 2:
            try:
                x = float(parts[0].strip())
                y = float(parts[1].strip())
                return (x, y)
            except ValueError:
                pass

    # Strategy 3: Find closest skeleton node (if skeleton is small).
    #
    # This used to read `idx = hash(channel_id) % len(nodes); return nodes[idx]`
    # -- a *geometric coordinate* derived from CPython's per-process salted
    # string hash, so the same channel ID resolved to a different physical
    # (x, y) in every interpreter (12/12 fresh interpreters disagreed;
    # docs/evidence/2026-08-04-networkx-path-order-spike.md §6, hazard H1).
    #
    # What it was trying to compute is stated by this function's own docstring
    # and by the comment above the branch: "find closest skeleton node". That
    # is only meaningful relative to a coordinate, and there is exactly one
    # available -- the one strategy 1 parsed out of the ID and then discarded
    # because it fell outside the 5 mm skeleton tolerance. Snapping *that* to
    # the nearest node is the operation the code claimed to perform; a hash was
    # never a stand-in for proximity, only for "any node at all".
    #
    # When no coordinate parsed, the result is None. That is strictly fewer
    # invented waypoints than before, never more: every ID that now yields None
    # previously yielded an arbitrary node, and no ID yields a coordinate that
    # it did not previously yield one for. The `<= 20` size gate belonged to
    # the hash hack (it bounded how arbitrary the pick could be) and is kept
    # only so this fix cannot widen the set of inputs that produce a waypoint.
    if parsed is not None and skeleton.graph.number_of_nodes() <= 20:
        return _nearest_skeleton_node(parsed, skeleton)

    return None


def _calculate_path_length(waypoints: list[tuple[float, float]]) -> float:
    """
    Calculate total path length from waypoints.

    Args:
        waypoints: List of (x, y) coordinates

    Returns:
        Total length in mm
    """
    if len(waypoints) < 2:
        return 0.0

    total_length = 0.0
    for i in range(len(waypoints) - 1):
        x1, y1 = waypoints[i]
        x2, y2 = waypoints[i + 1]
        dx = x2 - x1
        dy = y2 - y1
        length = (dx**2 + dy**2) ** 0.5
        total_length += length

    return total_length


def _nearest_terminal_order(
    start: tuple[float, float], pads: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Deterministically extend an existing copper component one pad at a time."""
    remaining = set(pads)
    ordered: list[tuple[float, float]] = []
    current = start
    while remaining:
        next_pad = min(
            remaining,
            key=lambda pad: (abs(pad[0] - current[0]) + abs(pad[1] - current[1]), pad),
        )
        ordered.append(next_pad)
        remaining.remove(next_pad)
        current = next_pad
    return ordered
