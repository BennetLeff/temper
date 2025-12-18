"""
Tests for spectral initialization and subgraph partitioning (temper-d5x).
"""

from __future__ import annotations

import jax.numpy as jnp
import pytest
from temper_placer.optimizer.initialization import SpectralInitializer
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Net

def test_spectral_disjoint_subgraphs():
    """Test Case 1: Verify disjoint subgraphs are not placed on top of each other."""
    # Create two isolated islands: (C1-C2) and (C3-C4)
    c1 = Component(ref="C1", footprint="0805", bounds=(5.0, 5.0))
    c2 = Component(ref="C2", footprint="0805", bounds=(5.0, 5.0))
    c3 = Component(ref="C3", footprint="0805", bounds=(5.0, 5.0))
    c4 = Component(ref="C4", footprint="0805", bounds=(5.0, 5.0))
    
    nets = [
        Net("N1", [("C1", "1"), ("C2", "1")]),
        Net("N2", [("C3", "1"), ("C4", "1")]),
    ]
    
    netlist = Netlist(components=[c1, c2, c3, c4], nets=nets)
    board = Board(width=100.0, height=100.0)
    
    initializer = SpectralInitializer(margin_fraction=0.1)
    positions = initializer.initialize(netlist, board)
    
    # Calculate center of mass for each island
    island1_pos = positions[:2]
    island2_pos = positions[2:]
    
    center1 = jnp.mean(island1_pos, axis=0)
    center2 = jnp.mean(island2_pos, axis=0)
    
    dist = jnp.linalg.norm(center1 - center2)
    
    print(f"\nCenter 1: {center1}")
    print(f"Center 2: {center2}")
    print(f"Distance: {dist}")
    
    # Currently, they might both be at the board center (50, 50)
    # because find_connected_components is implemented but 
    # the results are all normalized to [-0.5, 0.5] and then scaled 
    # to board, which might still overlap them if they share the same range.
    assert dist > 10.0
def test_disjoint_three_subgraphs():
    """Test Case 2: Three disjoint subgraphs (power, digital, analog) are well separated."""
    # Power domain: C1-C2
    # Digital domain: C3-C4-C5
    # Analog domain: C6 (isolated)
    components = [
        Component(ref=f"C{i}", footprint="0805", bounds=(10.0, 10.0))
        for i in range(1, 7)
    ]
    
    nets = [
        Net("N1", [("C1", "1"), ("C2", "1")]),
        Net("N2", [("C3", "1"), ("C4", "1")]),
        Net("N3", [("C4", "1"), ("C5", "1")]),
    ]
    
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=200.0, height=200.0)
    
    initializer = SpectralInitializer(margin_fraction=0.1)
    positions = initializer.initialize(netlist, board)
    
    # Calculate centers of mass
    island1 = positions[0:2]  # Power
    island2 = positions[2:5]  # Digital
    island3 = positions[5:6]  # Analog (isolated)
    
    center1 = jnp.mean(island1, axis=0)
    center2 = jnp.mean(island2, axis=0)
    center3 = island3[0]  # Single component
    
    # All islands should be at least 30mm apart (3x component size)
    dist_12 = jnp.linalg.norm(center1 - center2)
    dist_13 = jnp.linalg.norm(center1 - center3)
    dist_23 = jnp.linalg.norm(center2 - center3)
    
    print(f"\nPower-Digital: {dist_12:.2f}mm")
    print(f"Power-Analog: {dist_13:.2f}mm")
    print(f"Digital-Analog: {dist_23:.2f}mm")
    
    assert dist_12 > 30.0, f"Power-Digital too close: {dist_12:.2f}mm"
    assert dist_13 > 30.0, f"Power-Analog too close: {dist_13:.2f}mm"
    assert dist_23 > 30.0, f"Digital-Analog too close: {dist_23:.2f}mm"

def test_single_isolated_component_not_at_center():
    """Test Case 3: Single isolated component shouldn't dominate center position."""
    # Large connected graph + one isolated component
    components = [Component(ref=f"C{i}", footprint="0805", bounds=(5.0, 5.0)) for i in range(1, 6)]
    
    # C1-C2-C3-C4 form a chain, C5 is isolated
    nets = [
        Net("N1", [("C1", "1"), ("C2", "1")]),
        Net("N2", [("C2", "1"), ("C3", "1")]),
        Net("N3", [("C3", "1"), ("C4", "1")]),
    ]
    
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100.0, height=100.0)
    
    initializer = SpectralInitializer(margin_fraction=0.1)
    positions = initializer.initialize(netlist, board)
    
    # Large subgraph (C1-C4) should be near center
    large_subgraph = positions[0:4]
    isolated = positions[4]
    
    large_center = jnp.mean(large_subgraph, axis=0)
    board_center = jnp.array([board.width / 2, board.height / 2])
    
    # Large subgraph center should be within 30mm of board center
    dist_large_to_center = jnp.linalg.norm(large_center - board_center)
    
    # Isolated component should NOT be at board center (should be in corner/periphery)
    dist_isolated_to_center = jnp.linalg.norm(isolated - board_center)
    
    print(f"\nLarge subgraph center: {large_center}")
    print(f"Isolated component: {isolated}")
    print(f"Large subgraph distance to center: {dist_large_to_center:.2f}mm")
    print(f"Isolated distance to center: {dist_isolated_to_center:.2f}mm")
    
    assert dist_large_to_center < 30.0, "Large subgraph should be near center"
    assert dist_isolated_to_center > 20.0, "Isolated component shouldn't be at center"

