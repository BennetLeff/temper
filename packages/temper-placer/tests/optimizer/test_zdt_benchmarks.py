"""
ZDT (Zitzler-Deb-Thiele) test problems for NSGA-II correctness validation.

These benchmark problems have known analytical Pareto fronts, making them
ideal correctness oracles for multi-objective optimization algorithms.

References:
- Zitzler, Deb, Thiele (2000): "Comparison of Multiobjective Evolutionary Algorithms"
- Deb et al. (2002): "A fast and elitist multiobjective genetic algorithm: NSGA-II"
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import jax
import jax.numpy as jnp
import pytest
from jax import Array

from temper_placer.optimizer.nsga2 import fast_non_dominated_sort

# =============================================================================
# ZDT Test Problem Definitions
# =============================================================================


def zdt1(x: Array) -> Array:
    """
    ZDT1: Convex Pareto front.

    Decision variables: x ∈ [0, 1]^n (typically n=30)
    True Pareto front: f2 = 1 - sqrt(f1), f1 ∈ [0, 1]

    Args:
        x: Decision variable vector, shape (n,), values in [0, 1]

    Returns:
        Objective values [f1, f2]
    """
    f1 = x[0]
    g = 1.0 + 9.0 * jnp.mean(x[1:])
    f2 = g * (1.0 - jnp.sqrt(f1 / g))
    return jnp.array([f1, f2])


def zdt2(x: Array) -> Array:
    """
    ZDT2: Non-convex (concave) Pareto front.

    Decision variables: x ∈ [0, 1]^n (typically n=30)
    True Pareto front: f2 = 1 - (f1)^2, f1 ∈ [0, 1]

    Args:
        x: Decision variable vector, shape (n,), values in [0, 1]

    Returns:
        Objective values [f1, f2]
    """
    f1 = x[0]
    g = 1.0 + 9.0 * jnp.mean(x[1:])
    f2 = g * (1.0 - (f1 / g) ** 2)
    return jnp.array([f1, f2])


def zdt3(x: Array) -> Array:
    """
    ZDT3: Disconnected (discontinuous) Pareto front.

    Decision variables: x ∈ [0, 1]^n (typically n=30)
    True Pareto front: f2 = 1 - sqrt(f1) - f1*sin(10*pi*f1), for valid f1

    The Pareto front consists of 5 disconnected segments due to the sine term.

    Args:
        x: Decision variable vector, shape (n,), values in [0, 1]

    Returns:
        Objective values [f1, f2]
    """
    f1 = x[0]
    g = 1.0 + 9.0 * jnp.mean(x[1:])
    f2 = g * (1.0 - jnp.sqrt(f1 / g) - (f1 / g) * jnp.sin(10.0 * jnp.pi * f1))
    return jnp.array([f1, f2])


# =============================================================================
# True Pareto Front Generation
# =============================================================================


def true_pareto_front_zdt1(n_points: int = 100) -> Array:
    """
    Generate the true Pareto front for ZDT1.

    True front: f2 = 1 - sqrt(f1), f1 ∈ [0, 1]
    """
    f1 = jnp.linspace(0, 1, n_points)
    f2 = 1.0 - jnp.sqrt(f1)
    return jnp.stack([f1, f2], axis=1)


def true_pareto_front_zdt2(n_points: int = 100) -> Array:
    """
    Generate the true Pareto front for ZDT2.

    True front: f2 = 1 - f1^2, f1 ∈ [0, 1]
    """
    f1 = jnp.linspace(0, 1, n_points)
    f2 = 1.0 - f1**2
    return jnp.stack([f1, f2], axis=1)


def true_pareto_front_zdt3(n_points: int = 500) -> Array:
    """
    Generate the true Pareto front for ZDT3.

    The front consists of 5 disconnected segments.
    We sample densely and filter to valid (non-dominated) points.
    """
    f1 = jnp.linspace(0, 1, n_points)
    f2 = 1.0 - jnp.sqrt(f1) - f1 * jnp.sin(10.0 * jnp.pi * f1)

    # Stack and filter dominated points
    points = jnp.stack([f1, f2], axis=1)

    # Use non-dominated sort to get actual Pareto front
    fronts = fast_non_dominated_sort(points)
    front0_indices = jnp.array(fronts[0])
    return points[front0_indices]


# =============================================================================
# Quality Metrics
# =============================================================================


def hypervolume_2d(pareto_front: Array, reference_point: Array) -> float:
    """
    Calculate 2D hypervolume indicator.

    The hypervolume is the area dominated by the Pareto front and bounded
    by the reference point. Uses the standard "sweep line" algorithm.

    Args:
        pareto_front: (N, 2) array of non-dominated objective values
        reference_point: (2,) array defining the upper bound

    Returns:
        Hypervolume value (higher is better)
    """
    if len(pareto_front) == 0:
        return 0.0

    # Filter points that dominate the reference point (invalid)
    valid_mask = jnp.all(pareto_front < reference_point, axis=1)
    valid_points = pareto_front[valid_mask]

    if len(valid_points) == 0:
        return 0.0

    # Sort by first objective (ascending)
    sorted_indices = jnp.argsort(valid_points[:, 0])
    sorted_points = valid_points[sorted_indices]

    # Sweep line algorithm for 2D hypervolume
    # We sweep from left to right, tracking the "height" (in y direction)
    # that is dominated by points we've seen so far
    hv = 0.0
    prev_x = float(sorted_points[0, 0])
    current_height = float(reference_point[1] - sorted_points[0, 1])

    for i in range(1, len(sorted_points)):
        x = float(sorted_points[i, 0])
        y = float(sorted_points[i, 1])

        # Add rectangle from prev_x to current x, with current height
        width = x - prev_x
        if width > 0 and current_height > 0:
            hv += width * current_height

        # Update height: it's the max height dominated (i.e., min y seen so far)
        new_height = reference_point[1] - y
        if new_height > current_height:
            current_height = float(new_height)

        prev_x = x

    # Add final rectangle from last x to reference x
    last_x = float(sorted_points[-1, 0])
    width = float(reference_point[0]) - last_x
    if width > 0 and current_height > 0:
        hv += width * current_height

    return float(hv)


def inverted_generational_distance(found_front: Array, true_front: Array) -> float:
    """
    Calculate Inverted Generational Distance (IGD).

    IGD measures the average distance from each point in the true Pareto front
    to the closest point in the found front. Lower is better.

    IGD = (1/|P*|) * sum_{p* in P*} min_{p in P} d(p*, p)

    Args:
        found_front: (N, M) array of found non-dominated solutions
        true_front: (K, M) array of true Pareto-optimal points

    Returns:
        IGD value (lower is better)
    """
    if len(found_front) == 0:
        return float("inf")

    # For each true point, find distance to nearest found point
    # Euclidean distance
    distances = []
    for true_point in true_front:
        dists_to_found = jnp.sqrt(jnp.sum((found_front - true_point) ** 2, axis=1))
        min_dist = jnp.min(dists_to_found)
        distances.append(min_dist)

    return float(jnp.mean(jnp.array(distances)))


def spacing_metric(pareto_front: Array) -> float:
    """
    Calculate spacing metric (uniformity of distribution).

    Spacing measures how evenly distributed the solutions are along
    the Pareto front. Lower spacing means more uniform distribution.

    Args:
        pareto_front: (N, M) array of non-dominated solutions

    Returns:
        Spacing value (lower is better, 0 is perfectly uniform)
    """
    n = len(pareto_front)
    if n <= 1:
        return 0.0

    # Calculate distances to nearest neighbor for each point
    nn_distances = []
    for i in range(n):
        dists = jnp.sqrt(jnp.sum((pareto_front - pareto_front[i]) ** 2, axis=1))
        # Set self-distance to inf
        dists = dists.at[i].set(float("inf"))
        nn_distances.append(jnp.min(dists))

    nn_distances = jnp.array(nn_distances)
    mean_dist = jnp.mean(nn_distances)

    # Spacing is standard deviation of nearest-neighbor distances
    spacing = jnp.sqrt(jnp.mean((nn_distances - mean_dist) ** 2))
    return float(spacing)


# =============================================================================
# NSGA-II Runner for ZDT Problems
# =============================================================================


@dataclass
class ZDTResult:
    """Result of running NSGA-II on a ZDT problem."""

    found_front: Array  # Objective values of non-dominated solutions
    decision_vars: Array  # Decision variables of non-dominated solutions
    hypervolume: float
    igd: float
    spacing: float
    generations: int
    population_size: int


def run_nsga_on_zdt(
    problem_fn: Callable[[Array], Array],
    true_front: Array,
    n_vars: int = 30,
    pop_size: int = 100,
    generations: int = 100,
    reference_point: Array | None = None,
    seed: int = 42,
    mutation_prob: float | None = None,
) -> ZDTResult:
    """
    Run a simple NSGA-II implementation on a ZDT problem.

    This is a standalone implementation specifically for testing correctness,
    separate from the placement-oriented NSGA-II in nsga2.py.

    Args:
        problem_fn: ZDT function (zdt1, zdt2, or zdt3)
        true_front: True Pareto front for IGD calculation
        n_vars: Number of decision variables
        pop_size: Population size
        generations: Number of generations
        reference_point: Reference point for hypervolume (default [1.1, 1.1])
        seed: Random seed
        mutation_prob: Mutation probability per variable (default 1/n_vars)

    Returns:
        ZDTResult with metrics and solutions
    """
    if reference_point is None:
        reference_point = jnp.array([1.1, 1.1])
    if mutation_prob is None:
        mutation_prob = 1.0 / n_vars

    key = jax.random.PRNGKey(seed)

    # Initialize population: x ∈ [0, 1]^n_vars
    key, init_key = jax.random.split(key)
    population = jax.random.uniform(init_key, (pop_size, n_vars))

    # Evaluate initial population
    objectives = jax.vmap(problem_fn)(population)

    for _gen in range(generations):
        # Non-dominated sorting
        fronts = fast_non_dominated_sort(objectives)

        # Calculate crowding distances
        from temper_placer.optimizer.nsga2 import calculate_crowding_distance

        distances = calculate_crowding_distance(objectives)

        # Assign ranks
        ranks = jnp.zeros(pop_size, dtype=jnp.int32)
        for rank_val, front in enumerate(fronts):
            for idx in front:
                ranks = ranks.at[idx].set(rank_val)

        # Tournament selection
        key, sel_key = jax.random.split(key)
        parent_indices = _tournament_select(ranks, distances, sel_key, pop_size)

        # Crossover (SBX)
        key, cross_key = jax.random.split(key)
        offspring = _sbx_crossover(
            population[parent_indices[::2]], population[parent_indices[1::2]], cross_key
        )

        # Mutation (polynomial)
        key, mut_key = jax.random.split(key)
        offspring = _polynomial_mutation(offspring, mut_key, eta=20, prob=mutation_prob)

        # Clamp to [0, 1]
        offspring = jnp.clip(offspring, 0.0, 1.0)

        # Evaluate offspring
        offspring_obj = jax.vmap(problem_fn)(offspring)

        # Combine parents and offspring
        combined_pop = jnp.concatenate([population, offspring], axis=0)
        combined_obj = jnp.concatenate([objectives, offspring_obj], axis=0)

        # Environmental selection (NSGA-II)
        combined_fronts = fast_non_dominated_sort(combined_obj)
        combined_distances = calculate_crowding_distance(combined_obj)

        # Select best pop_size individuals
        next_indices = []
        for front in combined_fronts:
            if len(next_indices) + len(front) <= pop_size:
                next_indices.extend(front)
            else:
                # Fill remaining from current front by crowding distance
                needed = pop_size - len(next_indices)
                front_arr = jnp.array(front)
                front_dists = combined_distances[front_arr]
                sorted_by_dist = front_arr[jnp.argsort(-front_dists)]  # Descending
                next_indices.extend(sorted_by_dist[:needed].tolist())
                break

        next_indices = jnp.array(next_indices)
        population = combined_pop[next_indices]
        objectives = combined_obj[next_indices]

    # Final non-dominated sorting
    final_fronts = fast_non_dominated_sort(objectives)
    front0_indices = jnp.array(final_fronts[0])

    found_front = objectives[front0_indices]
    found_vars = population[front0_indices]

    # Calculate metrics
    hv = hypervolume_2d(found_front, reference_point)
    igd = inverted_generational_distance(found_front, true_front)
    sp = spacing_metric(found_front)

    return ZDTResult(
        found_front=found_front,
        decision_vars=found_vars,
        hypervolume=hv,
        igd=igd,
        spacing=sp,
        generations=generations,
        population_size=pop_size,
    )


def _tournament_select(ranks: Array, distances: Array, key: Array, n_select: int) -> Array:
    """Binary tournament selection based on rank and crowding distance."""
    pop_size = ranks.shape[0]

    def select_one(k):
        c1, c2 = jax.random.choice(k, pop_size, (2,), replace=False)
        # Prefer lower rank, then higher distance
        c1_better = (ranks[c1] < ranks[c2]) | (
            (ranks[c1] == ranks[c2]) & (distances[c1] > distances[c2])
        )
        return jnp.where(c1_better, c1, c2)

    keys = jax.random.split(key, n_select)
    return jax.vmap(select_one)(keys)


def _sbx_crossover(parents1: Array, parents2: Array, key: Array, eta: float = 20.0) -> Array:
    """Simulated Binary Crossover (SBX)."""
    n_pairs, n_vars = parents1.shape

    key, u_key = jax.random.split(key)
    u = jax.random.uniform(u_key, (n_pairs, n_vars))

    beta = jnp.where(
        u <= 0.5, jnp.power(2 * u, 1.0 / (eta + 1)), jnp.power(1.0 / (2 * (1 - u)), 1.0 / (eta + 1))
    )

    child1 = 0.5 * ((1 + beta) * parents1 + (1 - beta) * parents2)
    child2 = 0.5 * ((1 - beta) * parents1 + (1 + beta) * parents2)

    # Return both children concatenated
    return jnp.concatenate([child1, child2], axis=0)


def _polynomial_mutation(
    population: Array, key: Array, eta: float = 20.0, prob: float = 0.1
) -> Array:
    """Polynomial mutation."""
    shape = population.shape

    key, mask_key, delta_key = jax.random.split(key, 3)
    mask = jax.random.uniform(mask_key, shape) < prob
    u = jax.random.uniform(delta_key, shape)

    delta = jnp.where(
        u < 0.5,
        jnp.power(2 * u, 1.0 / (eta + 1)) - 1,
        1 - jnp.power(2 * (1 - u), 1.0 / (eta + 1)),
    )

    mutated = population + mask * delta
    return jnp.clip(mutated, 0.0, 1.0)


# =============================================================================
# Visualization
# =============================================================================


def plot_pareto_comparison(
    found_front: Array,
    true_front: Array,
    title: str = "NSGA-II vs True Pareto Front",
) -> str:
    """
    Generate an HTML visualization comparing found vs true Pareto front.

    Args:
        found_front: (N, 2) found Pareto front
        true_front: (K, 2) true Pareto front
        title: Plot title

    Returns:
        HTML string with plotly visualization
    """
    import json

    # Convert to Python lists for JSON
    found_f1 = found_front[:, 0].tolist()
    found_f2 = found_front[:, 1].tolist()
    true_f1 = true_front[:, 0].tolist()
    true_f2 = true_front[:, 1].tolist()

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body>
    <div id="plot" style="width:800px;height:600px;"></div>
    <script>
        var trueTrace = {{
            x: {json.dumps(true_f1)},
            y: {json.dumps(true_f2)},
            mode: 'lines',
            type: 'scatter',
            name: 'True Pareto Front',
            line: {{color: 'blue', width: 2}}
        }};

        var foundTrace = {{
            x: {json.dumps(found_f1)},
            y: {json.dumps(found_f2)},
            mode: 'markers',
            type: 'scatter',
            name: 'Found Solutions',
            marker: {{color: 'red', size: 8}}
        }};

        var layout = {{
            title: '{title}',
            xaxis: {{title: 'f1'}},
            yaxis: {{title: 'f2'}},
            showlegend: true
        }};

        Plotly.newPlot('plot', [trueTrace, foundTrace], layout);
    </script>
</body>
</html>
"""
    return html


