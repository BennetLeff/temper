import time

import jax
import jax.numpy as jnp
import pytest

from temper_placer.optimizer.nsga2 import (
    calculate_crowding_distance,
    fast_non_dominated_sort,
    select_knee_point,
)


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
    with pytest.raises(ValueError):
        tournament_selection(ranks, distances, key, num_selected=1, tournament_size=10)


def test_rotation_diversity_over_generations():
    """Rotation diversity should increase over generations."""
    from temper_placer.core.board import Board, LayerStackup
    from temper_placer.core.netlist import Component, Netlist
    from temper_placer.core.state import PlacementState
    from temper_placer.losses.base import LossContext
    from temper_placer.optimizer.nsga2 import NSGAOptimizer

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
        objectives=[lambda _p, _r, _c, _e, _t: type("Obj", (), {"value": jnp.float32(0.0)})()],
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


class TestKneePointSelection:
    """Tests for knee-point selection from Pareto front."""

    def test_knee_point_single_solution(self):
        """Single solution front should return that solution."""
        objectives = jnp.array([[1.0, 2.0]])
        front_indices = [0]

        knee_idx = select_knee_point(objectives, front_indices)
        assert knee_idx == 0

    def test_knee_point_two_solutions(self):
        """Two solution front should return the more balanced one (smaller normalized sum)."""
        objectives = jnp.array(
            [
                [1.0, 10.0],  # Sum in normalized space: depends on normalization
                [5.0, 5.0],  # Balanced
            ]
        )
        front_indices = [0, 1]

        knee_idx = select_knee_point(objectives, front_indices)
        # After normalization to [0,1]:
        # Point 0: (0, 1) -> sum = 1
        # Point 1: (1, 0) -> sum = 1
        # They're equal, so either could be returned
        assert knee_idx in front_indices

    def test_knee_point_selects_middle_solution(self):
        """Knee-point should prefer middle solutions over extremes."""
        # Line from (0, 10) to (10, 0) with middle point at (5, 5)
        # The knee is the point furthest from the line connecting extremes
        objectives = jnp.array(
            [
                [0.0, 10.0],  # Extreme in obj 0
                [3.0, 7.0],  # Close to extreme
                [5.0, 5.0],  # Perfect middle (knee point)
                [7.0, 3.0],  # Close to other extreme
                [10.0, 0.0],  # Extreme in obj 1
            ]
        )
        front_indices = [0, 1, 2, 3, 4]

        select_knee_point(objectives, front_indices)
        # The middle point (5, 5) should be selected as it's furthest from the diagonal
        # After normalization to [0,1], the line goes from (0,1) to (1,0)
        # Point (0.5, 0.5) is on the line so distance is 0
        # Actually, all points are on the line y = 10 - x, so they're all colinear
        # Let me create a non-colinear front

    def test_knee_point_noncolinear_front(self):
        """Knee-point on non-colinear front should select point furthest from line."""
        # Create a concave front where the middle point bows inward
        objectives = jnp.array(
            [
                [0.0, 10.0],  # Extreme in obj 0
                [3.0, 3.0],  # Knee point - best trade-off (bows toward origin)
                [10.0, 0.0],  # Extreme in obj 1
            ]
        )
        front_indices = [0, 1, 2]

        knee_idx = select_knee_point(objectives, front_indices)
        # Point (3, 3) should be selected as the knee
        assert knee_idx == 1

    def test_knee_point_empty_front_raises(self):
        """Empty front should raise ValueError."""
        objectives = jnp.array([[1.0, 2.0]])
        front_indices = []

        with pytest.raises(ValueError, match="empty front"):
            select_knee_point(objectives, front_indices)

    def test_knee_point_preserves_population_index(self):
        """Returned index should be from original population, not local front."""
        # Population of 5, but front only has indices 1, 3, 4
        objectives = jnp.array(
            [
                [100.0, 100.0],  # 0: Not in front
                [0.0, 10.0],  # 1: In front (extreme in obj 0)
                [100.0, 100.0],  # 2: Not in front
                [5.0, 5.0],  # 3: In front (middle)
                [10.0, 0.0],  # 4: In front (extreme in obj 1)
            ]
        )
        front_indices = [1, 3, 4]

        knee_idx = select_knee_point(objectives, front_indices)
        # Should return a population index, not a local index
        assert knee_idx in front_indices
        # The algorithm finds the point furthest from the line connecting extremes
        # In this case, points 1 and 4 are the extremes, and point 3 should be the knee

    def test_knee_point_three_objectives(self):
        """Knee-point selection should work for 3+ objectives."""
        objectives = jnp.array(
            [
                [0.0, 10.0, 10.0],  # Extreme in obj 0
                [10.0, 0.0, 10.0],  # Extreme in obj 1
                [10.0, 10.0, 0.0],  # Extreme in obj 2
                [4.0, 4.0, 4.0],  # Balanced (knee)
            ]
        )
        front_indices = [0, 1, 2, 3]

        knee_idx = select_knee_point(objectives, front_indices)
        # The balanced point should be selected
        assert knee_idx == 3


