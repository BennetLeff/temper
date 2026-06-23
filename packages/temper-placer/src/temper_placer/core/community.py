"""
Community detection for netlist functional grouping.

This module provides functions to automatically identify functional clusters
of components using graph community detection algorithms (Louvain).
"""

from __future__ import annotations

from dataclasses import dataclass

import community as community_louvain
import networkx as nx
import numpy as np

from temper_placer.core.netlist import Netlist
from temper_placer.optimizer.initialization import build_adjacency_matrix


@dataclass
class Community:
    """A detected functional cluster of components."""
    name: str
    component_refs: list[str]
    modularity_score: float


@dataclass
class ComponentCommunity:
    """A community membership record for a single component.

    Re-exported via :mod:`temper_placer.core` for backward compatibility with
    downstream callers that import ``ComponentCommunity`` from the public
    package interface.
    """

    component_ref: str
    community_name: str
    confidence: float = 1.0

def detect_communities(netlist: Netlist) -> list[Community]:
    """
    Detect functional communities in the netlist using the Louvain algorithm.

    Args:
        netlist: The netlist to analyze.

    Returns:
        List of Community objects representing detected functional blocks.
    """
    if netlist.n_components == 0:
        return []

    # 1. Build adjacency matrix
    # adjacency is a symmetric JAX Array (N, N)
    adj_matrix = build_adjacency_matrix(netlist)
    adj_np = np.array(adj_matrix)

    # 2. Create NetworkX graph
    G = nx.from_numpy_array(adj_np)

    # Map node indices back to component references
    idx_to_ref = {i: comp.ref for i, comp in enumerate(netlist.components)}

    # 3. Apply Louvain algorithm for community detection
    # partition is a dict: {node_idx: community_id}
    partition = community_louvain.best_partition(G, weight='weight', random_state=42)

    # 4. Group by community ID
    community_groups: dict[int, list[str]] = {}
    for node_idx, comm_id in partition.items():
        if comm_id not in community_groups:
            community_groups[comm_id] = []
        community_groups[comm_id].append(idx_to_ref[node_idx])

    # 5. Compute modularity score
    modularity = community_louvain.modularity(partition, G, weight='weight')

    # 6. Create Community objects
    communities = []
    for comm_id, refs in community_groups.items():
        # Ignore single-component communities (noise)
        if len(refs) > 1:
            communities.append(Community(
                name=f"auto_community_{comm_id}",
                component_refs=refs,
                modularity_score=modularity
            ))

    return communities

def get_community_component_indices(netlist: Netlist, community: Community) -> list[int]:
    """Resolve component references in a community to netlist indices."""
    return [netlist.get_component_index(ref) for ref in community.component_refs]


def partition_netlist_min_cut(netlist: Netlist, n_parts: int = 2) -> list[list[int]]:
    """
    Partition the netlist into n_parts using recursive min-cut bisection.

    Uses the Kernighan-Lin algorithm to find partitions that minimize
    the number of nets crossing between them (cut size).

    Args:
        netlist: The netlist to partition.
        n_parts: Number of partitions (must be power of 2 for simplicity).

    Returns:
        List of component index lists (one for each partition).
    """
    if netlist.n_components == 0:
        return []

    # 1. Build adjacency matrix and graph
    adj_matrix = build_adjacency_matrix(netlist)
    G = nx.from_numpy_array(np.array(adj_matrix))

    # 2. Recursive bisection
    def bisect(nodes):
        if len(nodes) <= 1:
            return [nodes]
        # Kernighan-Lin bisection
        subgraph = G.subgraph(nodes)
        try:
            part1, part2 = nx.community.kernighan_lin_bisection(subgraph, weight="weight")
            return [list(part1), list(part2)]
        except Exception:
            # Fallback if KL fails
            mid = len(nodes) // 2
            return [nodes[:mid], nodes[mid:]]

    # Start with all nodes
    all_indices = list(range(netlist.n_components))
    current_partitions = [all_indices]

    # Bisect until we have enough parts
    import math

    steps = int(math.ceil(math.log2(n_parts)))
    for _ in range(steps):
        new_partitions = []
        for part in current_partitions:
            if len(part) > 1:
                new_partitions.extend(bisect(part))
            else:
                new_partitions.append(part)
        current_partitions = new_partitions

    return current_partitions[:n_parts]
