"""Verbatim pre-migration oracle for the Phase E batch E4 channel-operations
orchestration (Rust Orchestration Engine plan 2026-08-09-001, Phase E E4).

This file is a byte-exact snapshot of the ORCHESTRATION bodies of the two
channel modules AS COMMITTED at the dispatch base (origin/main d1b330b90),
extracted verbatim:

- ``router_v6/channel_mapping.py`` — the full module: the ``ChannelPath`` /
  ``ChannelMapping`` dataclasses, ``map_topology_to_channels`` /
  ``_map_net_to_channels`` / ``_extract_waypoints`` /
  ``_parse_channel_coordinate`` / ``_skeleton_nodes_in_coordinate_order`` /
  ``_assign_layer`` / ``_ssot_layer_for_net`` / ``_validated_two_pad_terminals`` /
  ``expand_channel_path_terminals`` / ``fallback_channel_path`` (the
  topology-to-channel mapping orchestration) plus the four already-Rust
  leaf-kernel delegations it drives (``_calculate_path_length`` /
  ``_nearest_skeleton_node`` / ``_is_near_skeleton`` /
  ``_nearest_terminal_order`` through ``temper_geometry``).
- ``router_v6/channel_widths.py`` — the ``ChannelWidths`` dataclass,
  ``compute_channel_widths`` (BOTH the EDT production path and the per-point
  reference path), ``_compute_width_at_point``, ``_build_edt`` /
  ``_rasterize_boundary_mask`` / ``_compute_board_fingerprint`` /
  ``_edt_cache_path`` / ``_atomic_write_npz`` / ``_evict_if_over_budget`` /
  ``_exact_edt`` and the module constants (the channel-width measurement
  orchestration).  ``ChannelWidthsStage`` / ``validate_channel_widths`` are
  the pipeline-stage / DRC-fence-validator surface and are NOT extracted
  (they stay Python in the shim, unchanged, and are not differential
  surface).

The shapely/numpy/disk-cache portions stay Python (shapely ``contains_xy`` /
prepared-geometry ``distance`` and the WKB fingerprint have no Rust
equivalent — the E4 boundary, argued in the channel_widths.py shim header);
this oracle is what pins the PORTABLE orchestration — the channel-ID
coordinate parsing, the skeleton coordinate-order fallback, the layer
assignment, the two-pad terminal validation, the all-pad-tree expansion and
the EDT-branch edge sampling / batch-lookup dispatch / node-edge-width
assembly / statistics — against the Rust port in ``temper-orchestration``
(``channel_mapping.rs``).

The ``temper_placer`` imports below resolve to the pinned pre-E4 modules
(the pieces E4 did NOT migrate).  Do NOT edit: it is the reference.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg

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
    ``list(graph.nodes)``, which yields insertion order.
    """
    return sorted(skeleton.graph.nodes)


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

    Wave 4: computed in ``temper-geometry`` (``channel_mapping.rs``), which
    reproduces the reference's naive ``+=`` fold of ``(dx**2 + dy**2) ** 0.5``
    segment lengths (host-libm ``pow``) bit-exactly.
    """
    return _tg.channel_path_length_py(_flatten(waypoints))


def _nearest_terminal_order(
    start: tuple[float, float], pads: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Deterministically extend an existing copper component one pad at a time.

    Wave 4: computed in ``temper-geometry`` (``channel_mapping.rs``), which
    reproduces the reference's greedy nearest-by-Manhattan ordering over the
    de-duplicated ``set(pads)`` bit-exactly.
    """
    return _tg.nearest_terminal_order_py(start[0], start[1], _flatten(pads))


# ---------------------------------------------------------------------------
# router_v6/channel_widths.py — the compute surface (verbatim)
# ---------------------------------------------------------------------------

import contextlib
import hashlib
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.routing_space import RoutingSpace

_CACHE_FORMAT_VERSION = "v2"  # bump when the EDT algorithm or .npz schema changes
_EDT_CACHE_MAX_ENTRIES = int(os.environ.get("TEMPER_EDT_CACHE_MAX_ENTRIES", "500"))