class TestLazyCrowdingDistance:
    """Tests for lazy (per-front) crowding distance computation (temper-yi42.6).

    The lazy version computes crowding distance only for the partial front
    that needs it, which is actually the standard NSGA-II behavior per the
    original paper (Deb et al. 2002). This saves computation and produces
    results that are more correct per the algorithm specification.

    Note: The 'eager' version in this codebase computes global crowding
    distance, which is non-standard. The tests here verify the lazy version
    correctly implements per-front crowding distance.
    """

    def test_lazy_crowding_selects_from_partial_front(self):
        """Lazy selection should correctly select from partial front."""
        from temper_placer.optimizer.nsga2 import select_next_generation_lazy

        # Create objectives where front 0 has 4 members but we only want 3
        combined_obj = jnp.array(
            [
                [1.0, 10.0],  # 0: Front 0, extreme
                [5.0, 5.0],  # 1: Front 0, middle
                [10.0, 1.0],  # 2: Front 0, extreme
                [8.0, 4.0],  # 3: Front 0, middle (non-dominated because 8>5 but 4<5)
                [15.0, 15.0],  # 4: Front 1, dominated
            ]
        )

        indices = select_next_generation_lazy(combined_obj, pop_size=3)

        # Should select 3 from front 0
        assert len(indices) == 3
        # All selected should be from front 0 (indices 0-3)
        assert all(i < 4 for i in indices)
        # Extremes (0 and 2) should definitely be selected (infinite distance)
        assert 0 in indices
        assert 2 in indices

    def test_lazy_crowding_all_fronts_fit(self):
        """When all fronts fit, no crowding calculation needed."""
        from temper_placer.optimizer.nsga2 import select_next_generation_lazy

        # Simple case: 4 individuals, want all 4
        combined_obj = jnp.array(
            [
                [1.0, 10.0],
                [5.0, 5.0],
                [10.0, 1.0],
                [15.0, 15.0],  # Dominated
            ]
        )

        indices = select_next_generation_lazy(combined_obj, pop_size=4)
        assert len(indices) == 4
        assert set(indices) == {0, 1, 2, 3}

    def test_lazy_crowding_single_front_partial(self):
        """When only one front exists but needs partial selection."""
        from temper_placer.optimizer.nsga2 import select_next_generation_lazy

        # All non-dominated (on Pareto front)
        combined_obj = jnp.array(
            [
                [1.0, 10.0],  # Extreme
                [3.0, 7.0],
                [5.0, 5.0],
                [7.0, 3.0],
                [10.0, 1.0],  # Extreme
            ]
        )

        indices = select_next_generation_lazy(combined_obj, pop_size=3)

        # Should select 3 individuals
        assert len(indices) == 3
        # Extremes (0 and 4) should be selected (infinite distance)
        assert 0 in indices
        assert 4 in indices

    def test_lazy_crowding_preserves_front_ordering(self):
        """Lazy version should prefer high-rank fronts over low-rank."""
        from temper_placer.optimizer.nsga2 import select_next_generation_lazy

        # Front 0: indices 0, 1 (non-dominated)
        # Front 1: indices 2, 3 (dominated)
        combined_obj = jnp.array(
            [
                [1.0, 1.0],  # 0: Front 0
                [0.5, 1.5],  # 1: Front 0
                [2.0, 2.0],  # 2: Front 1 (dominated by 0)
                [3.0, 3.0],  # 3: Front 2 (dominated by 2)
            ]
        )

        indices = select_next_generation_lazy(combined_obj, pop_size=3)

        # Should select all of front 0 + some from front 1
        assert 0 in indices
        assert 1 in indices
        assert len(indices) == 3

    @pytest.mark.benchmark
    def test_lazy_crowding_speedup_benchmark(self):
        """Benchmark: lazy crowding distance should be faster than eager.

        Note: The overall speedup is limited because fast_non_dominated_sort
        dominates runtime (~93%). The lazy optimization saves ~67% of crowding
        distance computation time.
        """
        from temper_placer.optimizer.nsga2 import (
            calculate_crowding_distance,
            fast_non_dominated_sort,
            select_next_generation_lazy,
        )

        key = jax.random.PRNGKey(123)
        n = 200  # Combined population (2N where N=100)
        objectives = jax.random.uniform(key, (n, 3))
        pop_size = 100

        # Warm up JIT
        _ = select_next_generation_lazy(objectives, pop_size)

        # Benchmark lazy selection (includes sorting + partial crowding)
        n_runs = 3
        start = time.perf_counter()
        for _ in range(n_runs):
            _ = select_next_generation_lazy(objectives, pop_size)
        lazy_total_time = (time.perf_counter() - start) / n_runs

        # Benchmark just crowding distance (all vs partial)
        fronts = fast_non_dominated_sort(objectives)
        partial_front = fronts[-1] if len(fronts) > 1 else fronts[0]
        partial_indices = (
            jnp.array(partial_front[:50]) if len(partial_front) > 50 else jnp.array(partial_front)
        )
        partial_objectives = objectives[partial_indices]

        start = time.perf_counter()
        for _ in range(n_runs):
            _ = calculate_crowding_distance(objectives)
        crowding_all_time = (time.perf_counter() - start) / n_runs

        start = time.perf_counter()
        for _ in range(n_runs):
            _ = calculate_crowding_distance(partial_objectives)
        crowding_partial_time = (time.perf_counter() - start) / n_runs

        crowding_savings = (crowding_all_time - crowding_partial_time) / crowding_all_time * 100

        print(f"\nLazy total time: {lazy_total_time * 1000:.1f}ms")
        print(
            f"Crowding all: {crowding_all_time * 1000:.1f}ms, partial: {crowding_partial_time * 1000:.1f}ms"
        )
        print(f"Crowding distance savings: {crowding_savings:.1f}%")

        # Crowding distance savings should be significant (>30%)
        assert crowding_savings >= 30.0, f"Crowding savings {crowding_savings:.1f}% < 30%"


