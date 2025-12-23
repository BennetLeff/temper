import jax.numpy as jnp
import pytest
from temper_placer.optimizer.initialization import compute_spectral_coordinates, SpectralInitializer
from temper_placer.core.netlist import Netlist, Component, Net

def test_laplacian_eigenvalues_non_negative():
    """Verify that Laplacian eigenvalues are non-negative."""
    # Adjacency for a simple path graph 0-1-2
    adj = jnp.array([
        [0, 1, 0],
        [1, 0, 1],
        [0, 1, 0]
    ], dtype=jnp.float32)
    
    n = adj.shape[0]
    degrees = jnp.sum(adj, axis=1)
    D = jnp.diag(degrees)
    L = D - adj
    
    eigenvalues, _ = jnp.linalg.eigh(L)
    # Small epsilon for numerical stability
    assert jnp.all(eigenvalues > -1e-6)
    # First eigenvalue should be 0 (constant eigenvector)
    assert float(eigenvalues[0]) == pytest.approx(0.0, abs=1e-6)

def test_path_graph_spectral_linearity():
    """Path graph: positions are linear."""
    # 0-1-2-3-4
    adj = jnp.zeros((5, 5))
    for i in range(4):
        adj = adj.at[i, i+1].set(1.0)
        adj = adj.at[i+1, i].set(1.0)
        
    coords = compute_spectral_coordinates(adj, n_dims=1, normalized=False)
    # For a path graph, the Fiedler vector (second eigenvector) should be monotonic
    # (either increasing or decreasing)
    diffs = jnp.diff(coords[:, 0])
    assert jnp.all(diffs > 0) or jnp.all(diffs < 0)

def test_cycle_graph_spectral_circularity():
    """Cycle graph: positions form circle."""
    # 0-1-2-3-0
    adj = jnp.array([
        [0, 1, 0, 1],
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [1, 0, 1, 0]
    ], dtype=jnp.float32)
    
    coords = compute_spectral_coordinates(adj, n_dims=2, normalized=False)
    # For a 4-cycle, the 2nd and 3rd eigenvectors should form a diamond or square
    # distance from origin should be constant-ish
    dists = jnp.sqrt(jnp.sum(coords**2, axis=1))
    assert jnp.allclose(dists, dists[0], atol=1e-6)

def test_spectral_init_within_bounds(simple_netlist, simple_board):
    """Initial positions are within board bounds."""
    initializer = SpectralInitializer(margin_fraction=0.1)
    positions = initializer.initialize(simple_netlist, simple_board)
    
    x_min, y_min = simple_board.origin
    x_max = x_min + simple_board.width
    y_max = y_min + simple_board.height
    
    assert jnp.all(positions[:, 0] >= x_min)
    assert jnp.all(positions[:, 0] <= x_max)
    assert jnp.all(positions[:, 1] >= y_min)
    assert jnp.all(positions[:, 1] <= y_max)

def test_spectral_init_disconnected_graph():
    """Test spectral initialization with disconnected netlists."""
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Net, Netlist
    
    # Two disconnected pairs: (C0-C1) and (C2-C3)
    components = [Component(ref=f"C{i}", footprint="0805", bounds=(2, 2)) for i in range(4)]
    nets = [
        Net(name="N1", pins=[("C0", "1"), ("C1", "1")]),
        Net(name="N2", pins=[("C2", "1"), ("C3", "1")]),
    ]
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100, height=100)
    
    initializer = SpectralInitializer()
    positions = initializer.initialize(netlist, board)
    
    # Disconnected components should be placed in different regions (handled by packing)
    dist_intra1 = jnp.linalg.norm(positions[0] - positions[1])
    dist_intra2 = jnp.linalg.norm(positions[2] - positions[3])
    
    # Just check that all positions are valid and within bounds
    assert jnp.all(jnp.isfinite(positions))
    
    # The components within a subgraph should be at different positions
    assert dist_intra1 > 0.1
    assert dist_intra2 > 0.1

def test_spectral_init_isolated_nodes():
    """Test components with no connections (degree=0)."""
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Net, Netlist
    
    # 2 connected components + 1 isolated
    components = [Component(ref=f"C{i}", footprint="0805", bounds=(2, 2)) for i in range(3)]
    nets = [Net(name="N1", pins=[("C0", "1"), ("C1", "1")])]
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100, height=100)
    
    initializer = SpectralInitializer()
    positions = initializer.initialize(netlist, board)
    
    # Check all positions are finite and not NaN
    assert jnp.all(jnp.isfinite(positions))
    # Isolated node (C2) should have a valid position
    assert jnp.all(jnp.isfinite(positions[2]))
