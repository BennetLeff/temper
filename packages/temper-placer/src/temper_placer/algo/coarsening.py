"""
Multilevel coarsening algorithms for Hypergraphs.

This module implements Heavy Edge Matching (HEM) to reduce the complexity
of the hypergraph while preserving structural properties.
"""

from __future__ import annotations

import jax.numpy as jnp
import numpy as np
from jax.experimental import sparse

from temper_placer.core.hypergraph import HypergraphIncidence, PhysicsHypergraph


def coarsen_hypergraph(
    hg: PhysicsHypergraph,
    reduction_ratio: float = 0.5
) -> tuple[PhysicsHypergraph, sparse.BCOO]:
    """
    Coarsen the hypergraph using Heavy Edge Matching (HEM).

    Args:
        hg: The fine-grained PhysicsHypergraph.
        reduction_ratio: Target ratio of coarse nodes to fine nodes (e.g., 0.5 means halve the nodes).

    Returns:
        tuple: (CoarsePhysicsHypergraph, ProjectionMatrix)

        The ProjectionMatrix P is (N_fine, N_coarse).
        P[i, j] = 1 if fine node i belongs to coarse node j.

        Positions can be projected: pos_fine = P @ pos_coarse
    """
    # 1. Move to CPU/Numpy for structural graph operations (Matching is hard to vectorize)
    # We use the dense representation for matching logic if N is small (<10k),
    # which is true for PCBs.
    n_fine = hg.n_nodes

    if n_fine < 2:
        # Cannot coarsen
        identity = sparse.BCOO.fromdense(jnp.eye(n_fine))
        return hg, identity

    # Reconstruct connectivity for matching
    # A_clique = H W H.T (approximate)
    # Actually, we just need pairwise affinities.

    # Extract BCOO data to numpy
    H_indices = np.array(hg.incidence.matrix.indices)
    np.array(hg.incidence.matrix.data)
    edge_weights = np.array(hg.incidence.hyperedge_weights)

    # Build adjacency list: node -> set of (neighbor, weight)
    # Ideally we compute the clique expansion weights:
    # w(u,v) = sum(w(e) / (|e| - 1)) for e containing u,v

    # Compute edge sizes
    edge_sizes = np.zeros(hg.n_edges)
    np.add.at(edge_sizes, H_indices[:, 1], 1)

    # Valid edges for affinity (size >= 2)
    valid_mask = edge_sizes >= 2

    # Build pairwise affinity matrix (sparse)
    # This is O(N_pins^2) in worst case (massive net), but we filtered global nets already.

    from collections import defaultdict
    affinity = defaultdict(float)

    # Group nodes by edge
    edge_to_nodes = defaultdict(list)
    for i in range(len(H_indices)):
        node_idx = H_indices[i, 0]
        edge_idx = H_indices[i, 1]
        if valid_mask[edge_idx]:
            edge_to_nodes[edge_idx].append(node_idx)

    for edge_idx, nodes in edge_to_nodes.items():
        w = edge_weights[edge_idx] / (len(nodes) - 1)
        # Add to all pairs
        for i in range(len(nodes)):
            u = nodes[i]
            for j in range(i + 1, len(nodes)):
                v = nodes[j]
                # Canonical pair key
                key = tuple(sorted((u, v)))
                affinity[key] += w

    # 2. Heavy Edge Matching (Greedy)
    # Target coarse-node count: ceil(ratio * n_fine) at minimum to honor
    # the requested reduction; greedy matching stops once we have enough
    # matches to reach the target so we don't over-coarsen.
    target_n_coarse = max(1, int(round(reduction_ratio * n_fine)))
    target_n_matches = max(0, n_fine - target_n_coarse)

    matched = np.zeros(n_fine, dtype=bool)
    matches = [] # List of (u, v) tuples

    # Sort pairs by weight descending
    sorted_pairs = sorted(affinity.items(), key=lambda x: x[1], reverse=True)

    for (u, v), _w in sorted_pairs:
        if len(matches) >= target_n_matches:
            break
        if not matched[u] and not matched[v]:
            matched[u] = True
            matched[v] = True
            matches.append((u, v))

    # Handle unmatched nodes (singletons)
    singletons = np.where(~matched)[0]

    # 3. Build Projection Matrix P (Fine -> Coarse)
    n_coarse = len(matches) + len(singletons)

    P_rows = []
    P_cols = []
    P_data = []

    # Mappings for reconstruction
    coarse_node_refs = []

    # Add matched pairs
    for coarse_idx, (u, v) in enumerate(matches):
        # u -> coarse_idx
        P_rows.append(u)
        P_cols.append(coarse_idx)
        P_data.append(1.0)

        # v -> coarse_idx
        P_rows.append(v)
        P_cols.append(coarse_idx)
        P_data.append(1.0)

        # Name: "Merged_U1_U2"
        ref_u = hg.node_refs[u]
        ref_v = hg.node_refs[v]
        coarse_node_refs.append(f"M_{ref_u}_{ref_v}")

    # Add singletons
    offset = len(matches)
    for i, u in enumerate(singletons):
        coarse_idx = offset + i
        P_rows.append(u)
        P_cols.append(coarse_idx)
        P_data.append(1.0)

        coarse_node_refs.append(hg.node_refs[u])

    P_indices = jnp.array([P_rows, P_cols]).T
    P_values = jnp.array(P_data, dtype=jnp.float32)
    P = sparse.BCOO((P_values, P_indices), shape=(n_fine, n_coarse))

    # 4. Build Coarse Hypergraph Incidence H_c = P.T @ H
    # Note: P is (Fine, Coarse). We want H_coarse to be (Coarse, Edge).
    # H_fine is (Fine, Edge).
    # H_coarse = P.T @ H_fine

    H_fine = hg.incidence.matrix
    H_coarse_bcoo = P.T @ H_fine

    # 5. Aggregate Node Weights
    node_weights_fine = hg.incidence.node_weights
    # w_coarse = P.T @ w_fine
    node_weights_coarse = P.T @ node_weights_fine

    # 6. Hyperedge weights stay the same
    # But we might want to filter out edges that collapsed (became loops)
    # A hyperedge is a loop if it only connects to 1 coarse node.
    # We can detect this by checking degree of H_coarse columns.
    # For now, we keep them (degree 1 edges don't affect Laplacian anyway).

    coarse_incidence = HypergraphIncidence(
        matrix=H_coarse_bcoo,
        node_weights=node_weights_coarse,
        hyperedge_weights=hg.incidence.hyperedge_weights
    )

    coarse_hg = PhysicsHypergraph(
        incidence=coarse_incidence,
        node_refs=coarse_node_refs,
        hyperedge_names=hg.hyperedge_names, # Edges are preserved
        edge_voltages=hg.edge_voltages,
        edge_currents=hg.edge_currents,
        edge_widths=hg.edge_widths
    )

    return coarse_hg, P