# =============================================================================
# Tests
# =============================================================================


class TestZDTProblemDefinitions:
    """Test that ZDT problem functions are correctly implemented."""

    def test_zdt1_on_pareto_optimal(self):
        """ZDT1 with x[1:]=0 should produce Pareto-optimal points."""
        # When x[1:] = 0, g = 1, so f2 = 1 - sqrt(f1)
        n_vars = 30
        for f1_val in [0.0, 0.25, 0.5, 0.75, 1.0]:
            x = jnp.zeros(n_vars).at[0].set(f1_val)
            objs = zdt1(x)

            assert jnp.isclose(objs[0], f1_val), f"f1 should be {f1_val}"
            expected_f2 = 1.0 - jnp.sqrt(f1_val)
            assert jnp.isclose(objs[1], expected_f2, atol=1e-5), (
                f"f2 should be {expected_f2} for f1={f1_val}"
            )

    def test_zdt2_on_pareto_optimal(self):
        """ZDT2 with x[1:]=0 should produce Pareto-optimal points."""
        n_vars = 30
        for f1_val in [0.0, 0.25, 0.5, 0.75, 1.0]:
            x = jnp.zeros(n_vars).at[0].set(f1_val)
            objs = zdt2(x)

            assert jnp.isclose(objs[0], f1_val), f"f1 should be {f1_val}"
            expected_f2 = 1.0 - f1_val**2
            assert jnp.isclose(objs[1], expected_f2, atol=1e-5), (
                f"f2 should be {expected_f2} for f1={f1_val}"
            )

    def test_zdt3_on_pareto_optimal(self):
        """ZDT3 with x[1:]=0 should produce Pareto-optimal points."""
        n_vars = 30
        for f1_val in [0.1, 0.3, 0.5, 0.7, 0.9]:
            x = jnp.zeros(n_vars).at[0].set(f1_val)
            objs = zdt3(x)

            assert jnp.isclose(objs[0], f1_val), f"f1 should be {f1_val}"
            expected_f2 = 1.0 - jnp.sqrt(f1_val) - f1_val * jnp.sin(10.0 * jnp.pi * f1_val)
            assert jnp.isclose(objs[1], expected_f2, atol=1e-5)

    def test_zdt1_dominated_solutions(self):
        """Non-zero x[1:] should produce dominated solutions."""
        n_vars = 30
        x_optimal = jnp.zeros(n_vars).at[0].set(0.5)
        x_dominated = jnp.ones(n_vars) * 0.1
        x_dominated = x_dominated.at[0].set(0.5)

        obj_optimal = zdt1(x_optimal)
        obj_dominated = zdt1(x_dominated)

        # Same f1 but dominated solution has higher f2
        assert jnp.isclose(obj_optimal[0], obj_dominated[0])
        assert obj_dominated[1] > obj_optimal[1]