def test_eigenvalue_computation_disjoint():
    """Test Case 4: Verify eigenvalue computation doesn't crash on disconnected graph."""
    # Two pairs of connected components, no connections between pairs
    components = [Component(ref=f"C{i}", footprint="0805", bounds=(5.0, 5.0)) for i in range(1, 5)]
    
    nets = [
        Net("N1", [("C1", "1"), ("C2", "1")]),
        Net("N2", [("C3", "1"), ("C4", "1")]),
    ]
    
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100.0, height=100.0)
    
    initializer = SpectralInitializer(margin_fraction=0.1)
    
    # Should not crash
    positions = initializer.initialize(netlist, board)
    
    # All components should be on board
    assert jnp.all(positions[:, 0] >= 0), "All x positions should be on board"
    assert jnp.all(positions[:, 0] <= board.width), "All x positions should be on board"
    assert jnp.all(positions[:, 1] >= 0), "All y positions should be on board"
    assert jnp.all(positions[:, 1] <= board.height), "All y positions should be on board"
    
    print(f"\n✓ Eigenvalue computation succeeded for disjoint graph")
    print(f"Positions: {positions}")

# Unit tests for find_connected_components (temper-gcp.6)

def test_find_components_empty():
    """Empty graph returns empty list."""
    from temper_placer.optimizer.initialization import find_connected_components
    import jax.numpy as jnp
    
    adjacency = jnp.zeros((0, 0))
    result = find_connected_components(adjacency)
    assert result == []

def test_find_components_single():
    """Single node returns [[0]]."""
    from temper_placer.optimizer.initialization import find_connected_components
    import jax.numpy as jnp
    
    adjacency = jnp.zeros((1, 1))
    result = find_connected_components(adjacency)
    assert result == [[0]]

def test_find_components_fully_connected():
    """Fully connected graph returns single component."""
    from temper_placer.optimizer.initialization import find_connected_components
    import jax.numpy as jnp
    
    # 4 nodes, all connected
    adjacency = jnp.array([
        [0, 1, 1, 1],
        [1, 0, 1, 1],
        [1, 1, 0, 1],
        [1, 1, 1, 0],
    ])
    result = find_connected_components(adjacency)
    assert len(result) == 1
    assert set(result[0]) == {0, 1, 2, 3}

def test_find_components_two_pairs():
    """Two separate pairs [[0,1], [2,3]]."""
    from temper_placer.optimizer.initialization import find_connected_components
    import jax.numpy as jnp
    
    adjacency = jnp.array([
        [0, 1, 0, 0],
        [1, 0, 0, 0],
        [0, 0, 0, 1],
        [0, 0, 1, 0],
    ])
    result = find_connected_components(adjacency)
    assert len(result) == 2
    # Components should be [0,1] and [2,3]
    assert set(result[0]) == {0, 1}
    assert set(result[1]) == {2, 3}

def test_find_components_chain():
    """Chain 0-1-2-3 returns single component."""
    from temper_placer.optimizer.initialization import find_connected_components
    import jax.numpy as jnp
    
    adjacency = jnp.array([
        [0, 1, 0, 0],
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [0, 0, 1, 0],
    ])
    result = find_connected_components(adjacency)
    assert len(result) == 1
    assert set(result[0]) == {0, 1, 2, 3}

def test_find_components_star():
    """Star topology (center connected to all) returns single component."""
    from temper_placer.optimizer.initialization import find_connected_components
    import jax.numpy as jnp
    
    # Node 0 is center, connected to 1, 2, 3
    adjacency = jnp.array([
        [0, 1, 1, 1],
        [1, 0, 0, 0],
        [1, 0, 0, 0],
        [1, 0, 0, 0],
    ])
    result = find_connected_components(adjacency)
    assert len(result) == 1
    assert set(result[0]) == {0, 1, 2, 3}

def test_find_components_mixed():
    """Mix of connected + isolated components."""
    from temper_placer.optimizer.initialization import find_connected_components
    import jax.numpy as jnp
    
    # 0-1-2 connected, 3 isolated, 4-5 connected
    adjacency = jnp.array([
        [0, 1, 0, 0, 0, 0],
        [1, 0, 1, 0, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 1, 0],
    ])
    result = find_connected_components(adjacency)
    assert len(result) == 3
    
    # Find which component is which by size
    components_by_size = sorted(result, key=len, reverse=True)
    assert set(components_by_size[0]) == {0, 1, 2}  # Size 3
    assert set(components_by_size[1]) == {4, 5}     # Size 2
    assert set(components_by_size[2]) == {3}        # Size 1

def test_find_components_weighted():
    """Weighted edges (all >0 should connect)."""
    from temper_placer.optimizer.initialization import find_connected_components
    import jax.numpy as jnp
    
    # 0-1 with weight 0.5, 2-3 with weight 2.0
    adjacency = jnp.array([
        [0.0, 0.5, 0.0, 0.0],
        [0.5, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 2.0],
        [0.0, 0.0, 2.0, 0.0],
    ])
    result = find_connected_components(adjacency)
    assert len(result) == 2
    assert set(result[0]) == {0, 1}
    assert set(result[1]) == {2, 3}
