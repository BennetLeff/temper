"""
Physics-Aware Hypergraph representation for PCB placement.

This module defines the core immutable data structures for the hypergraph.
Uses Python dataclasses and scipy sparse matrices (JAX removed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import coo_matrix

Array: TypeAlias = NDArray  # type alias for sparse operations


@dataclass
class HypergraphIncidence:
    """
    Sparse COO representation of the Hypergraph Incidence Matrix H.

    Dimensions: (N_nodes, N_hyperedges)
    - Rows: Components (Nodes)
    - Cols: Nets (Hyperedges)

    Values:
    - 1.0 (or weight) if connected
    - 0.0 otherwise
    """

    matrix: coo_matrix
    node_weights: Array  # (N_nodes,) - e.g., component area
    hyperedge_weights: Array  # (N_edges,) - e.g., net priority/current


@dataclass
class PhysicsHypergraph:
    """
    Hypergraph with embedded physical attributes.
    """

    incidence: HypergraphIncidence

    # Metadata for reconstruction/mapping
    node_refs: list[str] = field(default_factory=list)
    hyperedge_names: list[str] = field(default_factory=list)

    # Physics Attributes (Parallel arrays to hyperedges)
    edge_voltages: Array = field(default_factory=lambda: np.array([]))  # (N_edges,) 0=LV, 1=HV
    edge_currents: Array = field(default_factory=lambda: np.array([]))  # (N_edges,) Amps
    edge_widths: Array = field(default_factory=lambda: np.array([]))  # (N_edges,) mm

    @property
    def n_nodes(self) -> int:
        return len(self.node_refs)

    @property
    def n_edges(self) -> int:
        return len(self.hyperedge_names)

    def compute_node_degrees(self) -> Array:
        """Compute degree of each node (sum of incident hyperedge weights)."""
        # H @ ones vector of edges
        ones = np.ones(self.n_edges)
        return self.incidence.matrix @ ones

    def compute_edge_degrees(self) -> Array:
        """Compute degree of each hyperedge (number of connected nodes)."""
        # H.T @ ones vector of nodes
        ones = np.ones(self.n_nodes)
        return self.incidence.matrix.T @ ones