def _checkout_discriminator() -> str:
    """A short hash that differs per git checkout/worktree."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            root = parent
            break
    else:
        root = here.parent
    return hashlib.sha256(str(root).encode()).hexdigest()[:16]


def _cache_root() -> Path:
    """``$TMPDIR`` (or the platform default) scoped to this checkout."""
    return Path(tempfile.gettempdir()) / "temper-edt-cache" / _checkout_discriminator()


_EDT_CACHE_DIR = _cache_root()


@dataclass
class ChannelWidths:
    """Width measurements for routing channels."""

    layer_name: str
    node_widths: dict[tuple[float, float], float]  # Node position -> width in mm
    edge_widths: dict[tuple[tuple[float, float], tuple[float, float]], float]  # Edge -> min width
    min_width: float  # Minimum width across all channels
    max_width: float  # Maximum width across all channels
    avg_width: float  # Average width

    @property
    def bottleneck_width(self) -> float:
        """Return the minimum channel width (bottleneck)."""
        return self.min_width

    def get_node_width(self, node: tuple[float, float]) -> float:
        """Get width at a specific node."""
        return self.node_widths.get(node, 0.0)


def _rasterize_boundary_mask(
    available_area,
    bounds: tuple[float, float, float, float],
    cell_size: float,
) -> np.ndarray:
    """Rasterize the available routing area onto a binary grid.

    Cells whose centers lie inside the available area are marked as
    interior (True).  Cells outside or on the boundary are False.

    The result is used as input to the Euclidean distance transform,
    where False cells act as distance-zero sources and True cells
    receive the distance to the nearest boundary.

    Proof of correctness (base case):
        For any cell exactly on the polygon boundary, the Shapely
        ``contains`` predicate returns False (boundary is not
        interior).  The cell is marked False in the mask.  The EDT
        assigns distance 0 to that cell.  This matches the Shapely
        distance query: distance(Point_on_boundary, boundary_ring) = 0.

    Induction step:
        For a cell at grid distance d from the nearest boundary cell,
        the EDT propagates distance through the grid using the Eikonal
        equation.  The error relative to the true Euclidean distance
        is bounded by cell_size * sqrt(2) (the diagonal of a single
        cell).  As cell_size → 0, the EDT converges to the true
        distance.
    """
    import shapely

    min_x, min_y, max_x, max_y = bounds
    w = int(np.ceil((max_x - min_x) / cell_size)) + 1
    h = int(np.ceil((max_y - min_y) / cell_size)) + 1

    xs = np.linspace(min_x, min_x + (w - 1) * cell_size, w)
    ys = np.linspace(min_y, min_y + (h - 1) * cell_size, h)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")

    # Vectorised, not looped. This previously built one shapely Point per grid
    # cell and called prepared.contains() on it -- the nominal batching was
    # cosmetic, since the inner loop still ran per-point in Python. A single
    # test (test_empty_board_infinite_capacity, 20 Hypothesis examples) spent
    # ~90s making 14,024,826 such calls, and this function was ~90% of the
    # runtime of the four slowest tests in the invariant suite.
    #
    # shapely.contains_xy is the same `contains` predicate evaluated in C over
    # arrays, so the boundary semantics the docstring's proof relies on are
    # unchanged: contains excludes the boundary, boundary cells stay False, and
    # the EDT keeps them as distance-zero sources. Verified bit-identical to
    # the old implementation across plain, multi-cutout, boundary-aligned and
    # fine-cell grids (80-104x faster on those cases).
    mask = shapely.contains_xy(available_area, xx.ravel(), yy.ravel())

    return np.asarray(mask, dtype=bool).reshape(h, w)


def _edt_width_lookup_batch(
    xs: np.ndarray,
    ys: np.ndarray,
    edt: np.ndarray,
    mask: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
) -> np.ndarray:
    """Batch EDT width lookup: one FFI crossing for all samples.

    Bit-identical per point to the pre-batch per-point reference
    implementation (same f64 arithmetic order, computed in
    ``temper-geometry``); the batch form exists because the sampling
    hot loop (~12k calls per layer) is per-call Python overhead.
    """
    h, w = edt.shape
    out = _tg.edt_width_lookup_batch(
        np.ascontiguousarray(xs, dtype=np.float64).tolist(),
        np.ascontiguousarray(ys, dtype=np.float64).tolist(),
        np.ascontiguousarray(edt, dtype=np.float64).tobytes(),
        np.ascontiguousarray(mask).tobytes(),
        h,
        w,
        bounds,
        cell_size,
    )
    return np.asarray(out, dtype=np.float64)


def _compute_board_fingerprint(routing_space: RoutingSpace, cell_size: float) -> str:
    """Content hash of everything that determines the EDT output.

    Must include, and previously did not:

    - The routing polygon's *exact* geometry (WKB), not just
      ``bounds``/``area``. Two ``available_area`` geometries can share a
      bounding box and total area while differing in actual boundary shape
      (different obstacle layout, concavity, hole placement) -- bounds+area
      is not an injective function of the geometry, so it was possible for
      two different boards/layers to collide on one cache key and silently
      serve each other's distance field.
    - ``cell_size``: a coarser/finer raster grid changes every distance
      value. Previously every call site just happened to pass 0.1mm by
      convention (see ``capacity_check.py``'s ``_EDT_CELL_SIZE`` comment
      "matches channel_widths.py") -- an unenforced invariant, not a
      guarantee.
    - ``_CACHE_FORMAT_VERSION``: bumping it invalidates every existing
      entry, so a future change to the EDT algorithm or the ``.npz``
      schema can't be silently misread as an old-format cache hit.

    ``layer_name`` is intentionally hashed in too (in addition to being a
    separate filename component below) so the key alone is already unique
    per layer, independent of how the filename happens to be built.
    """
    geom = routing_space.available_area
    h = hashlib.sha256()
    h.update(_CACHE_FORMAT_VERSION.encode())
    h.update(b"\0")
    h.update(routing_space.layer_name.encode())
    h.update(b"\0")
    h.update(repr(cell_size).encode())
    h.update(b"\0")
    h.update(geom.wkb)
    return h.hexdigest()[:32]


def _edt_cache_path(fp: str, layer: str) -> Path:
    safe_layer = "".join(c if c.isalnum() or c in "._-" else "_" for c in layer)
    return _EDT_CACHE_DIR / f"edt_{fp}_{safe_layer}.npz"


def _atomic_write_npz(path: Path, *, edt: np.ndarray, mask: np.ndarray) -> None:
    """Write an ``.npz`` cache entry atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez_compressed(f, edt=edt, mask=mask)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def _evict_if_over_budget(max_entries: int = _EDT_CACHE_MAX_ENTRIES) -> None:
    """Bound the per-checkout cache to ``max_entries`` files (LRU by mtime)."""
    try:
        entries = sorted(
            (p for p in _EDT_CACHE_DIR.glob("edt_*.npz") if p.is_file()),
            key=lambda p: (p.stat().st_mtime, p.name),
        )
    except OSError:
        return
    excess = len(entries) - max_entries
    for p in entries[: max(excess, 0)]:
        with contextlib.suppress(OSError):
            p.unlink()


