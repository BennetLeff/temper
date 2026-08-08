"""Tests for core.hypergraph module."""

import numpy as np
from scipy.sparse import coo_matrix

from temper_placer.core.hypergraph import (
    HypergraphIncidence,
    PhysicsHypergraph,
)


class TestPhysicsHypergraph:
    """Tests for PhysicsHypergraph."""

    def _make_hypergraph(self, n_nodes=3, n_edges=2):
        """Create a simple hypergraph with 3 nodes and 2 edges."""
        # Incidence: edge0 connects nodes 0,1; edge1 connects nodes 1,2
        rows = np.array([0, 1, 1, 2], dtype=np.int32)
        cols = np.array([0, 0, 1, 1], dtype=np.int32)
        data = np.ones(4, dtype=np.float64)
        matrix = coo_matrix((data, (rows, cols)), shape=(n_nodes, n_edges))
        node_weights = np.ones(n_nodes)
        edge_weights = np.ones(n_edges)
        incidence = HypergraphIncidence(
            matrix=matrix,
            node_weights=node_weights,
            hyperedge_weights=edge_weights,
        )
        return PhysicsHypergraph(
            incidence=incidence,
            node_refs=["N0", "N1", "N2"],
            hyperedge_names=["E0", "E1"],
        )

    def test_n_nodes(self):
        hg = self._make_hypergraph(3, 2)
        assert hg.n_nodes == 3

    def test_n_nodes_empty(self):
        """Empty hypergraph has zero nodes."""
        rows = np.array([], dtype=np.int32)
        cols = np.array([], dtype=np.int32)
        data = np.array([], dtype=np.float64)
        matrix = coo_matrix((data, (rows, cols)), shape=(0, 0))
        incidence = HypergraphIncidence(
            matrix=matrix, node_weights=np.array([]), hyperedge_weights=np.array([]),
        )
        hg = PhysicsHypergraph(
            incidence=incidence,
            node_refs=[],
            hyperedge_names=[],
        )
        assert hg.n_nodes == 0
        assert hg.n_edges == 0

    def test_compute_edge_degrees(self):
        hg = self._make_hypergraph(3, 2)
        degrees = hg.compute_edge_degrees()
        # Edge 0 connects nodes 0,1 -> degree 2
        # Edge 1 connects nodes 1,2 -> degree 2
        assert degrees.shape == (2,)
        assert degrees[0] == 2.0
        assert degrees[1] == 2.0

    def test_compute_edge_degrees_nonuniform(self):
        """Edge with different number of incident nodes."""
        rows = np.array([0, 1, 2, 0], dtype=np.int32)
        cols = np.array([0, 0, 0, 1], dtype=np.int32)
        data = np.ones(4, dtype=np.float64)
        matrix = coo_matrix((data, (rows, cols)), shape=(3, 2))
        incidence = HypergraphIncidence(
            matrix=matrix, node_weights=np.ones(3), hyperedge_weights=np.ones(2),
        )
        hg = PhysicsHypergraph(
            incidence=incidence,
            node_refs=["N0", "N1", "N2"],
            hyperedge_names=["E0", "E1"],
        )
        degrees = hg.compute_edge_degrees()
        assert degrees[0] == 3.0  # edge0 connects 3 nodes
        assert degrees[1] == 1.0  # edge1 connects 1 node

    def test_compute_node_degrees(self):
        hg = self._make_hypergraph(3, 2)
        deg = hg.compute_node_degrees()
        # Node 0: connected via edge0 -> deg 1
        # Node 1: connected via edge0 AND edge1 -> deg 2
        # Node 2: connected via edge1 -> deg 1
        assert deg.shape == (3,)
        assert deg[0] == 1.0
        assert deg[1] == 2.0
        assert deg[2] == 1.0


class TestHypergraphIncidence:
    """Tests for HypergraphIncidence."""

    def test_create(self):
        rows = np.array([0, 1], dtype=np.int32)
        cols = np.array([0, 0], dtype=np.int32)
        data = np.ones(2, dtype=np.float64)
        matrix = coo_matrix((data, (rows, cols)), shape=(2, 1))
        inc = HypergraphIncidence(
            matrix=matrix, node_weights=np.ones(2), hyperedge_weights=np.ones(1),
        )
        assert inc.node_weights.shape == (2,)
        assert inc.hyperedge_weights.shape == (1,)
        assert inc.matrix.shape == (2, 1)
