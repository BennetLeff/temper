"""
NSGA-II (Non-dominated Sorting Genetic Algorithm II) implementation.

Used for multi-objective placement optimization, allowing the exploration
of Pareto-optimal trade-offs between wirelength, thermal, and design rules.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jax
import jax.numpy as jnp
import numpy as np
from jax import Array

logger = logging.getLogger(__name__)


def fast_non_dominated_sort(objectives: Array) -> list[list[int]]:
    """
    Standard NSGA-II fast non-dominated sorting algorithm.

    Args:
        objectives: (N, M) array where N is population size and M is number of objectives.
            Assumes all objectives are to be minimized.

    Returns:
        List of fronts, where each front is a list of population indices.
    """
    n = objectives.shape[0]

    # domination_count[i] = number of individuals that dominate i
    domination_count = jnp.zeros(n, dtype=jnp.int32)
    # dominated_set[i] = list of indices that i dominates
    dominated_set = [[] for _ in range(n)]

    fronts = [[]]

    for i in range(n):
        for j in range(i + 1, n):
            # Check if i dominates j
            # i dominates j if:
            # 1. i is not worse than j in all objectives
            # 2. i is strictly better than j in at least one objective

            diff = objectives[i] - objectives[j]
            i_dominates_j = jnp.all(diff <= 0) and jnp.any(diff < 0)
            j_dominates_i = jnp.all(diff >= 0) and jnp.any(diff > 0)

            if i_dominates_j:
                dominated_set[i].append(j)
                domination_count = domination_count.at[j].add(1)
            elif j_dominates_i:
                dominated_set[j].append(i)
                domination_count = domination_count.at[i].add(1)

        if domination_count[i] == 0:
            fronts[0].append(i)

    curr_front = 0
    while fronts[curr_front]:
        next_front = []
        for i in fronts[curr_front]:
            for j in dominated_set[i]:
                domination_count = domination_count.at[j].add(-1)
                if domination_count[j] == 0:
                    next_front.append(j)

        curr_front += 1
        if not next_front:
            break
        fronts.append(next_front)

    return fronts


def calculate_crowding_distance(objectives: Array) -> Array:
    """
    Calculate crowding distance for individuals in objective space.

    Helps maintain diversity in the population by preferring individuals
    in less-crowded regions.

    Args:
        objectives: (N, M) array of objective values.

    Returns:
        (N,) array of crowding distances.
    """
    n, m = objectives.shape
    if n == 0:
        return jnp.array([])
    if n <= 2:
        return jnp.full(n, float("inf"))

    distances = jnp.zeros(n)

    for obj_idx in range(m):
        # Sort indices by current objective
        sorted_indices = jnp.argsort(objectives[:, obj_idx])

        # Extremes get infinite distance
        distances = distances.at[sorted_indices[0]].set(float("inf"))
        distances = distances.at[sorted_indices[-1]].set(float("inf"))

        # Range of the objective
        obj_range = objectives[sorted_indices[-1], obj_idx] - objectives[sorted_indices[0], obj_idx]
        if obj_range < 1e-6:
            continue

        # Calculate normalized distance for intermediate points
        for i in range(1, n - 1):
            dist = (
                objectives[sorted_indices[i + 1], obj_idx]
                - objectives[sorted_indices[i - 1], obj_idx]
            ) / obj_range
            distances = distances.at[sorted_indices[i]].add(dist)

    return distances


def evaluate_population(
    population_positions: Array,
    population_rotations: Array,
    objectives: list[Callable],
    context: Any,
    epoch: int,
    total_epochs: int,
) -> Array:
    """
    Evaluate all individuals in the population against multiple objectives.

    Args:
        population_positions: (PopSize, N, 2) positions.
        population_rotations: (PopSize, N, 4) rotations.
        objectives: List of objective functions.
        context: LossContext.
        epoch: Current generation/epoch.
        total_epochs: Total generations.

    Returns:
        (PopSize, M) array of objective values.
    """

    def eval_individual(pos, rot):
        vals = []
        for obj in objectives:
            res = obj(pos, rot, context, epoch, total_epochs)
            vals.append(res.value)
        return jnp.array(vals)

    return jax.vmap(eval_individual)(population_positions, population_rotations)


def tournament_selection(
    ranks: Array, distances: Array, key: Array, num_selected: int, tournament_size: int = 2
) -> Array:
    """
    Perform tournament selection based on NSGA-II crowded-comparison operator.

    Individuals are compared first by rank (lower is better),
    then by crowding distance (higher is better).

    Returns:
        Indices of selected individuals.
    """
    pop_size = ranks.shape[0]

    def select_one(k):
        # Pick random candidates
        candidates = jax.random.choice(k, jnp.arange(pop_size), (tournament_size,), replace=False)
        c_ranks = ranks[candidates]
        c_dists = distances[candidates]

        # Winner is the one with lowest rank
        # If ranks are tied, winner is the one with largest distance
        best_idx = 0
        for i in range(1, tournament_size):
            is_better = (c_ranks[i] < c_ranks[best_idx]) | (
                (c_ranks[i] == c_ranks[best_idx]) & (c_dists[i] > c_dists[best_idx])
            )
            best_idx = jnp.where(is_better, i, best_idx)

        return candidates[best_idx]

    keys = jax.random.split(key, num_selected)
    return jax.vmap(select_one)(keys)


def crossover_blx_alpha(parent1: Array, parent2: Array, key: Array, alpha: float = 0.5) -> Array:
    """
    Blend Crossover (BLX-alpha) for continuous variables.
    """
    c_min = jnp.minimum(parent1, parent2)
    c_max = jnp.maximum(parent1, parent2)
    range_val = c_max - c_min

    low = c_min - alpha * range_val
    high = c_max + alpha * range_val

    return jax.random.uniform(key, parent1.shape, minval=low, maxval=high)


def mutate_gaussian(positions: Array, key: Array, sigma: float = 1.0, rate: float = 0.1) -> Array:
    """
    Gaussian mutation for positions.
    """
    key_mask, key_noise = jax.random.split(key)
    mask = jax.random.uniform(key_mask, positions.shape[:1]) < rate
    noise = jax.random.normal(key_noise, positions.shape) * sigma

    return jnp.where(mask[:, None], positions + noise, positions)


@dataclass
class NSGAResult:
    """Result of NSGA-II optimization."""

    population_positions: Array
    population_rotations: Array
    objectives: Array
    fronts: list[list[int]]
    best_indices: list[int]  # Indices of individuals in the first front


class NSGAOptimizer:
    """Multi-objective optimizer using NSGA-II."""

    def __init__(
        self,
        population_size: int = 50,
        mutation_rate: float = 0.1,
        mutation_sigma: float = 2.0,
        crossover_alpha: float = 0.5,
    ):
        self.pop_size = population_size
        self.mutation_rate = mutation_rate
        self.mutation_sigma = mutation_sigma
        self.crossover_alpha = crossover_alpha

    def evolve(
        self,
        netlist: Any,
        board: Any,
        objectives: list[Callable],
        context: Any,
        generations: int = 100,
        initial_state: Any | None = None,
        seed: int = 42,
    ) -> NSGAResult:
        """Run the evolutionary process."""
        rng_key = jax.random.PRNGKey(seed)
        n_comps = netlist.n_components

        # 1. Initialize Population
        rng_key, init_key, init_rot_key = jax.random.split(rng_key, 3)
        if initial_state:
            # Perturb initial state to create population
            pop_pos = jnp.repeat(initial_state.positions[None, :, :], self.pop_size, axis=0)
            noise = jax.random.normal(init_key, pop_pos.shape) * 5.0
            pop_pos = pop_pos + noise
            pop_rot = jnp.repeat(initial_state.rotation_logits[None, :, :], self.pop_size, axis=0)
            rot_noise = jax.random.normal(init_rot_key, pop_rot.shape) * 0.5
            pop_rot = pop_rot + rot_noise
        else:
            # Random initialization
            def get_random_state(k):
                from temper_placer.core.state import PlacementState

                state = PlacementState.random_init(n_comps, board.width, board.height, k)
                return state.positions, state.rotation_logits

            keys = jax.random.split(init_key, self.pop_size)
            pop_pos, pop_rot = jax.vmap(get_random_state)(keys)

        # 2. Main Evolution Loop
        for gen in range(generations):
            # Evaluate
            obj_vals = evaluate_population(pop_pos, pop_rot, objectives, context, gen, generations)

            # Non-dominated sort
            fronts = fast_non_dominated_sort(obj_vals)
            distances = calculate_crowding_distance(obj_vals)

            # 3. Create Offspring
            rng_key, select_key, cross_key, mutate_key = jax.random.split(rng_key, 4)

            # Tournament selection for parents
            parent_indices = tournament_selection(
                jnp.array(
                    [
                        next(i for i, f in enumerate(fronts) if idx in f)
                        for idx in range(self.pop_size)
                    ]
                ),
                distances,
                select_key,
                self.pop_size,
            )

            # Crossover (pairs of parents)
            p1_idx = parent_indices[::2]
            p2_idx = parent_indices[1::2]
            cross_keys = jax.random.split(cross_key, len(p1_idx))

            child_pos = jax.vmap(
                lambda p1, p2, k: crossover_blx_alpha(p1, p2, k, self.crossover_alpha)
            )(pop_pos[p1_idx], pop_pos[p2_idx], cross_keys)
            child_rot = jax.vmap(
                lambda p1, p2, k: crossover_blx_alpha(p1, p2, k, self.crossover_alpha)
            )(pop_rot[p1_idx], pop_rot[p2_idx], cross_keys)

            # Mutation
            mutate_keys_pos, mutate_keys_rot = jax.random.split(mutate_key, 2)
            mutate_keys_pos = jax.random.split(mutate_keys_pos, self.pop_size // 2)
            mutate_keys_rot = jax.random.split(mutate_keys_rot, self.pop_size // 2)
            child_pos = jax.vmap(
                lambda p, k: mutate_gaussian(p, k, self.mutation_sigma, self.mutation_rate)
            )(child_pos, mutate_keys_pos)
            child_rot = jax.vmap(lambda p, k: mutate_gaussian(p, k, 0.3, self.mutation_rate))(
                child_rot, mutate_keys_rot
            )

            # Re-evaluate children
            child_obj_vals = evaluate_population(
                child_pos, child_rot, objectives, context, gen, generations
            )

            combined_pos = jnp.concatenate([pop_pos, child_pos], axis=0)
            combined_rot = jnp.concatenate([pop_rot, child_rot], axis=0)
            combined_obj = jnp.concatenate([obj_vals, child_obj_vals], axis=0)

            # Sort combined population
            combined_fronts = fast_non_dominated_sort(combined_obj)
            combined_distances = calculate_crowding_distance(combined_obj)

            # Pick best N
            next_indices = []
            for front in combined_fronts:
                if len(next_indices) + len(front) <= self.pop_size:
                    next_indices.extend(front)
                else:
                    # Fill remaining from current front using crowding distance
                    needed = self.pop_size - len(next_indices)
                    front_indices = jnp.array(front)
                    front_dists = combined_distances[front_indices]
                    # Sort by distance descending
                    sorted_front = front_indices[jnp.argsort(-front_dists)]
                    next_indices.extend(sorted_front[:needed].tolist())
                    break

            pop_pos = combined_pos[jnp.array(next_indices)]
            pop_rot = combined_rot[jnp.array(next_indices)]

            logger.info(f"Generation {gen}: Front 0 size = {len(combined_fronts[0])}")

        # Final evaluation and sort
        final_obj = evaluate_population(
            pop_pos, pop_rot, objectives, context, generations, generations
        )
        final_fronts = fast_non_dominated_sort(final_obj)

        return NSGAResult(
            population_positions=pop_pos,
            population_rotations=pop_rot,
            objectives=final_obj,
            fronts=final_fronts,
            best_indices=final_fronts[0],
        )


def select_knee_point(objectives: Array, weights: Array | None = None) -> int:
    """
    Select the knee point from a Pareto front using normalized ideal distance.

    Args:
        objectives: (N, M) array of objective values for the Pareto front.
        weights: (M,) array of weights for each objective, used to steer selection.

    Returns:
        Index of the knee point in the input array.
    """
    if objectives.shape[0] == 0:
        return 0

    # 1. Normalize objectives to [0, 1]
    f_min = jnp.min(objectives, axis=0)
    f_max = jnp.max(objectives, axis=0)

    # Avoid division by zero for fixed objectives
    f_range = jnp.maximum(f_max - f_min, 1e-6)

    norm_objs = (objectives - f_min) / f_range

    # 2. Apply weights if provided
    if weights is not None:
        norm_objs = norm_objs * weights

    # 3. Heuristic: point that minimizes L2 norm of (weighted) normalized objectives
    # This is the point closest to the ideal point in normalized space.
    scores = jnp.linalg.norm(norm_objs, axis=1)

    return int(jnp.argmin(scores))


def plot_pareto_front(result: NSGAResult, objective_names: list[str]):
    """
    Visualize the Pareto frontier using Plotly.
    """
    import pandas as pd
    import plotly.express as px

    # Extract individuals in the first front
    indices = jnp.array(result.best_indices)
    vals = result.objectives[indices]

    df = pd.DataFrame(vals, columns=objective_names)
    df["id"] = [f"Sol {i}" for i in range(len(indices))]

    if len(objective_names) == 2:
        fig = px.scatter(
            df,
            x=objective_names[0],
            y=objective_names[1],
            hover_name="id",
            title="NSGA-II Pareto Frontier",
        )
    elif len(objective_names) == 3:
        fig = px.scatter_3d(
            df,
            x=objective_names[0],
            y=objective_names[1],
            z=objective_names[2],
            hover_name="id",
            title="NSGA-II Pareto Frontier",
        )
    else:
        # High dimensional: use parallel coordinates
        fig = px.parallel_coordinates(df, color=objective_names[0])

    return fig
