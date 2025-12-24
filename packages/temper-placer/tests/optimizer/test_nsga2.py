import jax
import jax.numpy as jnp
import pytest

from temper_placer.optimizer.nsga2 import calculate_crowding_distance, fast_non_dominated_sort


def test_non_dominated_sort_simple():
    """Verify sorting of a simple 2D objective space."""
    # Objectives (minimize both):
    # A: [1, 10]
    # B: [2, 5]
    # C: [10, 1]
    # D: [5, 5] - Dominated by B
    objectives = jnp.array([[1.0, 10.0], [2.0, 5.0], [10.0, 1.0], [5.0, 5.0]])

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
    objectives = jnp.array([[1.0, 10.0], [5.0, 5.0], [10.0, 1.0]])

    distances = calculate_crowding_distance(objectives)

    # Extremes (0 and 2) should have infinite distance
    assert distances[0] == float("inf")
    assert distances[2] == float("inf")
    # Middle point (1) should have finite distance
    assert distances[1] > 0
    assert distances[1] < float("inf")


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
    assert distances[0] == float("inf")


def test_nsga2_two_individuals():
    """Two individuals: correct domination and crowding."""
    # A dominates B
    objectives = jnp.array(
        [
            [1.0, 1.0],  # A
            [2.0, 2.0],  # B
        ]
    )
    fronts = fast_non_dominated_sort(objectives)
    assert fronts == [[0], [1]]

    # Crowding distance for n=2 should be Inf for both
    distances = calculate_crowding_distance(objectives)
    assert distances[0] == float("inf")
    assert distances[1] == float("inf")


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
    objectives = jnp.array([[10.0, 10.0], [10.0, 10.0], [10.0, 10.0]])

    # 1. Non-dominated sort: all should be in front 0
    fronts = fast_non_dominated_sort(objectives)
    assert fronts == [[0, 1, 2]]

    # 2. Crowding distance: should not crash and return finite or infinite values
    distances = calculate_crowding_distance(objectives)
    assert jnp.all(jnp.logical_not(jnp.isnan(distances)))


def test_nsga2_tournament_selection_edge_cases():
    """Test tournament selection with edge cases."""
    from temper_placer.optimizer.nsga2 import tournament_selection

    ranks = jnp.array([0, 0, 1, 1, 2])  # Lower is better
    distances = jnp.array([10.0, 5.0, 10.0, 5.0, 10.0])  # Higher is better
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


def test_rotation_diversity_over_generations():
    """Rotation diversity should increase over generations."""
    from temper_placer.optimizer.nsga2 import NSGAOptimizer
    from temper_placer.core.board import Board, LayerStackup
    from temper_placer.core.netlist import Component, Net, Netlist
    from temper_placer.core.state import PlacementState
    from temper_placer.losses.base import LossContext

    board = Board(
        width=100,
        height=100,
        origin=(0, 0),
        zones=[],
        ground_domains=[],
        layer_stackup=LayerStackup.default_4layer(),
    )

    c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
    c2 = Component(ref="U2", footprint="S", bounds=(10, 10))
    netlist = Netlist(components=[c1, c2], nets=[])
    context = LossContext.from_netlist_and_board(netlist, board)

    # Create initial state with fixed rotations
    initial_rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]])
    initial_state = PlacementState(
        positions=jnp.array([[20.0, 20.0], [80.0, 80.0]]), rotation_logits=initial_rotations
    )

    optimizer = NSGAOptimizer(population_size=20, mutation_rate=0.2)

    result = optimizer.evolve(
        netlist=netlist,
        board=board,
        objectives=[lambda p, r, c, e, t: type("Obj", (), {"value": jnp.zeros(p.shape[0])})()],
        context=context,
        generations=10,
        initial_state=initial_state,
        seed=42,
    )

    # Calculate rotation variance in final population
    # Convert logits to rotation indices (0, 1, 2, 3)
    final_rotations = jnp.argmax(result.population_rotations, axis=-1)
    # Variance of rotation indices
    rotation_variance = jnp.var(final_rotations.flatten())

    # Variance should be > 0 (initial variance was 0 since all rotations were the same)
    assert rotation_variance > 0, f"Rotation variance should increase, but got {rotation_variance}"


