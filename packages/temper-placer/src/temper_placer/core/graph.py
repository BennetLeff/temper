"""
Graph representation for netlists.

Provides JAX-compatible data structures for ML-based placement quality
prediction and learned initialization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple
import numpy as np
Array = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist


class NetlistGraph(NamedTuple):
    """
    JAX-compatible graph representation of a netlist.

    Attributes:
        nodes: (N, F) node features (area, pin count, etc.).
        edges: (E, 2) edge indices (source, target).
        edge_weights: (E,) importance weights for each connection.
    """
    nodes: Array
    edges: Array
    edge_weights: Array


def netlist_to_graph(netlist: Netlist) -> NetlistGraph:
    """
    Convert a netlist to a graph representation.

    Args:
        netlist: The netlist to convert.

    Returns:
        NetlistGraph instance.
    """

    # 1. Node Features: [Area, PinCount, Fixed]
    areas = np.array([c.width * c.height for c in netlist.components])
    pin_counts = np.array([len(c.pins) for c in netlist.components])
    fixed = np.array([1.0 if c.fixed else 0.0 for c in netlist.components])

    nodes = np.stack([areas, pin_counts, fixed], axis=-1)

    # 2. Edges (Clique expansion of nets)
    edge_sources = []
    edge_targets = []
    edge_weights = []

    comp_refs = {c.ref: i for i, c in enumerate(netlist.components)}

    for net in netlist.nets:
        # Get component indices in this net
        indices = list({comp_refs[p[0]] for p in net.pins if p[0] in comp_refs})

        # Clique expansion: connect all pairs
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                u, v = indices[i], indices[j]
                edge_sources.append(u)
                edge_targets.append(v)
                edge_weights.append(net.weight)

    if not edge_sources:
        edges = np.zeros((0, 2), dtype=np.int32)
        weights = np.zeros((0,))
    else:
        edges = np.stack([np.array(edge_sources), np.array(edge_targets)], axis=-1)
        weights = np.array(edge_weights)

    return NetlistGraph(nodes=nodes, edges=edges, edge_weights=weights)


def batch_graphs(graphs: list[NetlistGraph]) -> NetlistGraph:
    """
    Batch multiple graphs into a single large disconnected graph.

    Shifts edge indices to maintain graph structure in the unified representation.

    Args:
        graphs: List of NetlistGraph instances.

    Returns:
        Unified NetlistGraph.
    """
    all_nodes = np.concatenate([g.nodes for g in graphs], axis=0)

    shifted_edges = []
    offset = 0
    for g in graphs:
        shifted_edges.append(g.edges + offset)
        offset += g.nodes.shape[0]

    all_edges = np.concatenate(shifted_edges, axis=0)
    all_weights = np.concatenate([g.edge_weights for g in graphs], axis=0)

    return NetlistGraph(nodes=all_nodes, edges=all_edges, edge_weights=all_weights)
