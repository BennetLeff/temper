"""
Component, Pin, Net, and Netlist data structures.

This module defines the netlist representation used throughout temper-placer.
Components represent physical parts, Pins are connection points, Nets define
electrical connectivity, and Netlist aggregates everything.

Delegation shim (Wave 4 Phase 3): the data model lives in Rust
(``temper_design_bundle_python``, see packages/temper-design-bundle/src/
netlist_contracts.rs). This module keeps the numpy surface as module-level
wrappers (``get_bounds_array``/``get_fixed_mask``/``build_adjacency_matrix``
— R10/KTD6, with consumers adapted per R12), the never-gated
``compute_eigenvector_centrality`` kernel (R10), and the hashlib-based
``find_isomorphic_groups`` helper (KTD7).
"""

from __future__ import annotations

from typing import TypeAlias

import numpy as np
from temper_design_bundle_python import (  # noqa: F401 — re-exports: the shim's public API
    Net,
    Netlist,
    NetlistComponent,
    Pin,
)

# The extension's flat namespace holds both board's and netlist's
# Component; the netlist one is exposed as NetlistComponent and re-exported
# here under the module's public name.
Component = NetlistComponent

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement


def get_bounds_array(netlist: Netlist) -> Array:
    """Get (N, 2) array of component bounds (width, height) (R10)."""
    return np.array([c.bounds for c in netlist.components], dtype=np.float32)


def get_fixed_mask(netlist: Netlist) -> Array:
    """Get (N,) boolean array of fixed components (R10)."""
    return np.array([c.fixed for c in netlist.components], dtype=np.bool_)


def build_adjacency_matrix(netlist: Netlist) -> Array:
    """
    Build weighted adjacency matrix from netlist connectivity.

    The adjacency matrix A is symmetric with A[i,j] equal to the number of nets
    connecting components i and j. Components on the same net create edges between
    all pairs of components on that net (complete subgraph).

    Args:
        netlist: Netlist with components and nets.

    Returns:
        (N, N) symmetric adjacency matrix where A[i,j] = number of nets
        connecting components i and j. Returns (0,0) array for empty netlist.
    """
    n = len(netlist.components)

    if n == 0:
        return np.array([]).reshape(0, 0)

    # Build component ref -> index mapping
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    # Initialize adjacency matrix
    adj = np.zeros((n, n), dtype=np.float32)

    # For each net, connect all component pairs
    for net in netlist.nets:
        # Get component indices for this net
        comp_indices = []
        for comp_ref, _ in net.pins:
            if comp_ref in ref_to_idx:
                comp_indices.append(ref_to_idx[comp_ref])

        # Remove duplicates (component may have multiple pins on same net)
        comp_indices = list(set(comp_indices))

        # Add edges between all pairs (complete subgraph)
        for i in range(len(comp_indices)):
            for j in range(i + 1, len(comp_indices)):
                idx_i = comp_indices[i]
                idx_j = comp_indices[j]

                adj[idx_i, idx_j] += 1
                adj[idx_j, idx_i] += 1  # Symmetric

    return np.array(adj)


def compute_eigenvector_centrality(adjacency: Array) -> Array:
    """
    Compute eigenvector centrality for each node in the graph.

    Eigenvector centrality measures a node's importance based on the
    importance of its neighbors. It corresponds to the eigenvector
    associated with the largest eigenvalue of the adjacency matrix.

    Args:
        adjacency: (N, N) weighted adjacency matrix.

    Returns:
        (N,) array of centrality scores, normalized to sum to 1.0.
    """
    n = adjacency.shape[0]
    if n == 0:
        return np.array([])
    if n == 1:
        return np.array([1.0], dtype=np.float32)

    # For symmetric matrices, eigh returns eigenvalues in ascending order
    eigenvalues, eigenvectors = np.linalg.eigh(adjacency)

    # The leading eigenvector is the last one (largest eigenvalue)
    centrality = eigenvectors[:, -1]

    # Eigenvector centrality should be non-negative (Perron-Frobenius theorem)
    centrality = np.abs(centrality)

    # Normalize so they sum to 1.0
    total = np.sum(centrality)
    if total > 0:
        centrality = centrality / total

    return centrality


def find_isomorphic_groups(netlist: Netlist, iterations: int = 2) -> list[list[int]]:
    """
    Find groups of components that are topologically isomorphic.

    Uses Weisfeiler-Lehman (WL) neighborhood hashing to identify components
    with identical local connectivity and footprints.

    Args:
        netlist: Netlist with components and nets.
        iterations: Number of neighborhood expansion steps.
            1: Same footprint and same neighbor footprints.
            2: Also considers neighbors of neighbors.

    Returns:
        List of groups, where each group is a list of component indices.
        Only groups with >1 member are returned.
    """
    import hashlib

    n = len(netlist.components)
    if n == 0:
        return []

    # 1. Initial labels: Footprint + Ref Prefix (to distinguish R from C)
    labels = []
    for c in netlist.components:
        # Extract ref prefix (all letters at start)
        import re

        match = re.match(r"^([a-zA-Z]+)", c.ref)
        prefix = match.group(1) if match else ""
        labels.append(f"{c.footprint}|{prefix}")

    # Build adjacency for hashing
    adj = build_adjacency_matrix(netlist)
    # Convert to list of neighbor indices for each component
    neighbor_lists = []
    for i in range(n):
        # Components connected by any net
        neighbors = np.where(adj[i] > 0)[0].tolist()
        neighbor_lists.append(neighbors)

    # 2. Iterative Refinement (WL algorithm)
    for _ in range(iterations):
        new_labels = []
        for i in range(n):
            # Get labels of neighbors
            neighbor_labels = sorted([labels[j] for j in neighbor_lists[i]])

            # Combine current label with neighbor labels
            sig = f"{labels[i]}|{','.join(neighbor_labels)}"
            # Hash to keep labels manageable
            h = hashlib.md5(sig.encode()).hexdigest()
            new_labels.append(h)
        labels = new_labels

    # 3. Group by final labels
    groups_dict: dict[str, list[int]] = {}
    for i, label in enumerate(labels):
        if label not in groups_dict:
            groups_dict[label] = []
        groups_dict[label].append(i)

    # 4. Filter groups with >1 member
    return [g for g in groups_dict.values() if len(g) > 1]