def _exact_edt(mask: np.ndarray) -> np.ndarray:
    """Exact Euclidean distance transform, delegating to
    ``temper_geometry.exact_edt_transform`` (Rust Felzenszwalb-Huttenlocher
    sweep).  Bit-exact vs ``scipy.ndimage.distance_transform_edt(mask)`` (no
    ``sampling`` argument) on every input reachable by this module -- see
    ``docs/evidence/2026-08-07-exact-edt-rust-spike.md``.  ``mask`` must
    already be the desired ``uint8``/bool array at the call site; this
    function does not renormalize dtype or semantics.
    """
    h, w = mask.shape
    mask_u8 = np.ascontiguousarray(mask, dtype=np.uint8)
    out_bytes = _tg.exact_edt_transform(mask_u8.tobytes(), h, w)
    return np.frombuffer(out_bytes, dtype="<f8").reshape(h, w)


def _build_edt(
    routing_space: RoutingSpace,
    cell_size: float,
    use_cache: bool = True,
) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float, float]]:
    """Build an EDT grid for the given routing space, with optional disk cache.

    Returns:
        (edt_distances, interior_mask, bounds)
    """
    bounds = routing_space.available_area.bounds
    fp = _compute_board_fingerprint(routing_space, cell_size)

    if use_cache:
        cache_path = _edt_cache_path(fp, routing_space.layer_name)
        try:
            with np.load(cache_path) as data:
                return np.array(data["edt"]), np.array(data["mask"]), bounds
        except FileNotFoundError:
            pass
        except (OSError, ValueError, EOFError, zipfile.BadZipFile):
            pass

    mask = _rasterize_boundary_mask(routing_space.available_area, bounds, cell_size)
    edt = _exact_edt(mask.astype(np.uint8))

    if use_cache:
        _atomic_write_npz(cache_path, edt=edt, mask=mask)
        _evict_if_over_budget()

    return edt, mask, bounds


