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