class TestQualityMetrics:
    """Test quality metric implementations."""

    def test_hypervolume_simple(self):
        """Test hypervolume with simple known case."""
        # Single point at (0.5, 0.5) with ref (1, 1)
        # HV = 0.5 * 0.5 = 0.25
        front = jnp.array([[0.5, 0.5]])
        ref = jnp.array([1.0, 1.0])
        hv = hypervolume_2d(front, ref)
        assert jnp.isclose(hv, 0.25, atol=0.01)

    def test_hypervolume_two_points(self):
        """Test hypervolume with two non-dominated points."""
        # Points (0.2, 0.8) and (0.8, 0.2) with ref (1, 1)
        front = jnp.array([[0.2, 0.8], [0.8, 0.2]])
        ref = jnp.array([1.0, 1.0])
        hv = hypervolume_2d(front, ref)

        # Sweep line calculation (sorted by f1):
        # Point 1 at x=0.2: height = 1.0 - 0.8 = 0.2
        # Point 2 at x=0.8: rect (0.8-0.2) * 0.2 = 0.12, then height becomes 1.0 - 0.2 = 0.8
        # Final rect: (1.0-0.8) * 0.8 = 0.16
        # Total = 0.12 + 0.16 = 0.28
        assert jnp.isclose(hv, 0.28, atol=0.01), f"Expected HV ~0.28, got {hv}"

    def test_hypervolume_empty(self):
        """Hypervolume of empty front is 0."""
        front = jnp.zeros((0, 2))
        ref = jnp.array([1.0, 1.0])
        hv = hypervolume_2d(front, ref)
        assert hv == 0.0

    def test_igd_perfect(self):
        """IGD is 0 when found front matches true front exactly."""
        true_front = jnp.array([[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]])
        found_front = true_front.copy()
        igd = inverted_generational_distance(found_front, true_front)
        assert jnp.isclose(igd, 0.0, atol=1e-6)

    def test_igd_larger_for_worse_front(self):
        """IGD increases when found front is further from true front."""
        true_front = jnp.array([[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]])

        # Good found front (close to true)
        found_good = jnp.array([[0.1, 0.95], [0.5, 0.55], [0.95, 0.1]])

        # Bad found front (far from true)
        found_bad = jnp.array([[0.5, 0.9], [0.6, 0.7], [0.9, 0.6]])

        igd_good = inverted_generational_distance(found_good, true_front)
        igd_bad = inverted_generational_distance(found_bad, true_front)

        assert igd_good < igd_bad

    def test_spacing_uniform(self):
        """Uniformly spaced points should have low spacing metric."""
        # Points evenly spaced on a line
        front = jnp.array([[0.0, 1.0], [0.25, 0.75], [0.5, 0.5], [0.75, 0.25], [1.0, 0.0]])
        sp = spacing_metric(front)
        assert sp < 0.1, f"Expected low spacing for uniform front, got {sp}"

    def test_spacing_non_uniform(self):
        """Non-uniformly spaced points should have higher spacing metric than uniform."""
        # Clustered points
        front_nonuniform = jnp.array(
            [[0.0, 1.0], [0.01, 0.99], [0.02, 0.98], [0.9, 0.1], [1.0, 0.0]]
        )
        sp_nonuniform = spacing_metric(front_nonuniform)

        # Uniformly spaced points for comparison
        front_uniform = jnp.array([[0.0, 1.0], [0.25, 0.75], [0.5, 0.5], [0.75, 0.25], [1.0, 0.0]])
        sp_uniform = spacing_metric(front_uniform)

        # Non-uniform should have higher spacing than uniform
        assert sp_nonuniform > sp_uniform, (
            f"Non-uniform spacing {sp_nonuniform:.4f} should be > uniform {sp_uniform:.4f}"
        )