def compute_channel_widths(
    routing_space: RoutingSpace,
    skeleton: ChannelSkeleton,
    sample_distance: float = 1.0,
    use_edt: bool = True,
) -> ChannelWidths:
    """
    Compute channel widths along the skeleton.

    Width is measured as the distance to the nearest obstacle (2x clearance).

    Args:
        routing_space: Routing space from Stage 2.2
        skeleton: Channel skeleton from Stage 2.3
        sample_distance: Distance between width samples along edges (mm)

    Returns:
        ChannelWidths with width measurements
    """
    node_widths = {}
    edge_widths: dict[tuple[tuple[float, float], tuple[float, float]], float] = {}

    # Get the available routing area
    available_area = routing_space.available_area

    if available_area.is_empty or skeleton.node_count == 0:
        # No routing space or skeleton
        return ChannelWidths(
            layer_name=routing_space.layer_name,
            node_widths={},
            edge_widths={},
            min_width=0.0,
            max_width=0.0,
            avg_width=0.0,
        )

    # Pre-build the per-call caches for ``_compute_width_at_point``.
    import shapely.prepared
    from shapely.geometry import MultiPolygon

    prepared_area = shapely.prepared.prep(available_area)
    if isinstance(available_area, MultiPolygon):
        cached_polygons = list(available_area.geoms)
    else:
        cached_polygons = [available_area]
    cached_exteriors = [p.exterior for p in cached_polygons]
    cached_interiors = [list(p.interiors) for p in cached_polygons]

    # EDT path: rasterize + distance transform replaces per-point Shapely
    _edt_grid, _edt_mask, _edt_bounds, _edt_cell = None, None, None, 0.1
    if use_edt:
        _edt_grid, _edt_mask, _edt_bounds = _build_edt(routing_space, _edt_cell)

    def _width_at(p: tuple[float, float]) -> float:
        return _compute_width_at_point(
            p,
            available_area,
            _prepared=prepared_area,
            _polygons=cached_polygons,
            _exteriors=cached_exteriors,
            _interiors=cached_interiors,
        )

    if _edt_grid is not None and _edt_mask is not None and _edt_bounds is not None:
        # Batched EDT path: collect every sample point, resolve all widths
        # in one FFI crossing (bit-identical per point to the per-point
        # reference pinned in the differential test suites), then assemble
        # node/edge widths.
        _node_points = list(skeleton.graph.nodes)

        _edge_samples: list[tuple[object, object, list[tuple[float, float]]]] = []
        for u, v in skeleton.graph.edges:
            dx = v[0] - u[0]
            dy = v[1] - u[1]
            edge_length = (dx**2 + dy**2) ** 0.5
            if edge_length > sample_distance:
                num_samples = int(edge_length / sample_distance)
                _edge_samples.append(
                    (
                        u,
                        v,
                        [
                            (u[0] + (i / num_samples) * dx, u[1] + (i / num_samples) * dy)
                            for i in range(1, num_samples)
                        ],
                    )
                )
            else:
                _edge_samples.append((u, v, []))

        _all_points = _node_points + [p for (_, _, pts) in _edge_samples for p in pts]
        if _all_points:
            _widths = _edt_width_lookup_batch(
                np.asarray([p[0] for p in _all_points], dtype=np.float64),
                np.asarray([p[1] for p in _all_points], dtype=np.float64),
                _edt_grid,
                _edt_mask,
                _edt_bounds,
                _edt_cell,
            )
        else:
            _widths = np.zeros(0, dtype=np.float64)

        node_widths = dict(zip(_node_points, _widths[: len(_node_points)]))
        _sample_offset = len(_node_points)
        for u, v, pts in _edge_samples:
            widths_along_edge = [node_widths[u], node_widths[v]]
            for k in range(len(pts)):
                widths_along_edge.append(float(_widths[_sample_offset + k]))
            _sample_offset += len(pts)
            edge_widths[(cast(tuple[float, float], u), cast(tuple[float, float], v))] = min(widths_along_edge) if widths_along_edge else 0.0
    else:
        # Reference path: per-point width sampling (EDT disabled or
        # unavailable).  Keep the original loop untouched for parity.
        for node in skeleton.graph.nodes:
            width = _width_at(node)
            node_widths[node] = width

        for u, v in skeleton.graph.edges:
            widths_along_edge = []

            widths_along_edge.append(node_widths[u])
            widths_along_edge.append(node_widths[v])

            dx = v[0] - u[0]
            dy = v[1] - u[1]
            edge_length = (dx**2 + dy**2) ** 0.5

            if edge_length > sample_distance:
                num_samples = int(edge_length / sample_distance)
                for i in range(1, num_samples):
                    t = i / num_samples
                    sample_x = u[0] + t * dx
                    sample_y = u[1] + t * dy
                    width = _width_at((sample_x, sample_y))
                    widths_along_edge.append(width)

            edge_widths[(cast(tuple[float, float], u), cast(tuple[float, float], v))] = min(widths_along_edge) if widths_along_edge else 0.0

    # Compute statistics
    all_widths = list(node_widths.values()) + list(edge_widths.values())

    if all_widths:
        min_width = min(all_widths)
        max_width = max(all_widths)
        avg_width = sum(all_widths) / len(all_widths)
    else:
        min_width = max_width = avg_width = 0.0

    return ChannelWidths(
        layer_name=routing_space.layer_name,
        node_widths=node_widths,
        edge_widths=cast(
            dict[tuple[tuple[float, float], tuple[float, float]], float],
            edge_widths,
        ),
        min_width=min_width,
        max_width=max_width,
        avg_width=avg_width,
    )


