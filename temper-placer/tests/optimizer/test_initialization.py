"""
Unit tests for spectral initialization (temper-1my.7).

Tests cover:
- Adjacency matrix construction from netlist (temper-1my.7.1)
- Laplacian computation and eigendecomposition (temper-1my.7.2)
- Spectral coordinate scaling to board bounds (temper-1my.7.3)
- SpectralInitializer integration (temper-1my.7.4)
"""

import pytest
import jax.numpy as jnp
import numpy as np

from temper_placer.optimizer.initialization import (
    build_adjacency_matrix,
    compute_spectral_coordinates,
    scale_to_board,
    SpectralInitializer,
)
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.board import Board


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_netlist():
    """Create a simple netlist for testing connectivity.

    Topology:
        R1 --- [NET1] --- R2
        R2 --- [NET2] --- R3

    So R1-R2 share 1 net, R2-R3 share 1 net, R1-R3 share 0 nets.
    """
    components = [
        Component(
            ref="R1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="NET1")],
        ),
        Component(
            ref="R2",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[
                Pin("1", "1", (0, 0), net="NET1"),
                Pin("2", "2", (0, 0), net="NET2"),
            ],
        ),
        Component(
            ref="R3",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="NET2")],
        ),
    ]

    nets = [
        Net(name="NET1", pins=[("R1", "1"), ("R2", "1")]),
        Net(name="NET2", pins=[("R2", "2"), ("R3", "1")]),
    ]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def star_netlist():
    """Create a star topology netlist.

    Topology:
        R1 -\
        R2 ---[GND]--- R4 (center)
        R3 -/

    All edges connect to R4 (hub).
    """
    components = [
        Component(
            ref="R1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="GND")],
        ),
        Component(
            ref="R2",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="GND")],
        ),
        Component(
            ref="R3",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="GND")],
        ),
        Component(
            ref="R4",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="GND")],
        ),
    ]

    nets = [
        Net(name="GND", pins=[("R1", "1"), ("R2", "1"), ("R3", "1"), ("R4", "1")]),
    ]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def disconnected_netlist():
    """Create a netlist with disconnected components.

    Topology:
        R1 --- [NET1] --- R2
        R3 --- [NET2] --- R4  (separate island)
    """
    components = [
        Component(
            ref="R1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="NET1")],
        ),
        Component(
            ref="R2",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="NET1")],
        ),
        Component(
            ref="R3",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="NET2")],
        ),
        Component(
            ref="R4",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="NET2")],
        ),
    ]

    nets = [
        Net(name="NET1", pins=[("R1", "1"), ("R2", "1")]),
        Net(name="NET2", pins=[("R3", "1"), ("R4", "1")]),
    ]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def board():
    """Standard test board."""
    return Board(width=100.0, height=150.0, origin=(0.0, 0.0))


# =============================================================================
# Adjacency Matrix Tests (temper-1my.7.1)
# =============================================================================


