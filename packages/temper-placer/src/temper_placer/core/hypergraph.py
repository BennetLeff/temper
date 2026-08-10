"""
Physics-Aware Hypergraph representation for PCB placement.

This module defines the core immutable data structures for the hypergraph.
Uses Python dataclasses and a plain-array COO triplet container (JAX removed;
scipy.sparse retired -- see ``Coo``'s docstring).

Wave 4 (unit ``core_graph_cluster``): the one genuine compute kernel — the
``Coo @ vector`` sparse matrix-vector product — is migrated to
``packages/temper-geometry/src/core_graph_geometry.rs``
(``hypergraph_coo_matvec``, replicating ``np.bincount`` scatter-add
semantics bit-for-bit, including the ``minlength`` length extension and
negative-column fancy-index wrapping). The container stays a Python
dataclass; ``__matmul__`` delegates. Bit-exact parity is pinned by
``tests/core/test_core_graph_cluster_rust_differential.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

import numpy as np
import temper_geometry as _tg
from numpy.typing import NDArray

Array: TypeAlias = NDArray  # type alias for sparse operations


@dataclass(frozen=True)
class Coo:
    """Minimal COO-triplet container, replacing ``scipy.sparse.coo_matrix``.

    ``extraction/hypergraph_factory.py`` builds this from triplets that are
    already deduplicated per net (a Python ``set()`` over connected-component
    indices, before construction -- see that module's docstring), so there is
    no duplicate-entry summation semantics to reproduce: this is triplet
    storage plus an order-invariant matrix-vector product, not an algorithm.
    ``docs/evidence/2026-08-07-scipy-keeps-re-triage.md`` Sec 3 re-triaged
    this call site and found the prior "sparse construction semantics are not
    reimplementable" premise did not hold once checked against the actual
    code and its sole consumer (``PhysicsHypergraph.compute_node_degrees``/
    ``compute_edge_degrees``, an order-invariant ``H @ ones`` / ``H.T @
    ones``).

    Duck-types the handful of ``scipy.sparse.coo_matrix`` attributes this
    codebase's call sites and tests actually use (``shape``, ``nnz``,
    ``row``, ``col``, ``data``, ``.T``, ``@``) -- this is not a general
    sparse-matrix replacement, only enough surface for those consumers.
    """

    row: Array  # (nnz,) int -- row index per stored triplet
    col: Array  # (nnz,) int -- column index per stored triplet
    data: Array  # (nnz,) -- value per stored triplet
    shape: tuple[int, int]

    @property
    def nnz(self) -> int:
        return int(self.data.shape[0])

    @property
    def T(self) -> Coo:  # noqa: N802 - matches scipy's `.T` attribute name
        return Coo(row=self.col, col=self.row, data=self.data, shape=(self.shape[1], self.shape[0]))

    def __matmul__(self, other: Array) -> Array:
        """Sparse matrix-vector product ``self @ other``.

        For each stored triplet ``(r, c, d)``, scatter-adds ``d *
        other[c]`` into ``result[r]``. The result does not depend on
        triplet order -- summing by group regardless of the order its inputs
        arrive in -- matching the order-invariance ``scipy.sparse.coo_matrix``'s
        matvec already provided (this class's justification for dropping it).

        The scatter-add itself (the ``np.bincount`` semantics: contributions
        ``data * other[col]`` computed in triplet order, summed in triplet
        order, output length ``max(shape[0], max(row)+1)``, negative ``col``
        wrapping like numpy fancy indexing) runs in Rust via
        ``temper_geometry.hypergraph_coo_matvec``, bit-identical to the
        pre-migration numpy expression.

        Wave-4 marshalling migration: numpy arrays are passed directly to
        the Rust kernel (``hypergraph_coo_matvec_py`` now accepts
        ``numpy.ndarray`` args and returns a ``numpy.ndarray``), eliminating
        the ``.tolist()`` / ``[float(d) for d in ...]`` / ``np.array()``
        marshalling that used to convert between Python lists and numpy
        arrays at the FFI boundary.
        """
        n_rows = self.shape[0]
        if self.nnz == 0:
            return np.zeros(n_rows, dtype=np.float64)
        return np.array(_tg.hypergraph_coo_matvec_py(
            self.row,
            self.col,
            self.data.astype(np.float64),
            n_rows,
            other,
        ))


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
