"""
Graph representation for netlists.

Provides JAX-compatible data structures for ML-based placement quality
prediction and learned initialization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

import jax.numpy as jnp
from jax import Array

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
    n = netlist.n_components
    
    # 1. Node Features: [Area, PinCount, Fixed]
    areas = jnp.array([c.width * c.height for c in netlist.components])
    pin_counts = jnp.array([len(c.pins) for c in netlist.components])
    fixed = jnp.array([1.0 if c.fixed else 0.0 for c in netlist.components])
    
    nodes = jnp.stack([areas, pin_counts, fixed], axis=-1)
    
    # 2. Edges (Clique expansion of nets)
    edge_sources = []
    edge_targets = []
    edge_weights = []
    
    comp_refs = {c.ref: i for i, c in enumerate(netlist.components)}
    
    for net in netlist.nets:
        # Get component indices in this net
        indices = list(set(comp_refs[p[0]] for p in net.pins if p[0] in comp_refs))
        
        # Clique expansion: connect all pairs
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                u, v = indices[i], indices[j]
                edge_sources.append(u)
                edge_targets.append(v)
                edge_weights.append(net.weight)
                
    if not edge_sources:
        edges = jnp.zeros((0, 2), dtype=jnp.int32)
        weights = jnp.zeros((0,))
    else:
        edges = jnp.stack([jnp.array(edge_sources), jnp.array(edge_targets)], axis=-1)
        weights = jnp.array(edge_weights)
        
    return NetlistGraph(nodes=nodes, edges=edges, edge_weights=weights)


def batch_graphs(graphs: List[NetlistGraph]) -> NetlistGraph:
    """
    Batch multiple graphs into a single large disconnected graph.

    Shifts edge indices to maintain graph structure in the unified representation.

    Args:
        graphs: List of NetlistGraph instances.

    Returns:
        Unified NetlistGraph.
    """
    all_nodes = jnp.concatenate([g.nodes for g in graphs], axis=0)
    
    shifted_edges = []
    offset = 0
    for g in graphs:
        shifted_edges.append(g.edges + offset)
        offset += g.nodes.shape[0]
        
    all_edges = jnp.concatenate(shifted_edges, axis=0)
    all_weights = jnp.concatenate([g.edge_weights for g in graphs], axis=0)
    
    return NetlistGraph(nodes=all_nodes, edges=all_edges, edge_weights=all_weights)
