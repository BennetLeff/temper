
import pytest
import jax
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

def test_nsga2_empty_population():
    """Empty population (n=0) should return empty fronts, no crash."""
    objectives = jnp.zeros((0, 2))
    fronts = fast_non_dominated_sort(objectives)
    assert fronts == [[]]
    
    distances = calculate_crowding_distance(objectives)
    assert len(distances) == 0

def test_nsga2_single_individual():
    """Single individual should be in front 0 with infinite crowding distance."""
    objectives = jnp.array([[1.0, 1.0]])
    fronts = fast_non_dominated_sort(objectives)
    assert fronts == [[0]]
    
    distances = calculate_crowding_distance(objectives)
    assert distances[0] == float('inf')

def test_nsga2_two_individuals():
    """Two individuals: correct domination and crowding."""
    # A dominates B
    objectives = jnp.array([
        [1.0, 1.0],  # A
        [2.0, 2.0]   # B
    ])
    fronts = fast_non_dominated_sort(objectives)
    assert fronts == [[0], [1]]
    
    # Crowding distance for n=2 should be Inf for both
    distances = calculate_crowding_distance(objectives)
    assert distances[0] == float('inf')
    assert distances[1] == float('inf')

def test_nsga2_domination_transitive():
    """Verify that domination is transitive: A dom B, B dom C -> A dom C."""
    # Objectives (minimize):
    # A: [1, 1]
    # B: [2, 2]
    # C: [3, 3]
    
    # A dominates B
    diff_ab = jnp.array([1.0, 1.0]) - jnp.array([2.0, 2.0])
    a_dom_b = jnp.all(diff_ab <= 0) and jnp.any(diff_ab < 0)
    assert a_dom_b
    
    # B dominates C
    diff_bc = jnp.array([2.0, 2.0]) - jnp.array([3.0, 3.0])
    b_dom_c = jnp.all(diff_bc <= 0) and jnp.any(diff_bc < 0)
    assert b_dom_c
    
    # A should dominate C
    diff_ac = jnp.array([1.0, 1.0]) - jnp.array([3.0, 3.0])
    a_dom_c = jnp.all(diff_ac <= 0) and jnp.any(diff_ac < 0)
    assert a_dom_c

def test_nsga2_identical_objectives():
    """Verify NSGA-II behavior when all individuals have identical objectives."""
    objectives = jnp.array([
        [10.0, 10.0],
        [10.0, 10.0],
        [10.0, 10.0]
    ])
    
    # 1. Non-dominated sort: all should be in front 0
    fronts = fast_non_dominated_sort(objectives)
    assert fronts == [[0, 1, 2]]
    
    # 2. Crowding distance: should not crash and return finite or infinite values
    distances = calculate_crowding_distance(objectives)
    assert jnp.all(jnp.logical_not(jnp.isnan(distances)))

def test_nsga2_tournament_selection_edge_cases():
    """Test tournament selection with edge cases."""
    from temper_placer.optimizer.nsga2 import tournament_selection
    
    ranks = jnp.array([0, 0, 1, 1, 2]) # Lower is better
    distances = jnp.array([10.0, 5.0, 10.0, 5.0, 10.0]) # Higher is better
    key = jax.random.PRNGKey(42)
    
    # 1. tournament_size = pop_size (5)
    # Best should always be selected (rank 0, dist 10.0 -> index 0)
    sel = tournament_selection(ranks, distances, key, num_selected=10, tournament_size=5)
    assert jnp.all(sel == 0)
    
    # 2. tournament_size = 1
    # Random selection
    sel_rand = tournament_selection(ranks, distances, key, num_selected=100, tournament_size=1)
    # Check that it's not all same
    assert jnp.unique(sel_rand).shape[0] > 1
    
    # 3. tournament_size > pop_size
    # Current implementation uses jax.random.choice(replace=False), which might fail
    # if tournament_size > pop_size. 
    # Let's see if it crashes.
    with pytest.raises(Exception):
        tournament_selection(ranks, distances, key, num_selected=1, tournament_size=10)
