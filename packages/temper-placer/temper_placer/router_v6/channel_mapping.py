"""
Router V6 Stage 4.1: Map Topology to Channels

Maps abstract topology graph to concrete routing channels.
Part of temper-qic1 (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from temper_placer.core.netlist import Component, Net
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.topology_extraction import NetTopology, TopologyGraph


@dataclass
class ChannelPath:
    """A path through routing channels."""

    net_name: str
    channel_sequence: list[str]  # Ordered list of channel IDs
    waypoints: list[tuple[float, float]]  # (x, y) coordinates along path
    total_length: float  # Total path length in mm
    preferred_layer: str = "F.Cu"  # Layer assignment for multi-layer routing


def _assign_layer(
    net_name: str,
    design_rules=None,
    competing_nets: set[str] | None = None
) -> str:
    """
    Assign net to preferred layer based on configuration hierarchy:
    
    1. Explicit layer constraint from YAML/design rules
    2. Power net heuristic (GND/VCC → B.Cu)
    3. Competing net alternation (oscillation prevention)
    4. Default (F.Cu)
    
    Professional PCB design principle:
    Layer assignment should come from design intent (YAML config),
    not hardcoded logic. This allows designers to specify routing strategy.
    """
    # 1. Check design rules for explicit layer constraint
    if design_rules:
        layer_constraint = design_rules.get_layer_constraint(net_name)
        if layer_constraint:
            return layer_constraint
    
    # 2. Power net heuristic (fallback)
    name_upper = net_name.upper()
    power_keywords = ["GND", "VCC", "VBUS", "+", "PWR", "V+", "V-"]
    if any(kw in name_upper for kw in power_keywords):
        return "B.Cu"
    
    # 3. Competing nets alternation (for nets without explicit constraint)
    # This prevents oscillation for parallel signals
    if competing_nets and net_name in competing_nets:
        # Deterministic alternation based on name hash
        if hash(net_name) % 2 == 0:
            return "F.Cu"
        else:
            return "B.Cu"
    
    # 4. Default
    return "F.Cu"


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
    nets: list[Net] | None = None,
    components: list[Component] | None = None,
    design_rules=None,  # Pass design rules for layer assignment
) -> ChannelMapping:
    """
    Map abstract topology graph to concrete routing channels.

    Args:
        topology: Topological routing graph
        skeleton: Channel skeleton
        nets: List of nets (optional, for fallback)
        components: List of components (optional, for pin lookup in fallback)
        design_rules: Design rules (optional, for layer assignment)

    Returns:
        ChannelMapping
    """
    channel_paths = {}

    # Use nets list if provided, otherwise infer from topology
    net_names = [net.name for net in nets] if nets else list(topology.net_topologies.keys())
    
    # Map for easy net lookup
    net_map = {net.name: net for net in nets} if nets else {}

    # Component lookup
    comp_map = {c.ref: c for c in components} if components else {}

    for net_name in net_names:
        net_topology = topology.get_topology(net_name)
        net_obj = net_map.get(net_name)
        
        # Map this net's topology (or fallback) to channels
        channel_path = _map_net_to_channels(net_name, net_topology, skeleton, net_obj, comp_map, design_rules)
        if channel_path:
            channel_paths[net_name] = channel_path

    return ChannelMapping(channel_paths=channel_paths)


def _map_net_to_channels(
    net_name: str,
    net_topology: NetTopology | None,
    skeleton: ChannelSkeleton,
    net_obj: Net | None = None,
    comp_map: dict[str, Component] | None = None,
    design_rules=None,
) -> ChannelPath | None:
    """
    Map a single net's topology to channel sequence.

    Args:
        net_name: Net name
        net_topology: Net's topological routing (can be None)
        skeleton: Channel skeleton graph
        net_obj: Net object for fallback (optional)
        comp_map: Component lookup map (optional)

    Returns:
        ChannelPath or None if mapping fails
    """
    channel_sequence = []

    # 1. Prefer Geometric Routing (Fallback) if available
    # The topological solver (Stage 3) is currently a mock that returns random edges.
    # To ensure connectivity, we bypass it and use Dijkstra on the skeleton directly.
    # This works well in conjunction with Rip-up and Reroute (Stage 4).
    if net_obj and comp_map and skeleton.graph.number_of_nodes() > 0:
        channel_sequence = _find_skeleton_path_for_net(net_obj, comp_map, skeleton)

    # 2. Use Topology as backup (if net_obj not provided or fallback failed)
    if not channel_sequence and net_topology:
        channel_sequence = net_topology.uses_channels

        if not channel_sequence:
            # Try to extract from path graph
            if net_topology.path_graph.number_of_edges() > 0:
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
            preferred_layer=_assign_layer(net_name, design_rules=design_rules),
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

    import re

    # Try to parse channel IDs as coordinates
    for channel_id in channel_sequence:
        # Check for multiple coordinates in ID (Edge ID)
        # Format: ..._(x1, y1)_(x2, y2)
        coord_matches = re.findall(r'\(([^)]+)\)', channel_id)
        if len(coord_matches) >= 2:
            # Edge with start/end points
            found_edge_points = False
            for match in coord_matches:
                try:
                    parts = match.split(',')
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


def _find_skeleton_path_for_net(
    net: Net,
    comp_map: dict[str, Component],
    skeleton: ChannelSkeleton,
) -> list[str]:
    """
    Find a path on the skeleton graph connecting net pins.

    Args:
        net: Net to route
        comp_map: Component lookup map
        skeleton: Channel skeleton

    Returns:
        List of channel IDs (edge IDs) or nodes representing the path
    """
    import math
    if not net.pins:
        return []

    # Get absolute positions of pins
    pin_positions = []
    for comp_ref, pin_name in net.pins:
        comp = comp_map.get(comp_ref)
        if comp:
            pin = comp.get_pin(pin_name)
            if pin:
                comp_x, comp_y = comp.initial_position or (0.0, 0.0)
                angle = float(comp.initial_rotation or 0) * math.pi / 2.0
                side = comp.initial_side if hasattr(comp, 'initial_side') and comp.initial_side is not None else 0
                pos = pin.absolute_position((comp_x, comp_y), angle, side)
                pin_positions.append(pos)
    
    if len(pin_positions) < 2:
        return []

    # Find nearest skeleton node for each pin
    skeleton_nodes = []
    for pos in pin_positions:
        node = _find_nearest_node(pos, skeleton)
        if node:
            skeleton_nodes.append(node)
    
    # Remove duplicates (multiple pins mapping to same node)
    skeleton_nodes = list(dict.fromkeys(skeleton_nodes))
    # Sort nodes using Greedy TSP (Nearest Neighbor) to minimize path length
    # This prevents zigzagging across the board for large nets (GND/VCC)
    if len(skeleton_nodes) > 2:
        sorted_nodes = [skeleton_nodes[0]]
        unvisited = set(skeleton_nodes[1:])
        
        while unvisited:
            current = sorted_nodes[-1]
            # Find nearest unvisited
            nearest = None
            min_dist = float('inf')
            
            for candidate in unvisited:
                # Euclidean distance squared
                dist = (current[0] - candidate[0])**2 + (current[1] - candidate[1])**2
                if dist < min_dist:
                    min_dist = dist
                    nearest = candidate
            
            sorted_nodes.append(nearest)
            unvisited.remove(nearest)
        
        skeleton_nodes = sorted_nodes

    if len(skeleton_nodes) < 2:
        return []

    # SIMPLIFIED OUTPUT: Return only terminal skeleton nodes
    # The A* router handles detailed pathfinding between these points.
    # This prevents waypoint explosion (e.g., GND: 533 → ~20 waypoints)
    
    # Validate connectivity using Dijkstra (but don't output intermediate nodes)
    connected_terminals = [skeleton_nodes[0]]
    
    for i in range(len(skeleton_nodes) - 1):
        start = skeleton_nodes[i]
        end = skeleton_nodes[i+1]
        try:
            # Check path exists (validates skeleton connectivity)
            nx.shortest_path(skeleton.graph, start, end, weight='weight')
            # Only add the terminal, not intermediate nodes
            connected_terminals.append(end)
        except nx.NetworkXNoPath:
            # Skip unreachable nodes
            pass
    
    # Convert nodes to str IDs (these are the waypoints the A* will route between)
    return [str(node) for node in connected_terminals]


def _find_nearest_node(
    pos: tuple[float, float],
    skeleton: ChannelSkeleton,
) -> tuple[float, float] | None:
    """Find nearest skeleton node to position."""
    best_node = None
    best_dist = float('inf')
    
    # Optimization: Check if graph has nodes
    if skeleton.graph.number_of_nodes() == 0:
        return None
        
    # Naive search (O(N)) - acceptable for ~2k nodes
    # For 33 nets, 33 * 2 * 2000 = 132k ops (fast)
    px, py = pos
    for node in skeleton.graph.nodes:
        nx_val, ny_val = node
        dist = (px - nx_val)**2 + (py - ny_val)**2
        if dist < best_dist:
            best_dist = dist
            best_node = node
            
    # Max snap distance 10mm (generous)
    if best_dist > 100.0: # squared
        return None
        
    return best_node


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
