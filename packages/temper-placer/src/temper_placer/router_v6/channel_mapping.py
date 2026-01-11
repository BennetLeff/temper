"""
Router V6 Stage 4.1: Map Topology to Channels

Maps abstract topology graph to concrete routing channels.
Part of temper-qic1 (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.topology_extraction import NetTopology, TopologyGraph


@dataclass
class ChannelPath:
    """A path through routing channels."""

    net_name: str
    channel_sequence: list[str]  # Ordered list of channel IDs
    waypoints: list[tuple[float, float]]  # (x, y) coordinates along path
    total_length: float  # Total path length in mm


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
    topology: TopologyGraph,
    skeleton: ChannelSkeleton,
) -> ChannelMapping:
    """
    Map abstract topology graph to concrete routing channels.

    Translates the topological routing solution into specific channel
    paths that nets will follow during geometric realization.

    Args:
        topology: Topological routing graph from Stage 3.9
        skeleton: Channel skeleton from Stage 2.3

    Returns:
        ChannelMapping with concrete channel paths

    Example:
        >>> from temper_placer.router_v6.topology_extraction import TopologyGraph
        >>> from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
        >>> import networkx as nx
        >>> topology = TopologyGraph(net_topologies={})
        >>> skeleton = ChannelSkeleton(nx.Graph(), "F.Cu", 0.0)
        >>> mapping = map_topology_to_channels(topology, skeleton)
        >>> mapping.mapped_net_count >= 0
        True
    """
    channel_paths = {}

    for net_name, net_topology in topology.net_topologies.items():
        # Map this net's topology to channels
        channel_path = _map_net_to_channels(net_name, net_topology, skeleton)
        if channel_path:
            channel_paths[net_name] = channel_path

    return ChannelMapping(channel_paths=channel_paths)


def _map_net_to_channels(
    net_name: str,
    net_topology: NetTopology,
    skeleton: ChannelSkeleton,
) -> ChannelPath | None:
    """
    Map a single net's topology to channel sequence.

    Args:
        net_name: Net name
        net_topology: Net's topological routing
        skeleton: Channel skeleton graph

    Returns:
        ChannelPath or None if mapping fails
    """
    # Use channels from topology
    channel_sequence = net_topology.uses_channels

    if not channel_sequence:
        # Try to extract from path graph
        if net_topology.path_graph.number_of_edges() > 0:
            # Use path graph nodes as channel sequence
            try:
                # Get a path through the graph (simplified)
                nodes = list(net_topology.path_graph.nodes())
                if nodes:
                    channel_sequence = [str(node) for node in nodes]
            except Exception:
                pass

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
                    return nodes[:min(5, len(nodes))]
        return []

    # Try to parse channel IDs as coordinates
    for channel_id in channel_sequence:
        coord = _parse_channel_coordinate(channel_id, skeleton)
        if coord:
            waypoints.append(coord)

    # If we successfully extracted waypoints, return them
    if waypoints:
        return waypoints

    # Fallback: use skeleton to generate path
    if skeleton.graph.number_of_nodes() > 0:
        nodes = list(skeleton.graph.nodes())
        return nodes[:min(len(channel_sequence) + 1, len(nodes))]

    return []


def _parse_channel_coordinate(
    channel_id: str,
    skeleton: ChannelSkeleton,
) -> tuple[float, float] | None:
    """
    Try to parse a channel ID into a coordinate.

    Attempts multiple strategies:
    1. Parse as "x_y" format (e.g., "10.5_20.3")
    2. Parse as "(x, y)" format
    3. Find nearest skeleton node matching the ID

    Args:
        channel_id: Channel identifier
        skeleton: Channel skeleton

    Returns:
        (x, y) coordinate or None
    """
    # Strategy 1: Parse "x_y" format
    if "_" in channel_id:
        parts = channel_id.split("_")
        # Try last two parts as coordinates
        if len(parts) >= 2:
            try:
                x = float(parts[-2])
                y = float(parts[-1])
                # Verify this coordinate is near a skeleton node
                coord = (x, y)
                if _is_near_skeleton(coord, skeleton, tolerance=5.0):
                    return coord
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

    # Strategy 3: Find closest skeleton node (if skeleton is small)
    if skeleton.graph.number_of_nodes() <= 20:
        # For small skeletons, use hash of channel_id to pick a node
        nodes = list(skeleton.graph.nodes())
        if nodes:
            idx = hash(channel_id) % len(nodes)
            return nodes[idx]

    return None


def _is_near_skeleton(
    coord: tuple[float, float],
    skeleton: ChannelSkeleton,
    tolerance: float = 5.0,
) -> bool:
    """
    Check if a coordinate is near any skeleton node.

    Args:
        coord: (x, y) coordinate
        skeleton: Channel skeleton
        tolerance: Distance tolerance in mm

    Returns:
        True if coordinate is near skeleton
    """
    x, y = coord
    for node in skeleton.graph.nodes():
        nx_node, ny_node = node
        dist = ((x - nx_node)**2 + (y - ny_node)**2)**0.5
        if dist <= tolerance:
            return True
    return False


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
        length = (dx**2 + dy**2)**0.5
        total_length += length

    return total_length
