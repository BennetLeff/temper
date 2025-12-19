"""
Graph utilities for netlist analysis.

This module provides tools to convert the netlist into a graph representation
suitable for spectral analysis and force-directed layout algorithms.
"""

from __future__ import annotations

import networkx as nx

from temper_placer.core.netlist import Netlist


class GraphBuilder:
    """
    Builds weighted graphs from netlists.

    Nodes represent components, and edges represent electrical connections.
    Weights are derived from net classes and criticality.
    """

    def __init__(self, netlist: Netlist):
        self.netlist = netlist

    def build_graph(self) -> nx.Graph:
        """
        Convert netlist to a weighted networkx Graph.

        Returns:
            nx.Graph where nodes are component refs and edges are weighted connections.
        """
        G = nx.Graph()

        # Add nodes with component attributes
        for comp in self.netlist.components:
            G.add_node(
                comp.ref,
                width=comp.width,
                height=comp.height,
                fixed=comp.fixed,
                area=comp.width * comp.height,
            )

        # Add edges based on nets
        for net in self.netlist.nets:
            # Skip empty nets or single-pin nets
            if len(net.pins) < 2:
                continue

            refs = list(net.get_component_refs())
            if len(refs) < 2:
                continue

            # Determine base weight based on net class
            weight = net.weight

            # Boost weight for critical nets
            if net.net_class == "Critical":
                weight *= 10.0
            elif net.net_class == "Power":
                weight *= 2.0  # Keep power components somewhat close
            elif net.net_class == "HighVoltage":
                # High voltage might need separation, but for connectivity
                # graph we usually want them clustered unless we have explicit repulsion.
                # Standard practice: keep them together but isolate the cluster.
                weight *= 1.5

            # Clique expansion model:
            # For a net with k pins, we connect all pairs.
            # To avoid over-weighting large nets (like GND), we scale by 1/(k-1).
            k = len(refs)
            scale_factor = 1.0 / (k - 1)
            final_weight = weight * scale_factor

            # Add edges between all pairs in the net
            for i in range(len(refs)):
                for j in range(i + 1, len(refs)):
                    u, v = refs[i], refs[j]
                    if G.has_edge(u, v):
                        G[u][v]["weight"] += final_weight
                    else:
                        G.add_edge(u, v, weight=final_weight)

        return G
