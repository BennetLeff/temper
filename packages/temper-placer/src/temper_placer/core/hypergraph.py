"""
Physics-Aware Hypergraph representation for PCB placement.

This module defines the core immutable data structures for the hypergraph.
The COO-triplet container lives in ``temper-design-bundle`` as a typed
pyclass (``hypergraph_contracts.Coo``); ``HypergraphIncidence`` and
``PhysicsHypergraph`` remain Python dataclasses over numpy arrays (scipy.sparse
retired -- see the ``Coo`` docstring history below).

Wave 4 (unit ``core_graph_cluster``): the one genuine compute kernel — the
``Coo @ vector`` sparse matrix-vector product — is migrated to
``packages/temper-geometry/src/core_graph_geometry.rs``
(``hypergraph_coo_matvec``, replicating ``np.bincount`` scatter-add
semantics bit-for-bit, including the ``minlength`` length extension and
negative-column fancy-index wrapping). ``__matmul__`` delegates. Bit-exact
parity is pinned by ``tests/core/test_core_graph_cluster_rust_differential.py``
and ``tests/core/test_hypergraph_coo_rust_differential.py``.

Orchestration plan Phase A unit U7
(``docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md``): the
``Coo`` container — the kernel's typed I/O boundary — moves to
``temper-design-bundle`` (``packages/temper-design-bundle/src/hypergraph_contracts.rs``).
Storage is typed Rust ``Vec`` fields; the numpy-visible surface (``row``/
``col``/``data`` and the ``@`` result) is preserved exactly by materializing
numpy arrays through numpy itself, and ``__matmul__`` still runs the
pre-migration kernel code path. The pinned hypergraph-factory differential
keeps the KTD9 numpy/set assembly as evidence and constructs ``Coo`` there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

import numpy as np
import temper_design_bundle_python as _tdb
from numpy.typing import NDArray

Array: TypeAlias = NDArray  # type alias for sparse operations

Coo: TypeAlias = _tdb.hypergraph_contracts.Coo


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

    matrix: Coo
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