def test_rotation_crossover_differs_from_parents():
    """Rotation crossover should produce children with different rotations than parents."""
    from temper_placer.optimizer.nsga2 import crossover_blx_alpha

    # Parent rotations with different preferences
    parent1_rot = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    parent2_rot = jnp.array([[0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])

    key = jax.random.PRNGKey(42)

    # Perform crossover
    child_rot = crossover_blx_alpha(parent1_rot, parent2_rot, key, alpha=0.5)

    # Child should differ from both parents
    assert not jnp.allclose(child_rot, parent1_rot, atol=0.1)
    assert not jnp.allclose(child_rot, parent2_rot, atol=0.1)


def test_rotation_mutation_stochastic_changes():
    """Rotation mutation should introduce stochastic changes to rotation logits."""
    from temper_placer.optimizer.nsga2 import mutate_gaussian

    # Initial rotation logits
    initial_rot = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]])

    key = jax.random.PRNGKey(42)

    # Apply mutation with rate > 0
    mutated_rot = mutate_gaussian(initial_rot, key, sigma=1.0, rate=0.5)

    # Some logits should have changed (not all identical to initial)
    # Check that at least one value differs significantly
    differences = jnp.abs(mutated_rot - initial_rot)
    max_diff = jnp.max(differences)

    assert max_diff > 0.1, f"Mutation should change logits, but max diff is {max_diff}"

def test_rotation_diversity_over_generations():
    """Rotation diversity should increase over generations."""
    from temper_placer.optimizer.nsga2 import NSGAOptimizer
    from temper_placer.core.board import Board, LayerStackup
    from temper_placer.core.netlist import Component, Netlist
    from temper_placer.core.state import PlacementState
    from temper_placer.losses.base import LossContext

    board = Board(width=100, height=100, origin=(0, 0), zones=[], ground_domains=[],
                  layer_stackup=LayerStackup.default_4layer())

    c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
    c2 = Component(ref="U2", footprint="S", bounds=(10, 10))
    netlist = Netlist(components=[c1, c2], nets=[])
    context = LossContext.from_netlist_and_board(netlist, board)

    # Create initial state with fixed rotations
    initial_rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]])
    initial_state = PlacementState(
        positions=jnp.array([[20.0, 20.0], [80.0, 80.0]]),
        rotation_logits=initial_rotations
    )

    optimizer = NSGAOptimizer(population_size=20, mutation_rate=0.2)

    result = optimizer.evolve(
        netlist=netlist,
        board=board,
        objectives=[lambda p, r, c, e, t: type('Obj', (), {'value': jnp.zeros(p.shape[0])})()],
        context=context,
        generations=10,
        initial_state=initial_state,
        seed=42
    )

    # Calculate rotation variance in final population
    final_rotations = jnp.argmax(result.population_rotations, axis=-1)
    rotation_variance = jnp.var(final_rotations.flatten())

    # Variance should be > 0 (initial variance was 0 since all rotations were same)
    assert rotation_variance > 0, f"Rotation variance should increase, but got {rotation_variance}"

def test_rotation_crossover_differs_from_parents():
    """Rotation crossover should produce children with different rotations than parents."""
    from temper_placer.optimizer.nsga2 import crossover_blx_alpha

    # Parent rotations with different preferences
    parent1_rot = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    parent2_rot = jnp.array([[0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])

    key = jax.random.PRNGKey(42)

    # Perform crossover
    child_rot = crossover_blx_alpha(parent1_rot, parent2_rot, key, alpha=0.5)

    # Child should differ from both parents
    assert not jnp.allclose(child_rot, parent1_rot, atol=0.1)
    assert not jnp.allclose(child_rot, parent2_rot, atol=0.1)

def test_rotation_mutation_stochastic_changes():
    """Rotation mutation should introduce stochastic changes to rotation logits."""
    from temper_placer.optimizer.nsga2 import mutate_gaussian

    # Initial rotation logits
    initial_rot = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]])

    key = jax.random.PRNGKey(42)

    # Apply mutation with rate > 0
    mutated_rot = mutate_gaussian(initial_rot, key, sigma=1.0, rate=0.5)

    # Some logits should have changed (not all identical to initial)
    differences = jnp.abs(mutated_rot - initial_rot)
    max_diff = jnp.max(differences)

    assert max_diff > 0.1, f"Mutation should change logits, but max diff is {max_diff}"