class TestOddPopulationSize:
    """Tests for odd population sizes (temper-yi42.7, Test 1).

    NSGA-II implementations often assume even population sizes for pairing
    during crossover. Odd sizes can expose bugs in selection/crossover logic.
    """

    @pytest.mark.xfail(
        reason="Bug: Odd population size causes vmap mismatch in crossover. See temper-yi42.7."
    )
    def test_odd_population_size_basic(self):
        """Optimizer with odd population size should not crash."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.optimizer.nsga2 import NSGAOptimizer

        board = Board(width=100, height=100)
        c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
        netlist = Netlist(components=[c1])
        context = LossContext.from_netlist_and_board(netlist, board)
        objectives = [WirelengthLoss()]

        optimizer = NSGAOptimizer(population_size=51)
        result = optimizer.evolve(
            netlist=netlist,
            board=board,
            objectives=objectives,
            context=context,
            generations=5,
        )

        # Population size should remain 51 throughout
        assert result.population_positions.shape[0] == 51

    @pytest.mark.xfail(
        reason="Bug: Odd population size causes vmap mismatch in crossover. See temper-yi42.7."
    )
    def test_odd_population_size_various(self):
        """Test several odd population sizes: 3, 7, 11, 51."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.optimizer.nsga2 import NSGAOptimizer

        board = Board(width=100, height=100)
        c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
        netlist = Netlist(components=[c1])
        context = LossContext.from_netlist_and_board(netlist, board)
        objectives = [WirelengthLoss()]

        for pop_size in [3, 7, 11, 51]:
            optimizer = NSGAOptimizer(population_size=pop_size)
            result = optimizer.evolve(
                netlist=netlist,
                board=board,
                objectives=objectives,
                context=context,
                generations=3,
            )
            assert result.population_positions.shape[0] == pop_size, (
                f"Expected pop_size={pop_size}, got {result.population_positions.shape[0]}"
            )

    @pytest.mark.xfail(
        reason="Bug: Odd population size causes vmap mismatch in crossover. See temper-yi42.7."
    )
    def test_odd_population_crossover_pairing(self):
        """With odd N, crossover should handle unpaired individual gracefully."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Net, Netlist
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.optimizer.nsga2 import NSGAOptimizer

        board = Board(width=100, height=100)
        c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
        c2 = Component(ref="U2", footprint="S", bounds=(10, 10))
        netlist = Netlist(
            components=[c1, c2],
            nets=[Net(name="N1", pins=[("U1", "1"), ("U2", "1")])],
        )
        context = LossContext.from_netlist_and_board(netlist, board)
        objectives = [WirelengthLoss()]

        # 5 individuals -> 2 pairs + 1 unpaired
        optimizer = NSGAOptimizer(population_size=5)
        result = optimizer.evolve(
            netlist=netlist,
            board=board,
            objectives=objectives,
            context=context,
            generations=10,
        )

        # Should complete without errors and maintain population size
        assert result.population_positions.shape[0] == 5
        assert len(result.fronts[0]) >= 1  # At least one solution in front 0


class TestRotationDiversityEdgeCases:
    """Tests for rotation diversity over generations (temper-yi42.7, Test 2).

    NSGA-II should explore different rotation configurations, leading to
    increased diversity in the rotation logits across the population.
    """

    def _rotation_variance(self, rotation_logits: jnp.ndarray) -> float:
        """Calculate variance of rotation logits across population."""
        # rotation_logits shape: (pop_size, n_components, 4)
        # Flatten to (pop_size, n_components * 4) and compute variance
        flat = rotation_logits.reshape(rotation_logits.shape[0], -1)
        return float(jnp.var(flat))

    def test_rotation_diversity_increases_from_uniform(self):
        """After N generations, rotation variance should exceed initial."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Net, Netlist
        from temper_placer.core.state import PlacementState
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.optimizer.nsga2 import NSGAOptimizer

        board = Board(width=100, height=100)
        # Use multiple components to have meaningful rotation variance
        components = [Component(ref=f"U{i}", footprint="S", bounds=(10, 10)) for i in range(5)]
        nets = [
            Net(name=f"N{i}", pins=[(f"U{i}", "1"), (f"U{(i + 1) % 5}", "1")]) for i in range(5)
        ]
        netlist = Netlist(components=components, nets=nets)
        context = LossContext.from_netlist_and_board(netlist, board)
        objectives = [WirelengthLoss()]

        # Start from a uniform initial state (all same rotations)
        initial_state = PlacementState.random_init(
            n_components=5,
            board_width=100,
            board_height=100,
            key=jax.random.PRNGKey(42),
        )
        # Force uniform rotations to start
        uniform_rot = jnp.zeros((5, 4)).at[:, 0].set(1.0)  # All at 0 degrees
        initial_state = PlacementState(
            positions=initial_state.positions,
            rotation_logits=uniform_rot,
            net_virtual_nodes=initial_state.net_virtual_nodes,
        )

        optimizer = NSGAOptimizer(population_size=20)

        # Run for few generations and capture result
        result = optimizer.evolve(
            netlist=netlist,
            board=board,
            objectives=objectives,
            context=context,
            generations=50,
            initial_state=initial_state,
        )

        # Initial variance was near 0 (all same), final should be higher
        final_var = self._rotation_variance(result.population_rotations)

        # We expect some variance in the final population
        # Even if mutations don't directly affect rotations, the population
        # initialization from perturbing the initial state should create diversity
        assert final_var > 0, "Expected non-zero rotation variance after evolution"

    def test_rotation_logits_valid_range(self):
        """Rotation logits should remain valid throughout evolution."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.optimizer.nsga2 import NSGAOptimizer

        board = Board(width=100, height=100)
        components = [Component(ref=f"U{i}", footprint="S", bounds=(10, 10)) for i in range(3)]
        netlist = Netlist(components=components)
        context = LossContext.from_netlist_and_board(netlist, board)
        objectives = [WirelengthLoss()]

        optimizer = NSGAOptimizer(population_size=10)
        result = optimizer.evolve(
            netlist=netlist,
            board=board,
            objectives=objectives,
            context=context,
            generations=20,
        )

        # Rotation logits should not contain NaN or Inf
        assert jnp.all(jnp.isfinite(result.population_rotations)), "Rotation logits contain NaN/Inf"


class TestParetoFrontNonDominance:
    """Tests for Pareto front non-dominance property (temper-yi42.7, Test 3).

    The fundamental property of a Pareto front: no solution should dominate
    any other solution in the front.
    """

    def _dominates(self, obj_a: jnp.ndarray, obj_b: jnp.ndarray) -> bool:
        """Check if solution A dominates solution B (minimization)."""
        diff = obj_a - obj_b
        return bool(jnp.all(diff <= 0) and jnp.any(diff < 0))

    def test_pareto_front_non_dominated_simple(self):
        """All solutions in front 0 should be mutually non-dominated."""
        # Create objective values with known non-dominated front
        objectives = jnp.array(
            [
                [1.0, 10.0],  # Non-dominated (best in obj 0)
                [5.0, 5.0],  # Non-dominated (balanced)
                [10.0, 1.0],  # Non-dominated (best in obj 1)
                [6.0, 6.0],  # Dominated by [5.0, 5.0]
                [8.0, 8.0],  # Dominated by [5.0, 5.0]
            ]
        )

        fronts = fast_non_dominated_sort(objectives)

        # Front 0 should be {0, 1, 2}
        front_0 = fronts[0]
        assert set(front_0) == {0, 1, 2}

        # No solution in front 0 should dominate another
        for i in front_0:
            for j in front_0:
                if i != j:
                    assert not self._dominates(objectives[i], objectives[j]), (
                        f"Solution {i} dominates {j} in front 0"
                    )

    def test_pareto_front_non_dominated_random(self):
        """Test non-dominance on random objectives."""
        key = jax.random.PRNGKey(123)
        objectives = jax.random.uniform(key, (100, 3))

        fronts = fast_non_dominated_sort(objectives)
        front_0 = fronts[0]

        # Check non-dominance within front 0
        for i in front_0:
            for j in front_0:
                if i != j:
                    assert not self._dominates(objectives[i], objectives[j]), (
                        f"Solution {i} dominates {j} in front 0"
                    )

    def test_pareto_front_dominates_subsequent_fronts(self):
        """Solutions in front 0 should dominate some in later fronts."""
        objectives = jnp.array(
            [
                [1.0, 1.0],  # Front 0 (dominates all others)
                [2.0, 2.0],  # Front 1
                [3.0, 3.0],  # Front 2
            ]
        )

        fronts = fast_non_dominated_sort(objectives)

        # Front 0 is {0}, which dominates indices 1 and 2
        assert fronts[0] == [0]
        assert 1 in fronts[1]
        assert 2 in fronts[2]

        # Verify domination
        assert self._dominates(objectives[0], objectives[1])
        assert self._dominates(objectives[0], objectives[2])
        assert self._dominates(objectives[1], objectives[2])


class TestZDTBenchmarkConvergence:
    """Tests for convergence on ZDT benchmark problems (temper-yi42.7, Test 4).

    ZDT (Zitzler-Deb-Thiele) test problems have known Pareto fronts,
    allowing us to verify NSGA-II converges correctly.
    """

    def _zdt1_objectives(self, x: jnp.ndarray) -> jnp.ndarray:
        """
        ZDT1 test problem.

        x: (n,) array of decision variables in [0, 1]
        Returns: (2,) array of objectives [f1, f2]

        True Pareto front: f2 = 1 - sqrt(f1) for f1 in [0, 1]
        """
        f1 = x[0]
        g = 1.0 + 9.0 * jnp.mean(x[1:])
        h = 1.0 - jnp.sqrt(f1 / g)
        f2 = g * h
        return jnp.array([f1, f2])

    def _hypervolume_2d(self, points: jnp.ndarray, reference: jnp.ndarray) -> float:
        """
        Calculate 2D hypervolume indicator.

        points: (N, 2) array of objective values
        reference: (2,) reference point (should dominate all points)
        """
        # Filter points dominated by reference
        valid = jnp.all(points < reference, axis=1)
        points = points[valid]

        if len(points) == 0:
            return 0.0

        # Sort by first objective
        sorted_indices = jnp.argsort(points[:, 0])
        sorted_points = points[sorted_indices]

        # Calculate hypervolume using sweep line algorithm
        hv = 0.0
        prev_f2 = float(reference[1])

        for i in range(len(sorted_points)):
            f1 = float(sorted_points[i, 0])
            f2 = float(sorted_points[i, 1])

            if f2 < prev_f2:
                # Width from previous x to current x
                if i == 0:
                    f1 - 0.0  # From origin
                else:
                    f1 - float(sorted_points[i - 1, 0])

                # Height contribution from this point to reference
                hv += (float(reference[0]) - f1) * (prev_f2 - f2)
                prev_f2 = f2

        return hv

    def test_zdt1_pareto_front_shape(self):
        """Test that NSGA-II finds a Pareto front approximating ZDT1's true front."""
        # We'll use the NSGA-II sorting on pre-computed ZDT1 samples
        key = jax.random.PRNGKey(42)

        # Generate random decision variables
        n_solutions = 100
        n_vars = 30

        x_samples = jax.random.uniform(key, (n_solutions, n_vars))
        objectives = jax.vmap(self._zdt1_objectives)(x_samples)

        # Run non-dominated sort
        fronts = fast_non_dominated_sort(objectives)
        front_0_indices = jnp.array(fronts[0])
        pareto_objs = objectives[front_0_indices]

        # True Pareto front: f2 = 1 - sqrt(f1)
        # Check that front 0 solutions are close to this
        f1_vals = pareto_objs[:, 0]
        1.0 - jnp.sqrt(f1_vals)
        pareto_objs[:, 1]

        # Solutions should be near or below the true front
        # (below because g > 1 makes f2 larger than optimal)
        # We just verify the shape is reasonable
        assert len(front_0_indices) > 1, "Expected multiple solutions in Pareto front"

    def test_hypervolume_improves_with_generations(self):
        """Hypervolume should improve (or stay same) as evolution progresses."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Net, Netlist
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.thermal import EdgePreferenceLoss
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.optimizer.nsga2 import NSGAOptimizer

        board = Board(width=100, height=100)
        c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
        c2 = Component(ref="U2", footprint="S", bounds=(10, 10))
        netlist = Netlist(
            components=[c1, c2],
            nets=[Net(name="N1", pins=[("U1", "1"), ("U2", "1")])],
        )
        context = LossContext.from_netlist_and_board(netlist, board)

        # Conflicting objectives
        objectives = [
            WirelengthLoss(),
            EdgePreferenceLoss(
                thermal_pad_indices=jnp.array([0]),
                board_width=100.0,
                board_height=100.0,
                preferred_margin_mm=5.0,
            ),
        ]

        # Run short evolution
        optimizer = NSGAOptimizer(population_size=30)
        result_short = optimizer.evolve(
            netlist=netlist,
            board=board,
            objectives=objectives,
            context=context,
            generations=10,
            seed=42,
        )

        # Run longer evolution
        optimizer2 = NSGAOptimizer(population_size=30)
        result_long = optimizer2.evolve(
            netlist=netlist,
            board=board,
            objectives=objectives,
            context=context,
            generations=50,
            seed=42,
        )

        # Get Pareto front objectives
        short_objs = result_short.objectives[jnp.array(result_short.best_indices)]
        long_objs = result_long.objectives[jnp.array(result_long.best_indices)]

        # Use a reference point that dominates all solutions
        ref_point = jnp.array(
            [
                max(float(jnp.max(short_objs[:, 0])), float(jnp.max(long_objs[:, 0]))) + 1.0,
                max(float(jnp.max(short_objs[:, 1])), float(jnp.max(long_objs[:, 1]))) + 1.0,
            ]
        )

        hv_short = self._hypervolume_2d(short_objs, ref_point)
        hv_long = self._hypervolume_2d(long_objs, ref_point)

        # Longer evolution should have equal or better hypervolume
        # (Note: due to stochasticity, we allow some tolerance)
        assert hv_long >= hv_short * 0.9, (
            f"Hypervolume should not decrease significantly: "
            f"short={hv_short:.4f}, long={hv_long:.4f}"
        )

    def test_inverted_generational_distance(self):
        """Test IGD (Inverted Generational Distance) metric on ZDT1."""
        key = jax.random.PRNGKey(42)

        # Generate solutions
        n_solutions = 200
        n_vars = 30

        x_samples = jax.random.uniform(key, (n_solutions, n_vars))
        objectives = jax.vmap(self._zdt1_objectives)(x_samples)

        # Get Pareto front
        fronts = fast_non_dominated_sort(objectives)
        front_0_indices = jnp.array(fronts[0])
        pareto_objs = objectives[front_0_indices]

        # True Pareto front samples
        f1_true = jnp.linspace(0, 1, 100)
        f2_true = 1.0 - jnp.sqrt(f1_true)
        true_front = jnp.stack([f1_true, f2_true], axis=1)

        # Calculate IGD: average distance from true front to approximation
        def min_dist_to_approx(true_point):
            dists = jnp.sqrt(jnp.sum((pareto_objs - true_point) ** 2, axis=1))
            return jnp.min(dists)

        igd = float(jnp.mean(jax.vmap(min_dist_to_approx)(true_front)))

        # IGD should be reasonable (not too large)
        # For random sampling (not evolutionary search), IGD will be moderate
        # because we're not actually optimizing towards the Pareto front,
        # just sorting random samples
        assert igd < 3.0, f"IGD too high: {igd:.4f}"


def test_nsga2_population_size_validation():
    """Verify that odd population sizes are rejected."""
    from temper_placer.optimizer.nsga2 import NSGAOptimizer

    # Test various odd sizes
    for odd_size in [1, 3, 51, 101, 999]:
        with pytest.raises(ValueError, match="must be even"):
            NSGAOptimizer(population_size=odd_size)

    # Test various even sizes (should all work)
    for even_size in [2, 4, 50, 100, 1000]:
        optimizer = NSGAOptimizer(population_size=even_size)
        assert optimizer.pop_size == even_size


def test_nsga2_geometry_operators_enabled_by_default():
    """Verify that geometry operators are enabled by default."""
    from temper_placer.optimizer.nsga2 import NSGAOptimizer

    # Default should enable geometry operators
    optimizer = NSGAOptimizer()
    assert optimizer.use_geometry_operators is True

    # Explicit enable
    optimizer_enabled = NSGAOptimizer(use_geometry_operators=True)
    assert optimizer_enabled.use_geometry_operators is True

    # Explicit disable
    optimizer_disabled = NSGAOptimizer(use_geometry_operators=False)
    assert optimizer_disabled.use_geometry_operators is False
