"""
Router V6 Stage 3.9: Extract Topology Solution

Extracts routing topology from SAT solution.
Part of temper-8qm8 (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from temper_placer.router_v6.topology_solver import TopologicalSolution


@dataclass
class NetTopology:
    """Topological routing for a single net."""

    net_name: str
    path_graph: nx.DiGraph  # Directed graph representing routing topology
    uses_channels: list[str]  # Channel IDs used by this net
    total_length_estimate: float  # Estimated total length (mm)


@dataclass
class TopologyGraph:
    """Complete topological routing graph for the design."""

    net_topologies: dict[str, NetTopology]  # net_name -> NetTopology

    @property
    def routed_net_count(self) -> int:
        """Number of nets with routing topology."""
        return len(self.net_topologies)

    def get_topology(self, net_name: str) -> NetTopology | None:
        """Get topology for a specific net."""
        return self.net_topologies.get(net_name)


def extract_topology_solution(
    solution: TopologicalSolution,
    net_names: list[str],
) -> TopologyGraph:
    """
    Extract routing topology from SAT solution.

    Converts boolean variable assignments into a routing graph that
    specifies which channels each net uses and how they connect.

    Args:
        solution: Solved topological solution from Stage 3.8
        net_names: List of nets to extract topology for

    Returns:
        TopologyGraph with routing topology for all nets

    Example:
        >>> from temper_placer.router_v6.topology_solver import SolverStatus
        >>> solution = TopologicalSolution(SolverStatus.SATISFIABLE, {}, 1.0)
        >>> topology = extract_topology_solution(solution, ["NET1", "NET2"])
        >>> topology.routed_net_count >= 0
        True
    """
    if not solution.is_satisfiable:
        # No solution available
        return TopologyGraph(net_topologies={})

    net_topologies = {}

    for net_name in net_names:
        # Extract topology for this net
        net_topology = _extract_net_topology(solution, net_name)
        if net_topology:
            net_topologies[net_name] = net_topology

    return TopologyGraph(net_topologies=net_topologies)


def _extract_net_topology(
    solution: TopologicalSolution,
    net_name: str,
) -> NetTopology | None:
    """
    Extract topology for a single net from SAT solution.

    Args:
        solution: Topological solution
        net_name: Net to extract

    Returns:
        NetTopology or None if net has no routing
    """
    # Create directed graph for this net's routing
    path_graph = nx.DiGraph()
    uses_channels = []

    # Parse solution to find variables related to this net
    for var_name, value in solution.assignment.items():
        if not value:
            # Variable is False, skip
            continue

        # Look for routing variables for this net
        # Format: "route_{net}_{source}_to_{sink}" or "uses_{net}_{channel}"
        if f"route_{net_name}_" in var_name or f"uses_{net_name}_" in var_name:
            if "route_" in var_name:
                # Extract source and sink from variable name
                parts = var_name.split("_")
                if len(parts) >= 4:
                    # Find source and sink nodes
                    try:
                        to_idx = parts.index("to")
                        source = "_".join(parts[2:to_idx])
                        sink = "_".join(parts[to_idx+1:])

                        # Add edge to path graph
                        path_graph.add_edge(source, sink)
                    except (ValueError, IndexError):
                        pass

            elif "uses_" in var_name:
                # Extract channel ID
                parts = var_name.split("_")
                if len(parts) >= 3:
                    channel_id = "_".join(parts[2:])
                    uses_channels.append(channel_id)

    # Estimate path length (simplified)
    total_length = len(path_graph.edges) * 10.0  # Assume 10mm per hop

    if path_graph.number_of_nodes() > 0 or uses_channels:
        return NetTopology(
            net_name=net_name,
            path_graph=path_graph,
            uses_channels=uses_channels,
            total_length_estimate=total_length,
        )

    return None