def _compute_width_at_point(
    point: tuple[float, float],
    available_area,
    _prepared=None,
    _polygons=None,
    _exteriors=None,
    _interiors=None,
) -> float:
    """
    Compute channel width at a point.

    Width is 2x the distance to the nearest boundary (clearance on both sides).

    Args:
        point: (x, y) coordinate
        available_area: Available routing area (Polygon or MultiPolygon)
        _prepared: Optional pre-built ``shapely.prepared.prep`` of
            ``available_area``.
        _polygons: Optional pre-extracted polygon list.
        _exteriors: Optional pre-cached list of ``polygon.exterior`` rings.
        _interiors: Optional pre-cached list of ``list(polygon.interiors)``.

    Returns:
        Width in mm
    """
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.geometry import Point as ShapelyPoint

    pt = ShapelyPoint(point)

    if _prepared is None:
        import shapely.prepared

        _prepared = shapely.prepared.prep(available_area)
    if _polygons is None:
        if isinstance(available_area, Polygon):
            _polygons = [available_area]
        elif isinstance(available_area, MultiPolygon):
            _polygons = list(available_area.geoms)
        else:
            return 0.0

    if not _prepared.contains(pt):
        return 0.0

    min_distance = float("inf")
    if _exteriors is None:
        _exteriors = [p.exterior for p in _polygons]
    if _interiors is None:
        _interiors = [list(p.interiors) for p in _polygons]

    for exterior, interiors in zip(_exteriors, _interiors):
        d = pt.distance(exterior)
        if d < min_distance:
            min_distance = d
        for interior in interiors:
            d = pt.distance(interior)
            if d < min_distance:
                min_distance = d

    if min_distance == float("inf"):
        return 0.0
    return 2.0 * min_distance


from typing import cast  # noqa: E402