class TestBuildAdjacencyMatrix:
    """Tests for build_adjacency_matrix function."""

    def test_empty_netlist(self):
        """Empty netlist should return empty matrix."""
        netlist = Netlist(components=[], nets=[])
        adj = build_adjacency_matrix(netlist)

        assert adj.shape == (0, 0)

    def test_single_component(self):
        """Single component should return 1x1 zero matrix."""
        netlist = Netlist(
            components=[Component("R1", "0805", (2.0, 1.25))],
            nets=[],
        )
        adj = build_adjacency_matrix(netlist)

        assert adj.shape == (1, 1)
        assert adj[0, 0] == 0

    def test_simple_chain(self, simple_netlist):
        """Test simple chain: R1--R2--R3."""
        adj = build_adjacency_matrix(simple_netlist)

        # Should be 3x3
        assert adj.shape == (3, 3)

        # R1-R2 share NET1 → adj[0,1] = adj[1,0] = 1
        assert adj[0, 1] == 1
        assert adj[1, 0] == 1

        # R2-R3 share NET2 → adj[1,2] = adj[2,1] = 1
        assert adj[1, 2] == 1
        assert adj[2, 1] == 1

        # R1-R3 share no nets → adj[0,2] = adj[2,0] = 0
        assert adj[0, 2] == 0
        assert adj[2, 0] == 0

        # Diagonal should be zero (no self-loops)
        assert adj[0, 0] == 0
        assert adj[1, 1] == 0
        assert adj[2, 2] == 0

    def test_star_topology(self, star_netlist):
        """Test star topology with high-fanout net."""
        adj = build_adjacency_matrix(star_netlist)

        assert adj.shape == (4, 4)

        # All components share GND net, so each pair has weight 1
        # This creates a complete graph K4
        for i in range(4):
            for j in range(4):
                if i == j:
                    assert adj[i, j] == 0  # No self-loops
                else:
                    assert adj[i, j] == 1  # All connected via GND

    def test_multiple_nets_between_components(self):
        """Test components connected by multiple nets."""
        components = [
            Component(
                ref="U1",
                footprint="QFN",
                bounds=(5.0, 5.0),
                pins=[
                    Pin("VCC", "1", (0, 0), net="VCC"),
                    Pin("GND", "2", (0, 0), net="GND"),
                ],
            ),
            Component(
                ref="C1",
                footprint="0805",
                bounds=(2.0, 1.25),
                pins=[
                    Pin("+", "1", (0, 0), net="VCC"),
                    Pin("-", "2", (0, 0), net="GND"),
                ],
            ),
        ]

        nets = [
            Net(name="VCC", pins=[("U1", "VCC"), ("C1", "+")]),
            Net(name="GND", pins=[("U1", "GND"), ("C1", "-")]),
        ]

        netlist = Netlist(components=components, nets=nets)
        adj = build_adjacency_matrix(netlist)

        # U1 and C1 share 2 nets (VCC and GND)
        assert adj[0, 1] == 2
        assert adj[1, 0] == 2

    def test_symmetry(self, simple_netlist):
        """Adjacency matrix must be symmetric."""
        adj = build_adjacency_matrix(simple_netlist)

        assert jnp.allclose(adj, adj.T)

    def test_disconnected_components(self, disconnected_netlist):
        """Disconnected components should have block-diagonal structure."""
        adj = build_adjacency_matrix(disconnected_netlist)

        # R1-R2 connected (block 1)
        assert adj[0, 1] == 1
        assert adj[1, 0] == 1

        # R3-R4 connected (block 2)
        assert adj[2, 3] == 1
        assert adj[3, 2] == 1

        # No connections between blocks
        assert adj[0, 2] == 0
        assert adj[0, 3] == 0
        assert adj[1, 2] == 0
        assert adj[1, 3] == 0


# =============================================================================
# Laplacian and Spectral Coordinates Tests (temper-1my.7.2)
# =============================================================================


class TestComputeSpectralCoordinates:
    """Tests for Laplacian computation and eigendecomposition."""

    def test_empty_adjacency(self):
        """Empty adjacency should return empty coordinates."""
        adj = jnp.array([])
        coords = compute_spectral_coordinates(adj.reshape(0, 0), n_dims=2)

        assert coords.shape == (0, 2)

    def test_single_node(self):
        """Single isolated node."""
        adj = jnp.array([[0.0]])
        coords = compute_spectral_coordinates(adj, n_dims=2)

        # Single node can't have 2D coordinates (need at least 3 eigenvalues)
        # Should return zeros or handle gracefully
        assert coords.shape == (1, 2)

    def test_path_graph(self):
        """Path graph R1--R2--R3 should give roughly linear layout."""
        # Adjacency for path graph
        adj = jnp.array([
            [0.0, 1.0, 0.0],  # R1 connected to R2
            [1.0, 0.0, 1.0],  # R2 connected to R1, R3
            [0.0, 1.0, 0.0],  # R3 connected to R2
        ])

        coords = compute_spectral_coordinates(adj, n_dims=2, normalized=True)

        assert coords.shape == (3, 2)

        # Fiedler vector for path graph should place nodes linearly
        # R2 (middle) should be between R1 and R3 in first eigenvector
        fiedler = coords[:, 0]  # First dimension

        # Check ordering: either R1 < R2 < R3 or R3 < R2 < R1
        is_ascending = fiedler[0] < fiedler[1] < fiedler[2]
        is_descending = fiedler[2] < fiedler[1] < fiedler[0]

        assert is_ascending or is_descending

    def test_star_graph(self):
        """Star graph with center hub."""
        # Complete graph K4 (all nodes connected)
        adj = jnp.array([
            [0.0, 1.0, 1.0, 1.0],
            [1.0, 0.0, 1.0, 1.0],
            [1.0, 1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0, 0.0],
        ])

        coords = compute_spectral_coordinates(adj, n_dims=2, normalized=True)

        assert coords.shape == (4, 2)
        # For complete graph, spectral embedding tends to spread nodes evenly
        # Just verify shape and no NaN/Inf
        assert not jnp.isnan(coords).any()
        assert not jnp.isinf(coords).any()

    def test_disconnected_graph(self):
        """Disconnected graph should handle multiple zero eigenvalues."""
        # Two separate edges: R1--R2 and R3--R4
        adj = jnp.array([
            [0.0, 1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0, 0.0],
        ])

        coords = compute_spectral_coordinates(adj, n_dims=2, normalized=True)

        assert coords.shape == (4, 2)
        # Should not crash on multiple zero eigenvalues
        assert not jnp.isnan(coords).any()
        assert not jnp.isinf(coords).any()

    def test_normalized_vs_unnormalized(self):
        """Test both Laplacian types."""
        adj = jnp.array([
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
        ])

        coords_norm = compute_spectral_coordinates(adj, normalized=True)
        coords_unnorm = compute_spectral_coordinates(adj, normalized=False)

        assert coords_norm.shape == (3, 2)
        assert coords_unnorm.shape == (3, 2)

        # Both should give valid coordinates (may differ numerically)
        assert not jnp.isnan(coords_norm).any()
        assert not jnp.isnan(coords_unnorm).any()


