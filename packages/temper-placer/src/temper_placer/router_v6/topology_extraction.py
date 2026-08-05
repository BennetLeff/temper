"""
Router V6 Stage 3.9: Topology graph types.

The topology graph is built directly from the Rust solver result in
``_pipeline_route`` (see ``rust_result["topology_graph"]``); this module owns
only the dataclasses that result is marshalled into.
Part of temper-8qm8 (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


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
