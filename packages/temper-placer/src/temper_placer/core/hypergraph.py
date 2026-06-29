"""
Physics-Aware Hypergraph representation for PCB placement.

This module defines the core immutable data structures for the hypergraph.
It uses flax.struct.dataclass for automatic JAX PyTree registration.
"""

from __future__ import annotations

from collections.abc import Sequence

import jax.numpy as jnp
from flax import struct
from jax import Array
from jax.experimental import sparse


@struct.dataclass
class HypergraphIncidence:
    """
    Sparse BCOO representation of the Hypergraph Incidence Matrix H.

    Dimensions: (N_nodes, N_hyperedges)
    - Rows: Components (Nodes)
    - Cols: Nets (Hyperedges)

    Values:
    - 1.0 (or weight) if connected
    - 0.0 otherwise
    """
    matrix: sparse.BCOO
    node_weights: Array      # (N_nodes,) - e.g., component area
    hyperedge_weights: Array # (N_edges,) - e.g., net priority/current


@struct.dataclass
class PhysicsHypergraph:
    """
    Hypergraph with embedded physical attributes.

    This is a registered JAX PyTree. Metadata fields (lists of strings)
    are marked as static (pytree_node=False).
    """
    incidence: HypergraphIncidence

    # Metadata for reconstruction/mapping (Static)
    node_refs: Sequence[str] = struct.field(pytree_node=False)
    hyperedge_names: Sequence[str] = struct.field(pytree_node=False)

    # Physics Attributes (Parallel arrays to hyperedges)
    edge_voltages: Array = struct.field(default_factory=lambda: jnp.array([])) # (N_edges,) 0=LV, 1=HV
    edge_currents: Array = struct.field(default_factory=lambda: jnp.array([])) # (N_edges,) Amps
    edge_widths: Array = struct.field(default_factory=lambda: jnp.array([]))   # (N_edges,) mm

    @property
    def n_nodes(self) -> int:
        return len(self.node_refs)

    @property
    def n_edges(self) -> int:
        return len(self.hyperedge_names)

    def compute_node_degrees(self) -> Array:
        """Compute degree of each node (sum of incident hyperedge weights)."""
        # H @ ones vector of edges
        ones = jnp.ones(self.n_edges)
        return self.incidence.matrix @ ones

    def compute_edge_degrees(self) -> Array:
        """Compute degree of each hyperedge (number of connected nodes)."""
        # H.T @ ones vector of nodes
        ones = jnp.ones(self.n_nodes)
        return self.incidence.matrix.T @ ones