# =============================================================================
# Coordinate Scaling Tests (temper-1my.7.3)
# =============================================================================


class TestScaleToBoard:
    """Tests for scaling spectral coordinates to board bounds."""

    def test_unit_square_to_board(self, board):
        """Test scaling unit square to board."""
        # Coordinates in [0, 1] x [0, 1]
        spectral_coords = jnp.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
        ])

        positions = scale_to_board(spectral_coords, board, margin_fraction=0.0)

        # With no margin, should map to full board
        assert positions[0, 0] == pytest.approx(board.origin[0], abs=0.1)
        assert positions[0, 1] == pytest.approx(board.origin[1], abs=0.1)
        assert positions[3, 0] == pytest.approx(board.origin[0] + board.width, abs=0.1)
        assert positions[3, 1] == pytest.approx(board.origin[1] + board.height, abs=0.1)

    def test_with_margin(self, board):
        """Test margin is respected."""
        spectral_coords = jnp.array([
            [0.0, 0.0],
            [1.0, 1.0],
        ])

        margin = 0.1
        positions = scale_to_board(spectral_coords, board, margin_fraction=margin)

        # Min position should be at margin
        expected_min_x = board.origin[0] + board.width * margin
        expected_min_y = board.origin[1] + board.height * margin

        assert positions[0, 0] == pytest.approx(expected_min_x, abs=0.1)
        assert positions[0, 1] == pytest.approx(expected_min_y, abs=0.1)

        # Max position should be at (1 - margin)
        expected_max_x = board.origin[0] + board.width * (1 - margin)
        expected_max_y = board.origin[1] + board.height * (1 - margin)

        assert positions[1, 0] == pytest.approx(expected_max_x, abs=0.1)
        assert positions[1, 1] == pytest.approx(expected_max_y, abs=0.1)

    def test_all_same_coords(self, board):
        """Degenerate case: all coordinates the same."""
        spectral_coords = jnp.array([
            [0.5, 0.5],
            [0.5, 0.5],
            [0.5, 0.5],
        ])

        positions = scale_to_board(spectral_coords, board, margin_fraction=0.1)

        # Should place all at center of board
        center_x = board.origin[0] + board.width / 2
        center_y = board.origin[1] + board.height / 2

        for i in range(3):
            assert positions[i, 0] == pytest.approx(center_x, abs=0.5)
            assert positions[i, 1] == pytest.approx(center_y, abs=0.5)

    def test_negative_coords(self, board):
        """Test handling of negative spectral coordinates."""
        spectral_coords = jnp.array([
            [-1.0, -1.0],
            [1.0, 1.0],
        ])

        positions = scale_to_board(spectral_coords, board, margin_fraction=0.0)

        # Should normalize to [0, 1] first, then scale
        assert jnp.all(positions[:, 0] >= board.origin[0])
        assert jnp.all(positions[:, 0] <= board.origin[0] + board.width)
        assert jnp.all(positions[:, 1] >= board.origin[1])
        assert jnp.all(positions[:, 1] <= board.origin[1] + board.height)

    def test_output_within_bounds(self, board):
        """All positions must be within board bounds."""
        # Random spectral coords
        rng = np.random.RandomState(42)
        spectral_coords = jnp.array(rng.randn(10, 2))

        positions = scale_to_board(spectral_coords, board, margin_fraction=0.1)

        margin_x = board.width * 0.1
        margin_y = board.height * 0.1

        assert jnp.all(positions[:, 0] >= board.origin[0] + margin_x)
        assert jnp.all(positions[:, 0] <= board.origin[0] + board.width - margin_x)
        assert jnp.all(positions[:, 1] >= board.origin[1] + margin_y)
        assert jnp.all(positions[:, 1] <= board.origin[1] + board.height - margin_y)