class TestNSGAOnZDT:
    """Test NSGA-II correctness on ZDT benchmark problems."""

    @pytest.mark.slow
    def test_nsga2_zdt1_hypervolume(self):
        """NSGA-II should achieve >60% of optimal hypervolume on ZDT1.

        Note: ZDT problems require many generations (~200-500) to converge well.
        We use fewer variables and more generations to make the test feasible.
        """
        true_front = true_pareto_front_zdt1(100)
        ref_point = jnp.array([1.1, 1.1])

        # Calculate optimal hypervolume
        optimal_hv = hypervolume_2d(true_front, ref_point)

        # Run NSGA-II with tuned parameters
        # Use fewer variables for faster convergence
        result = run_nsga_on_zdt(
            zdt1,
            true_front,
            n_vars=10,  # Fewer variables = easier optimization
            pop_size=100,
            generations=200,  # More generations needed for convergence
            reference_point=ref_point,
            mutation_prob=0.1,  # Higher mutation for exploration
            seed=42,
        )

        # Should achieve >60% of optimal (60% is reasonable for limited gens)
        hv_ratio = result.hypervolume / optimal_hv
        assert hv_ratio > 0.60, (
            f"HV ratio {hv_ratio:.3f} < 0.60. HV={result.hypervolume:.4f}, Optimal={optimal_hv:.4f}"
        )

    @pytest.mark.slow
    def test_nsga2_zdt2_hypervolume(self):
        """NSGA-II should achieve >60% of optimal hypervolume on ZDT2."""
        true_front = true_pareto_front_zdt2(100)
        ref_point = jnp.array([1.1, 1.1])

        optimal_hv = hypervolume_2d(true_front, ref_point)

        result = run_nsga_on_zdt(
            zdt2,
            true_front,
            n_vars=10,
            pop_size=100,
            generations=200,
            reference_point=ref_point,
            mutation_prob=0.1,
            seed=42,
        )

        hv_ratio = result.hypervolume / optimal_hv
        assert hv_ratio > 0.60, (
            f"HV ratio {hv_ratio:.3f} < 0.60. HV={result.hypervolume:.4f}, Optimal={optimal_hv:.4f}"
        )

    @pytest.mark.slow
    def test_nsga2_zdt3_hypervolume(self):
        """NSGA-II should achieve >50% of optimal hypervolume on ZDT3 (harder due to disconnected front)."""
        true_front = true_pareto_front_zdt3(500)
        ref_point = jnp.array([1.1, 1.1])

        optimal_hv = hypervolume_2d(true_front, ref_point)

        result = run_nsga_on_zdt(
            zdt3,
            true_front,
            n_vars=10,
            pop_size=100,
            generations=250,  # More generations for disconnected front
            reference_point=ref_point,
            mutation_prob=0.1,
            seed=42,
        )

        # ZDT3 is harder, accept 50%
        hv_ratio = result.hypervolume / optimal_hv
        assert hv_ratio > 0.50, (
            f"HV ratio {hv_ratio:.3f} < 0.50. HV={result.hypervolume:.4f}, Optimal={optimal_hv:.4f}"
        )

    @pytest.mark.slow
    def test_nsga2_convergence_monotonic(self):
        """Hypervolume should generally increase over generations."""
        true_front = true_pareto_front_zdt1(100)
        # Use generous ref point so HV > 0 even early
        ref_point = jnp.array([1.5, 10.0])

        # Run with different generation counts
        hvs = []
        for gens in [25, 50, 100, 200]:
            result = run_nsga_on_zdt(
                zdt1,
                true_front,
                n_vars=10,  # Fewer vars for faster convergence
                pop_size=50,
                generations=gens,
                reference_point=ref_point,
                mutation_prob=0.1,
                seed=42,
            )
            hvs.append(result.hypervolume)

        # Check monotonic increase (allowing small fluctuations)
        for i in range(1, len(hvs)):
            # Allow 5% regression due to stochasticity
            assert hvs[i] >= hvs[i - 1] * 0.95, (
                f"HV decreased significantly: {hvs[i - 1]:.4f} -> {hvs[i]:.4f} at gens {[25, 50, 100, 200][i]}"
            )

    @pytest.mark.slow
    def test_nsga2_igd_quality(self):
        """NSGA-II should achieve reasonable IGD on ZDT1."""
        true_front = true_pareto_front_zdt1(100)

        result = run_nsga_on_zdt(
            zdt1,
            true_front,
            n_vars=10,
            pop_size=100,
            generations=200,
            mutation_prob=0.1,
            seed=42,
        )

        # IGD < 0.5 is reasonable for limited generations
        assert result.igd < 0.5, f"IGD {result.igd:.4f} > 0.5"

    def test_nsga2_zdt1_quick(self):
        """Quick sanity check that NSGA-II runs without error on ZDT1."""
        true_front = true_pareto_front_zdt1(50)
        # Use a generous reference point since quick runs don't converge well
        ref_point = jnp.array([1.5, 10.0])

        result = run_nsga_on_zdt(
            zdt1,
            true_front,
            n_vars=10,  # Fewer variables
            pop_size=20,  # Small population
            generations=10,  # Few generations
            reference_point=ref_point,
            seed=42,
        )

        # Just verify it runs and produces valid output
        assert result.found_front.shape[1] == 2
        assert len(result.found_front) > 0
        # With generous ref point, should have non-zero HV
        assert result.hypervolume > 0

    def test_nsga2_zdt2_quick(self):
        """Quick sanity check for ZDT2."""
        true_front = true_pareto_front_zdt2(50)
        ref_point = jnp.array([1.5, 10.0])

        result = run_nsga_on_zdt(
            zdt2,
            true_front,
            n_vars=10,
            pop_size=20,
            generations=10,
            reference_point=ref_point,
            seed=42,
        )

        assert result.found_front.shape[1] == 2
        assert len(result.found_front) > 0
        assert result.hypervolume > 0

    def test_nsga2_zdt3_quick(self):
        """Quick sanity check for ZDT3."""
        true_front = true_pareto_front_zdt3(100)
        ref_point = jnp.array([1.5, 10.0])

        result = run_nsga_on_zdt(
            zdt3,
            true_front,
            n_vars=10,
            pop_size=20,
            generations=10,
            reference_point=ref_point,
            seed=42,
        )

        assert result.found_front.shape[1] == 2
        assert len(result.found_front) > 0
        # ZDT3 may have negative f2 values, so HV calculation may differ


