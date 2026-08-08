"""Tests for core.netlist coverage (compute_eigenvector_centrality, etc.)."""

import numpy as np
import pytest

from temper_placer.core.netlist import compute_eigenvector_centrality


class TestEigenvectorCentrality:
    """Tests for compute_eigenvector_centrality."""

    def test_empty(self):
        adj = np.zeros((0, 0))
        result = compute_eigenvector_centrality(adj)
        assert result.shape == (0,)

    def test_single_node(self):
        adj = np.array([[1.0]], dtype=np.float32)
        result = compute_eigenvector_centrality(adj)
        assert result.shape == (1,)
        assert result[0] == 1.0

    def test_two_nodes_equal(self):
        """Two connected nodes should have equal centrality."""
        adj = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
        result = compute_eigenvector_centrality(adj)
        assert result.shape == (2,)
        assert np.allclose(result[0], result[1])

    def test_two_nodes_asymmetric(self):
        """Node with higher-degree connections gets higher centrality."""
        # Node 0 connected to 2 (self by weight), node 1 barely connected
        adj = np.array([[2.0, 1.0], [1.0, 0.1]], dtype=np.float32)
        result = compute_eigenvector_centrality(adj)
        # Node 0 should have higher centrality
        assert result[0] > result[1]

    def test_three_nodes(self):
        """3-node line graph: middle node has highest centrality."""
        adj = np.array([
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
        ], dtype=np.float32)
        result = compute_eigenvector_centrality(adj)
        # Middle node (index 1) should have highest centrality
        assert result[1] > result[0]
        assert result[1] > result[2]

    def test_normalized_sum_one(self):
        """Centrality scores should sum to 1.0."""
        adj = np.eye(5, dtype=np.float32)
        result = compute_eigenvector_centrality(adj)
        assert np.allclose(np.sum(result), 1.0)