# =============================================================================
# SpectralInitializer Integration Tests (temper-1my.7.4)
# =============================================================================


class TestSpectralInitializer:
    """Tests for SpectralInitializer class."""

    def test_initialization(self):
        """Test SpectralInitializer construction."""
        initializer = SpectralInitializer(
            normalized_laplacian=True,
            margin_fraction=0.1,
        )

        assert initializer.normalized_laplacian is True
        assert initializer.margin_fraction == 0.1

    def test_simple_netlist(self, simple_netlist, board):
        """Test initialization on simple netlist."""
        initializer = SpectralInitializer()

        positions = initializer.initialize(simple_netlist, board)

        # Should return (N, 2) array
        assert positions.shape == (3, 2)

        # All positions within board bounds
        assert jnp.all(positions[:, 0] >= board.origin[0])
        assert jnp.all(positions[:, 0] <= board.origin[0] + board.width)
        assert jnp.all(positions[:, 1] >= board.origin[1])
        assert jnp.all(positions[:, 1] <= board.origin[1] + board.height)

    def test_star_netlist(self, star_netlist, board):
        """Test initialization on star topology."""
        initializer = SpectralInitializer()

        positions = initializer.initialize(star_netlist, board)

        assert positions.shape == (4, 2)
        assert not jnp.isnan(positions).any()
        assert not jnp.isinf(positions).any()

    def test_disconnected_netlist(self, disconnected_netlist, board):
        """Test initialization handles disconnected components."""
        initializer = SpectralInitializer()

        positions = initializer.initialize(disconnected_netlist, board)

        assert positions.shape == (4, 2)
        # Should not crash on disconnected graph
        assert not jnp.isnan(positions).any()

    def test_deterministic(self, simple_netlist, board):
        """Spectral initialization should be deterministic."""
        initializer = SpectralInitializer()

        positions1 = initializer.initialize(simple_netlist, board)
        positions2 = initializer.initialize(simple_netlist, board)

        # Should produce exactly the same result
        assert jnp.allclose(positions1, positions2)

    def test_empty_netlist(self, board):
        """Handle empty netlist gracefully."""
        netlist = Netlist(components=[], nets=[])
        initializer = SpectralInitializer()

        positions = initializer.initialize(netlist, board)

        assert positions.shape == (0, 2)

    def test_single_component(self, board):
        """Single component should be placed at center."""
        netlist = Netlist(
            components=[Component("R1", "0805", (2.0, 1.25))],
            nets=[],
        )
        initializer = SpectralInitializer()

        positions = initializer.initialize(netlist, board)

        assert positions.shape == (1, 2)
        # Should be near center of board
        center_x = board.origin[0] + board.width / 2
        center_y = board.origin[1] + board.height / 2
        assert positions[0, 0] == pytest.approx(center_x, abs=5.0)
        assert positions[0, 1] == pytest.approx(center_y, abs=5.0)

    def test_respects_margin(self, simple_netlist, board):
        """Test margin is respected."""
        margin = 0.15
        initializer = SpectralInitializer(margin_fraction=margin)

        positions = initializer.initialize(simple_netlist, board)

        # All positions should be within margin
        margin_x = board.width * margin
        margin_y = board.height * margin

        assert jnp.all(positions[:, 0] >= board.origin[0] + margin_x)
        assert jnp.all(positions[:, 0] <= board.origin[0] + board.width - margin_x)
        assert jnp.all(positions[:, 1] >= board.origin[1] + margin_y)
        assert jnp.all(positions[:, 1] <= board.origin[1] + board.height - margin_y)