class TestTrueParetoFronts:
    """Test true Pareto front generation."""

    def test_zdt1_true_front_shape(self):
        """ZDT1 true front should have correct shape."""
        front = true_pareto_front_zdt1(100)
        assert front.shape == (100, 2)

    def test_zdt1_true_front_bounds(self):
        """ZDT1 true front should be in [0, 1] x [0, 1]."""
        front = true_pareto_front_zdt1(100)
        assert jnp.all(front[:, 0] >= 0) and jnp.all(front[:, 0] <= 1)
        assert jnp.all(front[:, 1] >= 0) and jnp.all(front[:, 1] <= 1)

    def test_zdt2_true_front_shape(self):
        """ZDT2 true front should have correct shape."""
        front = true_pareto_front_zdt2(100)
        assert front.shape == (100, 2)

    def test_zdt3_true_front_is_non_dominated(self):
        """ZDT3 true front points should be non-dominated."""
        front = true_pareto_front_zdt3(200)

        # All points should be in front 0 (non-dominated)
        fronts = fast_non_dominated_sort(front)
        # There may be some numerical issues, but most should be in front 0
        assert len(fronts[0]) == len(front), "All true Pareto front points should be non-dominated"


class TestVisualization:
    """Test visualization utilities."""

    def test_plot_pareto_comparison_generates_html(self):
        """Visualization should generate valid HTML."""
        found = jnp.array([[0.2, 0.8], [0.5, 0.5], [0.8, 0.2]])
        true = true_pareto_front_zdt1(50)

        html = plot_pareto_comparison(found, true, "Test Plot")

        assert "<html>" in html
        assert "Plotly" in html
        assert "True Pareto Front" in html
        assert "Found Solutions" in html
