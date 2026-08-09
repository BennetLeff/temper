"""
Graph representation for netlists.

Provides numpy-compatible data structures for ML-based placement quality
prediction and learned initialization.

Wave 4 (unit ``core_graph_cluster``): the compute kernels are migrated to
``packages/temper-geometry/src/core_graph_geometry.rs`` — the net clique
expansion (``netlist_to_graph``) and the batch offset-shift/concatenation
(``batch_graphs``). The numpy *constructor* steps (``np.stack`` /
``np.concatenate`` / dtype selection) stay here because numpy's construction
semantics are a library boundary; the quadratic clique loop and the int64
offset shifts run in Rust. Bit-exact parity is pinned by
``tests/core/test_core_graph_cluster_rust_differential.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, TypeAlias

import numpy as np
import temper_geometry as _tg

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

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
    # (per-component one-multiply map — kept here; the quadratic clique
    # expansion below is the migrated compute, in Rust.)
    areas = np.array([c.width * c.height for c in netlist.components])
    pin_counts = np.array([len(c.pins) for c in netlist.components])
    fixed = np.array([1.0 if c.fixed else 0.0 for c in netlist.components])

    nodes = np.stack([areas, pin_counts, fixed], axis=-1)

    # 2. Edges (Clique expansion of nets) — Rust kernel.
    # The per-net index list is built here with the oracle's exact CPython
    # `set` comprehension so its iteration order (and therefore the pair
    # order) is identical on both sides.
    comp_refs = {c.ref: i for i, c in enumerate(netlist.components)}

    net_indices = []
    net_weights = []
    for net in netlist.nets:
        indices = list({comp_refs[p[0]] for p in net.pins if p[0] in comp_refs})
        net_indices.append(indices)
        net_weights.append(net.weight)

    edge_sources, edge_targets, edge_weights = _tg.graph_clique_expand_py(
        net_indices, net_weights
    )

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
    if not graphs:
        raise ValueError("need at least one array to concatenate")

    # The node/edge/weight concatenation and the per-graph int64 offset shift
    # run in Rust (`graph_batch_concat`); numpy does the final constructor.
    node_flats = [g.nodes.ravel().tolist() for g in graphs]
    edge_flats = [g.edges.ravel().tolist() for g in graphs]
    weight_flats = [g.edge_weights.tolist() for g in graphs]

    all_nodes_flat, all_edges_flat, all_weights = _tg.graph_batch_concat_py(
        node_flats, edge_flats, weight_flats
    )

    all_nodes = np.array(all_nodes_flat).reshape(-1, 3)
    # The oracle concatenates the SHIFTED edge arrays: all-empty graphs keep
    # the empty branch's int32 dtype; any non-empty int64 edge promotes the
    # result to int64. Replicate both cases.
    if all_edges_flat:
        all_edges = np.array(all_edges_flat).reshape(-1, 2)
    else:
        all_edges = np.zeros((0, 2), dtype=np.int32)
    all_weights = np.array(all_weights)

    return NetlistGraph(nodes=all_nodes, edges=all_edges, edge_weights=all_weights)
