"""
Router V6 Stage 2.3: Extract Channel Skeleton

Extracts channel centerlines using medial axis transform to find routing paths.
Part of temper-h6t7 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import networkx as nx
import temper_geometry as _tg
from shapely.geometry import LineString, Polygon

from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


@dataclass
class ChannelSkeleton:
    """Skeleton graph representing routing channels."""

    graph: nx.Graph  # Nodes are (x, y) positions, edges are channel segments
    layer_name: str
    total_length: float  # Total channel length in mm

    @property
    def is_connected(self) -> bool:
        """Check if the channel graph is fully connected."""
        return nx.is_connected(self.graph) if len(self.graph.nodes) > 0 else True

    @property
    def node_count(self) -> int:
        """Number of nodes in the skeleton."""
        return len(self.graph.nodes)

    @property
    def edge_count(self) -> int:
        """Number of edges in the skeleton."""
        return len(self.graph.edges)


def extract_channel_skeleton(
    routing_space: RoutingSpace,
    simplify_tolerance: float = 0.5,
    pcb=None,  # Optional ParsedPCB for pad anchoring
) -> ChannelSkeleton:
    """
    Extract routing channel skeleton using medial axis approximation.

    If pcb is provided, adds component pad positions as anchor nodes
    connected to nearest skeleton nodes. This ensures routes connect
    to actual pad centers, not approximated skeleton positions.

    Args:
        routing_space: Routing space from Stage 2.2
        simplify_tolerance: Tolerance for simplifying skeleton (mm)
        pcb: Optional ParsedPCB for adding pad anchor nodes

    Returns:
        ChannelSkeleton with graph representation

    Example:
        >>> skeleton = extract_channel_skeleton(routing_space, pcb=pcb)
        >>> skeleton.is_connected
        True
    """
    # Create graph
    G = nx.Graph()

    # Get available routing area
    available_area = routing_space.available_area

    if available_area.is_empty:
        # No routing space available
        return ChannelSkeleton(
            graph=G,
            layer_name=routing_space.layer_name,
            total_length=0.0,
        )

    # Extract skeleton using Voronoi-based medial axis approximation
    skeleton_lines = _extract_medial_axis(available_area, simplify_tolerance)

    total_length = 0.0

    # Build graph from skeleton lines
    for line in skeleton_lines:
        coords = list(line.coords)

        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]

            # Add nodes (use tuple for hashability)
            G.add_node(p1, pos=p1)
            G.add_node(p2, pos=p2)

            # Calculate edge weight (length)
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = (dx**2 + dy**2) ** 0.5

            # Add edge with length weight
            G.add_edge(p1, p2, weight=length)
            G.add_edge(p1, p2, weight=length)
            total_length += length

    # Ensure connectivity by bridging islands
    G = _ensure_skeleton_connectivity(G, max_bridge_distance=10.0)

    # **OPTION F FIX**: Add component pad positions as anchor nodes
    if pcb and hasattr(pcb, "components") and G.number_of_nodes() > 0:
        import math

        # Extract all pad positions
        pad_positions = []
        for comp in pcb.components:
            if not comp.initial_position or not hasattr(comp, "pins"):
                continue

            rotation_deg = (
                comp.initial_rotation * 90.0 if comp.initial_rotation is not None else 0.0
            )
            math.radians(rotation_deg)
            comp.initial_side if hasattr(
                comp, "initial_side"
            ) and comp.initial_side is not None else 0

            for pin in comp.pins:
                if pin.net:
                    abs_pos = pin_world_position(pin, comp)
                    pad_positions.append(abs_pos)

        # Add pads as anchor nodes, connected to nearest skeleton node
        skeleton_nodes = list(G.nodes())
        pads_added = 0

        for pad_pos in pad_positions:
            # Skip if pad already exists in skeleton (within 0.1mm)
            if any(
                abs(pad_pos[0] - n[0]) < 0.1 and abs(pad_pos[1] - n[1]) < 0.1
                for n in skeleton_nodes
            ):
                continue

            # Find nearest skeleton node
            nearest_node = None
            min_dist = float("inf")
            for node in skeleton_nodes:
                dist = math.sqrt((pad_pos[0] - node[0]) ** 2 + (pad_pos[1] - node[1]) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_node = node

            # Add pad as new node with edge to nearest skeleton node
            if nearest_node and min_dist < 50.0:  # Only connect if within 50mm
                G.add_node(pad_pos, pos=pad_pos)
                G.add_edge(pad_pos, nearest_node, weight=min_dist)
                total_length += min_dist
                pads_added += 1

        if pads_added > 0:
            print(f"  Added {pads_added} pad anchor nodes to skeleton")

    return ChannelSkeleton(
        graph=G,
        layer_name=routing_space.layer_name,
        total_length=total_length,
    )


def _extract_medial_axis(
    polygon_or_multipolygon,
    simplify_tolerance: float = 0.5,
) -> list[LineString]:
    """
    Extract medial axis using Voronoi diagram approach.

    Args:
        polygon_or_multipolygon: Available routing area
        simplify_tolerance: Simplification tolerance

    Returns:
        List of LineStrings representing skeleton
    """
    from shapely.geometry import MultiPolygon, Polygon

    # Handle MultiPolygon
    if isinstance(polygon_or_multipolygon, MultiPolygon):
        all_lines = []

        if hasattr(polygon_or_multipolygon, "geoms"):
            polys = list(polygon_or_multipolygon.geoms)
        else:
            polys = [polygon_or_multipolygon]

        # Combine skeletons from all polygons
        for p in polys:
            lines = _extract_medial_axis_single(p, simplify_tolerance)
            print(f"  Extracted {len(lines)} skeleton lines")
            all_lines.extend(lines)
        return all_lines
    elif isinstance(polygon_or_multipolygon, Polygon):
        return _extract_medial_axis_single(polygon_or_multipolygon, simplify_tolerance)
    else:
        return []


def _extract_medial_axis_single(
    polygon: Polygon,
    simplify_tolerance: float = 0.5,
) -> list[LineString]:
    """
    Extract medial axis for a single polygon via an independent (non-GEOS)
    Voronoi diagram, computed in Rust.

    Delegates the full pipeline -- boundary sampling, Voronoi, the
    interior-edge filter, and both fallback branches (degenerate <3-point
    input, and Voronoi-yields-nothing) -- to
    ``temper_geometry.extract_medial_axis_single_py``. See
    ``packages/temper-geometry/src/channel_skeleton.rs`` for the port.

    Why an independent (spade, not GEOS) Voronoi is safe here: SAT
    channel-edge identity (``constraint_model.py::canonical_channel_edges``)
    is built from endpoints quantised to 1e-6 mm and ordered by that
    quantised key -- not from Voronoi emission order or raw float ``repr()``
    (fixed on ``fix/constraint-model-edge-identity``, the blocker recorded
    in three prior triage documents, most recently
    ``docs/evidence/2026-08-07-channel-skeleton-triage-no-port.md``). The
    2026-08-04 spike
    (``docs/evidence/2026-08-04-shapely-voronoi-channel-skeleton-spike.md``)
    measured an independent (Qhull) Voronoi reproducing the GEOS skeleton to
    <1e-9 mm on 12/12 boards -- three orders of magnitude finer than the
    1e-6 mm quantum -- and this migration re-verified the claim (12/12
    boards, both at the 1e-6 mm node-set level and directly on
    ``canonical_channel_edges()``-style ids) before porting.

    ``simplify_tolerance`` is threaded through for signature parity; it is
    a documented no-op on this path (spike §8: GEOS's Voronoi edges here
    are always exactly 2 coordinates, and Douglas-Peucker simplification of
    a 2-point line is the identity -- spade's undirected Voronoi edges are
    likewise always two circumcenters, so the same holds structurally).

    Args:
        polygon: Single polygon
        simplify_tolerance: Simplification tolerance (no-op; see above)

    Returns:
        List of LineStrings
    """
    outer = list(polygon.exterior.coords)
    holes = [list(interior.coords) for interior in polygon.interiors]
    segments = _tg.extract_medial_axis_single_py(outer, holes, simplify_tolerance)
    return [LineString([p1, p2]) for p1, p2 in segments]


def _ensure_skeleton_connectivity(G: nx.Graph, max_bridge_distance: float = 5.0) -> nx.Graph:
    """
    Ensure skeleton graph is fully connected by adding bridge edges.

    Args:
        G: Potentially fragmented skeleton graph
        max_bridge_distance: Maximum distance (mm) to bridge between islands

    Returns:
        Connected graph
    """
    if G.number_of_nodes() == 0:
        return G

    # Find connected components
    # nx.connected_components returns a generator of sets
    components = list(nx.connected_components(G))

    if len(components) <= 1:
        return G  # Already connected

    print(f"DEBUG: Skeleton has {len(components)} disconnected islands, bridging...")

    # Build bridges between components
    # We iteratively merge components until only one remains or we can't bridge any more
    current_components = components

    while len(current_components) > 1:
        best_bridge = None
        best_distance = float("inf")

        # Find closest pair of nodes between any two components
        # This is O(N^2) worst case but N is small (<2000 nodes)
        for i in range(len(current_components)):
            for j in range(i + 1, len(current_components)):
                comp_a = current_components[i]
                comp_b = current_components[j]

                for node_a in comp_a:
                    for node_b in comp_b:
                        # Nodes are (x, y) tuples
                        dist = ((node_a[0] - node_b[0]) ** 2 + (node_a[1] - node_b[1]) ** 2) ** 0.5

                        if dist < best_distance:
                            best_distance = dist
                            best_bridge = (node_a, node_b, i, j)

        if best_bridge is None or best_distance > max_bridge_distance:
            print(
                f"DEBUG: Warning: Cannot bridge islands (min distance: {best_distance:.1f}mm > {max_bridge_distance}mm)"
            )
            break

        # Add bridge edge
        node_a, node_b, comp_i, comp_j = best_bridge
        G.add_edge(node_a, node_b, weight=best_distance)
        print(f"DEBUG: Added bridge: {best_distance:.2f}mm")

        # Re-compute components to reflect the merge
        # (Naive re-compute is safer than manual set merging to keep logic simple)
        current_components = list(nx.connected_components(G))

    return G


class ChannelSkeletonStage(Stage):
    """Stage 2.3: Extract channel skeletons from routing spaces."""

    @property
    def name(self) -> str:
        return "ChannelSkeleton"

    def run(self, state: BoardState) -> BoardState:
        assert state._parsed_pcb is not None
        pcb: ParsedPCB = state._parsed_pcb
        routing_spaces = state.routing_spaces
        skeletons: dict[str, ChannelSkeleton] = {}
        # Was hardcoded to the two literal outer-copper layer names only --
        # a hardcode present since this stage's original implementation
        # (4bf34600), predating this board having a 4-layer stackup with
        # named inner routable layers. Once RoutingSpaceStage
        # (routing_space.py:85) already restricts `routing_spaces` to
        # routable layers, filtering again here to two hardcoded names
        # silently drops every other routable layer from ever getting a
        # channel skeleton -- regardless of whether it is present and
        # usable. Combined with the plane-condemnation quantifier bug (see
        # the use_declared_layer_roles=True comment in _pipeline_core.py),
        # this left state.channel_skeletons == {} even when routing_spaces
        # was non-empty (see
        # docs/evidence/2026-08-07-router-silent-noop-diagnosis.md, "Bug
        # B"). A 4-layer board should be able to use its inner layers, so
        # build a skeleton for every routable layer routing_spaces
        # actually contains.
        for layer_name, routing_space in routing_spaces.items():  # type: ignore[union-attr]
            skeleton = extract_channel_skeleton(routing_space, pcb=pcb)
            skeletons[layer_name] = skeleton
        return replace(state, channel_skeletons=skeletons)


@register_validator("ChannelSkeleton")
def validate_channel_skeleton(state: BoardState) -> list[StageDRCFailure]:
    """Validate channel skeleton invariants."""
    failures: list[StageDRCFailure] = []
    if state.channel_skeletons is None:
        failures.append(
            StageDRCFailure(
                field="channel_skeletons",
                value=None,
                reason="Channel skeletons not computed",
                stage="ChannelSkeleton",
            )
        )
        return failures

    for layer_name, skeleton in state.channel_skeletons.items():
        if skeleton.node_count == 0 and state.routing_spaces:
            rs = state.routing_spaces.get(layer_name)
            if rs and rs.routing_area > 0:
                failures.append(
                    StageDRCFailure(
                        field="channel_skeletons",
                        value=layer_name,
                        reason="Zero nodes on layer with positive routing area",
                        stage="ChannelSkeleton",
                    )
                )

    return failures
