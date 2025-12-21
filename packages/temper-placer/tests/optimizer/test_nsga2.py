
import pytest
import jax.numpy as jnp
from temper_placer.optimizer.nsga2 import fast_non_dominated_sort, calculate_crowding_distance

def test_non_dominated_sort_simple():
    """Verify sorting of a simple 2D objective space."""
    # Objectives (minimize both):
    # A: [1, 10]
    # B: [2, 5]
    # C: [10, 1]
    # D: [5, 5] - Dominated by B
    objectives = jnp.array([
        [1.0, 10.0],
        [2.0, 5.0],
        [10.0, 1.0],
        [5.0, 5.0]
    ])
    
    fronts = fast_non_dominated_sort(objectives)
    
    # Front 0 should be [0, 1, 2] (A, B, C)
    # Front 1 should be [3] (D)
    assert 0 in fronts[0]
    assert 1 in fronts[0]
    assert 2 in fronts[0]
    assert 3 in fronts[1]

def test_crowding_distance():
    """Verify crowding distance calculation."""
    # 3 points on a line: [1, 10], [5, 5], [10, 1]
    objectives = jnp.array([
        [1.0, 10.0],
        [5.0, 5.0],
        [10.0, 1.0]
    ])
    
    distances = calculate_crowding_distance(objectives)
    
    # Extremes (0 and 2) should have infinite distance
    assert distances[0] == float('inf')
    assert distances[2] == float('inf')
    # Middle point (1) should have finite distance
    assert distances[1] > 0
    assert distances[1] < float('inf')
