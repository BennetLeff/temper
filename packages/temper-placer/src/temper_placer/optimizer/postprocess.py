"""
Post-processing utilities for placement optimization.

This module provides post-processing functions to refine placements after
gradient-based optimization:

1. **Grid Snap**: Snap component positions to KiCad placement grid
2. **Discrete Rotation Refinement**: Finalize rotations by trying all options

Post-processing is run after continuous optimization to produce
manufacturing-ready placements that conform to design rules.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.optimizer.legalization import project_to_drc_feasible

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist

logger = logging.getLogger(__name__)


# Default KiCad placement grid (0.5mm)
DEFAULT_GRID_SIZE = 0.5  # mm


@dataclass
class PostProcessConfig:
    """Configuration for post-processing steps."""

    # Grid snap settings
    grid_snap_enabled: bool = True
    grid_size: float = DEFAULT_GRID_SIZE  # mm

    # Legalization settings
    legalization_enabled: bool = True
    legalization_margin: float = 0.5  # mm
    legalization_iterations: int = 100

    # Discrete rotation refinement settings
    rotation_refinement_enabled: bool = True
    rotation_search_type: str = "greedy"  # "greedy", "beam", or "sa"
    beam_width: int = 3  # Only used if beam search
    sa_iterations: int = 200  # Only used if simulated annealing
    sa_initial_temp: float = 1.0
    sa_cooling_rate: float = 0.95
    allow_swaps: bool = True
    allow_jiggles: bool = True

    # Detailed local search settings (greedy refinement)
    local_search_enabled: bool = True
    local_search_iterations: int = 2
    local_search_neighbors: int = 4  # Number of neighbors to try for swaps


@dataclass
class PostProcessResult:
    """Result of post-processing."""

    state: PlacementState
    grid_snapped: bool
    rotations_refined: bool
    overlaps_resolved: int  # Number of overlaps fixed
    legalized: bool = False
    final_loss: float | None = None


def snap_to_grid(
    state: PlacementState,
    grid_size: float = DEFAULT_GRID_SIZE,
) -> PlacementState:
    """
    Snap component positions to placement grid.

    Args:
        state: Current placement state.
        grid_size: Grid spacing in mm (default 0.5mm per KiCad).

    Returns:
        New PlacementState with positions snapped to grid.

    Example:
        >>> state = PlacementState.from_positions(jnp.array([[1.3, 2.7]]))
        >>> snapped = snap_to_grid(state, grid_size=0.5)
        >>> # snapped.positions == [[1.5, 2.5]]
    """
    snapped_positions = jnp.round(state.positions / grid_size) * grid_size
    return PlacementState(
        positions=snapped_positions,
        rotation_logits=state.rotation_logits,
    )


def snap_to_grid_with_overlap_check(
    state: PlacementState,
    grid_size: float = DEFAULT_GRID_SIZE,
    component_sizes: Array | None = None,
    check_overlap_fn: Callable | None = None,
) -> tuple[PlacementState, int]:
    """
    Snap to grid while trying to avoid introducing overlaps.

    For each component, if snapping causes overlap, tries adjacent grid points.

    Args:
        state: Current placement state.
        grid_size: Grid spacing in mm.
        component_sizes: (N, 2) array of component (width, height) for overlap check.
        check_overlap_fn: Optional function(positions, sizes) -> overlap_count.

    Returns:
        Tuple of (snapped_state, num_overlaps_introduced).
    """
    positions = state.positions
    n_components = positions.shape[0]

    # Simple snap if no overlap checking
    if check_overlap_fn is None or component_sizes is None:
        return snap_to_grid(state, grid_size), 0

    # Snap all positions
    snapped = jnp.round(positions / grid_size) * grid_size

    # Check for overlaps and try alternatives
    overlaps_introduced = 0
    final_positions = []

    for i in range(n_components):
        pos = snapped[i]
        # Try snapped position first
        test_positions = snapped.at[i].set(pos)
        if check_overlap_fn(test_positions, component_sizes) == 0:
            final_positions.append(pos)
            continue

        # Try adjacent grid points
        offsets = jnp.array(
            [
                [0, grid_size],
                [0, -grid_size],
                [grid_size, 0],
                [-grid_size, 0],
                [grid_size, grid_size],
                [grid_size, -grid_size],
                [-grid_size, grid_size],
                [-grid_size, -grid_size],
            ]
        )

        found_valid = False
        for offset in offsets:
            alt_pos = pos + offset
            test_positions = snapped.at[i].set(alt_pos)
            if check_overlap_fn(test_positions, component_sizes) == 0:
                final_positions.append(alt_pos)
                found_valid = True
                break

        if not found_valid:
            # Keep original snapped position, count as overlap
            final_positions.append(pos)
            overlaps_introduced += 1

    final_positions = jnp.stack(final_positions)
    return PlacementState(
        positions=final_positions,
        rotation_logits=state.rotation_logits,
    ), overlaps_introduced


def get_rotation_index(rotation_logits: Array) -> Array:
    """
    Get discrete rotation indices from logits (argmax).

    Args:
        rotation_logits: (N, 4) rotation preference logits.

    Returns:
        (N,) array of rotation indices (0=0°, 1=90°, 2=180°, 3=270°).
    """
    return jnp.argmax(rotation_logits, axis=-1)


def rotation_index_to_angle(rotation_idx: int) -> float:
    """Convert rotation index to angle in radians."""
    return float(rotation_idx) * jnp.pi / 2


def set_rotation_index(
    state: PlacementState,
    component_idx: int,
    rotation_idx: int,
) -> PlacementState:
    """
    Set a specific component's rotation to a discrete value.

    Args:
        state: Current placement state.
        component_idx: Index of component to modify.
        rotation_idx: Rotation index (0=0°, 1=90°, 2=180°, 3=270°).

    Returns:
        New PlacementState with updated rotation logits.
    """
    # Create one-hot logits with high confidence for selected rotation
    new_logits = jnp.full((4,), -10.0)  # Low logits for non-selected
    new_logits = new_logits.at[rotation_idx].set(10.0)  # High logit for selected

    updated_logits = state.rotation_logits.at[component_idx].set(new_logits)
    return PlacementState(
        positions=state.positions,
        rotation_logits=updated_logits,
    )


def discrete_rotation_refinement_greedy(
    state: PlacementState,
    loss_fn: Callable[[PlacementState], float],
    fixed_components: list[int] | None = None,
) -> tuple[PlacementState, float]:
    """
    Refine rotations by trying all options for each component (greedy).

    For each non-fixed component, tries all 4 rotations and keeps the best.
    Processes components in order, each choice affecting subsequent decisions.

    Args:
        state: Current placement state with rotation logits from optimization.
        loss_fn: Function that computes total loss for a state.
        fixed_components: List of component indices with fixed rotations.

    Returns:
        Tuple of (refined_state, final_loss).

    Example:
        >>> def loss_fn(state):
        ...     return compute_overlap(state) + compute_wirelength(state)
        >>> refined, loss = discrete_rotation_refinement_greedy(state, loss_fn)
    """
    if fixed_components is None:
        fixed_components = []

    n_components = state.n_components
    current_state = state
    current_loss = loss_fn(current_state)

    logger.debug(f"Starting greedy rotation refinement, initial loss: {current_loss:.4f}")

    for comp_idx in range(n_components):
        if comp_idx in fixed_components:
            continue

        best_rotation = get_rotation_index(current_state.rotation_logits)[comp_idx]
        best_loss = current_loss

        # Try all 4 rotations
        for rot_idx in range(4):
            test_state = set_rotation_index(current_state, comp_idx, rot_idx)
            test_loss = loss_fn(test_state)

            if test_loss < best_loss:
                best_loss = test_loss
                best_rotation = rot_idx

        # Apply best rotation
        if best_rotation != get_rotation_index(current_state.rotation_logits)[comp_idx]:
            current_state = set_rotation_index(current_state, comp_idx, int(best_rotation))
            current_loss = best_loss
            logger.debug(
                f"Component {comp_idx}: changed to rotation {best_rotation}, loss: {best_loss:.4f}"
            )

    logger.debug(f"Greedy refinement complete, final loss: {current_loss:.4f}")
    return current_state, current_loss


def discrete_rotation_refinement_beam(
    state: PlacementState,
    loss_fn: Callable[[PlacementState], float],
    beam_width: int = 3,
    fixed_components: list[int] | None = None,
) -> tuple[PlacementState, float]:
    """
    Refine rotations using beam search over all combinations.

    Maintains top-k candidates at each step, exploring more of the search space
    than greedy but with bounded complexity.

    Args:
        state: Current placement state.
        loss_fn: Function that computes total loss.
        beam_width: Number of candidates to maintain.
        fixed_components: List of component indices with fixed rotations.

    Returns:
        Tuple of (best_state, best_loss).
    """
    if fixed_components is None:
        fixed_components = []

    n_components = state.n_components

    # Initialize beam with current state
    beam: list[tuple[PlacementState, float]] = [(state, loss_fn(state))]

    logger.debug(f"Starting beam search rotation refinement, beam_width={beam_width}")

    for comp_idx in range(n_components):
        if comp_idx in fixed_components:
            continue

        # Expand each candidate in beam
        candidates: list[tuple[PlacementState, float]] = []

        for current_state, _ in beam:
            for rot_idx in range(4):
                test_state = set_rotation_index(current_state, comp_idx, rot_idx)
                test_loss = loss_fn(test_state)
                candidates.append((test_state, test_loss))

        # Keep top beam_width candidates
        candidates.sort(key=lambda x: x[1])
        beam = candidates[:beam_width]

        logger.debug(f"Component {comp_idx}: beam losses = {[f'{loss_val:.4f}' for _, loss_val in beam]}")

    # Return best candidate
    best_state, best_loss = min(beam, key=lambda x: x[1])
    logger.debug(f"Beam search complete, final loss: {best_loss:.4f}")
    return best_state, best_loss


def detailed_local_search(
    state: PlacementState,
    loss_fn: Callable[[PlacementState], float],
    grid_size: float = 0.5,
    iterations: int = 2,
    num_neighbors: int = 4,
    fixed_components: list[int] | None = None,
    allow_swaps: bool = True,
    allow_displacements: bool = True,
) -> tuple[PlacementState, float]:
    """
    Greedy hill-climbing local search for detailed placement refinement.

    Attempts deterministic micro-moves and accepts only those that reduce loss.
    This step helps recover from quantization errors after grid snapping.

    Moves:
    1. Adjacent Swap: Swap component with its nearest neighbors.
    2. Small Displacement: Move +/- 1 grid unit in X and Y.

    Args:
        state: Current placement state.
        loss_fn: Function to evaluate loss.
        grid_size: Placement grid resolution (mm).
        iterations: Number of full passes over all components.
        num_neighbors: Number of nearest neighbors to check for swaps.
        fixed_components: Indices of components to skip.
        allow_swaps: Enable/disable component swaps.
        allow_displacements: Enable/disable grid-unit movements.

    Returns:
        Tuple of (improved_state, final_loss).
    """
    if fixed_components is None:
        fixed_components = []

    n_components = state.n_components
    current_state = state
    current_loss = loss_fn(current_state)

    logger.debug(f"Starting detailed local search, initial loss: {current_loss:.4f}")

    for _iter_idx in range(iterations):
        improved = False

        for i in range(n_components):
            if i in fixed_components:
                continue

            # 1. Try Small Displacements (+/- 1 grid unit)
            if allow_displacements:
                offsets = jnp.array(
                    [[grid_size, 0], [-grid_size, 0], [0, grid_size], [0, -grid_size]]
                )
                for offset in offsets:
                    new_pos = current_state.positions.at[i].add(offset)
                    test_state = PlacementState(new_pos, current_state.rotation_logits)
                    test_loss = loss_fn(test_state)

                    if test_loss < current_loss - 1e-6:
                        current_state = test_state
                        current_loss = test_loss
                        improved = True
                        logger.debug(f"Comp {i} displaced, new loss: {current_loss:.4f}")

            # 2. Try Adjacent Swaps
            if allow_swaps and n_components > 1:
                # Find nearest neighbors by centroid distance
                pos = current_state.positions[i]
                dists = jnp.sum((current_state.positions - pos) ** 2, axis=1)
                # Sort indices by distance, skip self (index 0 is self)
                neighbor_indices = jnp.argsort(dists)[1 : num_neighbors + 1]

                for j in neighbor_indices:
                    j = int(j)
                    if j in fixed_components:
                        continue

                    # Try swap i and j
                    new_pos = current_state.positions
                    pos_i, pos_j = new_pos[i], new_pos[j]
                    new_pos = new_pos.at[i].set(pos_j).at[j].set(pos_i)

                    test_state = PlacementState(new_pos, current_state.rotation_logits)
                    test_loss = loss_fn(test_state)

                    if test_loss < current_loss - 1e-6:
                        current_state = test_state
                        current_loss = test_loss
                        improved = True
                        logger.debug(f"Swapped {i} and {j}, new loss: {current_loss:.4f}")

        if not improved:
            break

    logger.debug(f"Detailed local search complete, final loss: {current_loss:.4f}")
    return current_state, current_loss


def discrete_rotation_refinement_sa(
    state: PlacementState,
    loss_fn: Callable[[PlacementState], float],
    iterations: int = 200,
    initial_temp: float = 1.0,
    cooling_rate: float = 0.95,
    fixed_components: list[int] | None = None,
    seed: int = 42,
    allow_swaps: bool = True,
    allow_jiggles: bool = True,
    grid_size: float = 0.5,
    netlist: Netlist | None = None,
) -> tuple[PlacementState, float]:
    """
    Refine placement using Simulated Annealing (SA) with micro-moves.

    Explores the search space by randomly applying:
    1. Rotation flip
    2. Jiggle (move +/- 1 grid unit)
    3. Swap (swap two components with identical footprints)

    Accepts moves based on the Metropolis criterion.
    """
    if fixed_components is None:
        fixed_components = []

    n_components = state.n_components
    movable = [i for i in range(n_components) if i not in fixed_components]
    if not movable:
        return state, loss_fn(state)

    # Pre-group identical footprints for swapping
    swap_groups = []
    if allow_swaps and netlist:
        from collections import defaultdict
        fp_map = defaultdict(list)
        for i in movable:
            fp_map[netlist.components[i].footprint].append(i)
        swap_groups = [indices for indices in fp_map.values() if len(indices) > 1]

    current_state = state
    current_loss = loss_fn(current_state)
    best_state = current_state
    best_loss = current_loss

    rng_key = jax.random.PRNGKey(seed)
    temp = initial_temp

    logger.debug(f"Starting micro-move SA refinement, iterations={iterations}")

    for _i in range(iterations):
        rng_key, move_key, comp_key, val_key, accept_key = jax.random.split(rng_key, 5)

        # 1. Pick a move type
        # 0: Rotation, 1: Jiggle, 2: Swap
        move_types = [0]
        if allow_jiggles:
            move_types.append(1)
        if allow_swaps and swap_groups:
            move_types.append(2)

        move_type = int(jax.random.choice(move_key, jnp.array(move_types)))
        test_state = current_state

        if move_type == 0:
            # Rotation flip
            comp_idx = int(jax.random.choice(comp_key, jnp.array(movable)))
            new_rot = int(jax.random.randint(val_key, (), 0, 4))
            test_state = set_rotation_index(current_state, comp_idx, new_rot)

        elif move_type == 1:
            # Jiggle
            comp_idx = int(jax.random.choice(comp_key, jnp.array(movable)))
            offset = jax.random.randint(val_key, (2,), -1, 2) * grid_size
            new_pos = current_state.positions.at[comp_idx].add(offset)
            test_state = PlacementState(new_pos, current_state.rotation_logits)

        elif move_type == 2:
            # Swap
            group_idx = int(jax.random.randint(comp_key, (), 0, len(swap_groups)))
            indices = jnp.array(swap_groups[group_idx])
            pair = jax.random.choice(val_key, indices, (2,), replace=False)
            idx1, idx2 = int(pair[0]), int(pair[1])

            new_pos = current_state.positions
            pos1, pos2 = new_pos[idx1], new_pos[idx2]
            new_pos = new_pos.at[idx1].set(pos2).at[idx2].set(pos1)
            test_state = PlacementState(new_pos, current_state.rotation_logits)

        # Metropolis criterion
        test_loss = loss_fn(test_state)
        delta = test_loss - current_loss
        if delta < 0 or jax.random.uniform(accept_key) < jnp.exp(-delta / jnp.maximum(temp, 1e-6)):
            current_state = test_state
            current_loss = test_loss

            if current_loss < best_loss:
                best_state = current_state
                best_loss = current_loss

        # Cool down
        temp *= cooling_rate

    logger.debug(f"Micro-move SA refinement complete, final loss: {best_loss:.4f}")
    return best_state, best_loss


def discrete_rotation_refinement(
    state: PlacementState,
    loss_fn: Callable[[PlacementState], float],
    search_type: str = "greedy",
    beam_width: int = 3,
    sa_iterations: int = 200,
    sa_initial_temp: float = 1.0,
    sa_cooling_rate: float = 0.95,
    fixed_components: list[int] | None = None,
    allow_swaps: bool = True,
    allow_jiggles: bool = True,
    grid_size: float = 0.5,
    netlist: Netlist | None = None,
) -> tuple[PlacementState, float]:
    """
    Refine rotations to discrete values after continuous optimization.

    This is the main entry point for rotation refinement. After gradient-based
    optimization with Gumbel-Softmax, this function converts the soft rotation
    distributions to hard discrete choices by searching for the best combination.

    Args:
        state: PlacementState with soft rotation logits from optimization.
        loss_fn: Function(state) -> loss that evaluates placement quality.
        search_type: "greedy" (fast, O(4N)), "beam" (better, O(4N * beam_width)),
                    or "sa" (Simulated Annealing).
        beam_width: Beam width if using beam search.
        sa_iterations: Number of iterations for SA.
        sa_initial_temp: Initial temperature for SA.
        sa_cooling_rate: Cooling rate for SA.
        fixed_components: Component indices that should not be rotated.
        allow_swaps: Allow swapping identical footprints in SA.
        allow_jiggles: Allow small position adjustments in SA.
        grid_size: Grid size for jiggles.
        netlist: Required for swap validation.

    Returns:
        Tuple of (refined_state, final_loss) with discrete rotation logits.
    """
    if search_type == "beam":
        return discrete_rotation_refinement_beam(state, loss_fn, beam_width, fixed_components)
    elif search_type == "sa":
        return discrete_rotation_refinement_sa(
            state,
            loss_fn,
            iterations=sa_iterations,
            initial_temp=sa_initial_temp,
            cooling_rate=sa_cooling_rate,
            fixed_components=fixed_components,
            allow_swaps=allow_swaps,
            allow_jiggles=allow_jiggles,
            grid_size=grid_size,
            netlist=netlist,
        )
    else:
        return discrete_rotation_refinement_greedy(state, loss_fn, fixed_components)


def postprocess(
    state: PlacementState,
    loss_fn: Callable[[PlacementState], float],
    config: PostProcessConfig | None = None,
    component_sizes: Array | None = None,  # noqa: ARG001
    fixed_components: list[int] | None = None,
    context: LossContext | None = None,
    netlist: Netlist | None = None,
) -> PostProcessResult:
    """
    Run full post-processing pipeline on optimized placement.

    Applies in order:
    1. Grid snap (align positions to placement grid)
    2. Legalization (resolve hard overlaps/boundaries)
    3. Discrete rotation refinement (finalize rotation choices)

    Args:
        state: PlacementState from optimization.
        loss_fn: Loss function for evaluating placement quality.
        config: Post-processing configuration.
        component_sizes: (N, 2) array of component sizes for overlap checking.
        fixed_components: Component indices that should not be modified.
        context: LossContext for legalization rules.
        netlist: Netlist for component-level refinement (swaps).

    Returns:
        PostProcessResult with refined state and metadata.
    """
    if config is None:
        config = PostProcessConfig()

    current_state = state
    grid_snapped = False
    legalized = False
    rotations_refined = False
    overlaps_fixed = 0

    logger.info("Starting post-processing pipeline")

    # Step 1: Grid snap
    if config.grid_snap_enabled:
        logger.info(f"Snapping to {config.grid_size}mm grid")
        current_state = snap_to_grid(current_state, config.grid_size)
        grid_snapped = True

    # Step 2: Legalization
    if config.legalization_enabled and context is not None:
        logger.info(f"Running DRC-feasible projection (legalization) with {config.legalization_iterations} iterations")
        current_state = project_to_drc_feasible(
            current_state,
            context,
            margin_mm=config.legalization_margin,
            max_iterations=config.legalization_iterations,
        )
        legalized = True

    # Step 3: Discrete rotation refinement
    if config.rotation_refinement_enabled:
        logger.info(f"Refining rotations using {config.rotation_search_type} search")
        current_state, final_loss = discrete_rotation_refinement(
            current_state,
            loss_fn,
            search_type=config.rotation_search_type,
            beam_width=config.beam_width,
            sa_iterations=config.sa_iterations,
            sa_initial_temp=config.sa_initial_temp,
            sa_cooling_rate=config.sa_cooling_rate,
            fixed_components=fixed_components,
            allow_swaps=config.allow_swaps,
            allow_jiggles=config.allow_jiggles,
            grid_size=config.grid_size,
            netlist=netlist,
        )
        rotations_refined = True
    else:
        final_loss = loss_fn(current_state)

    # Step 4: Detailed local search (Greedy hill climbing)
    if config.local_search_enabled:
        logger.info("Running detailed local search refinement")
        current_state, final_loss = detailed_local_search(
            current_state,
            loss_fn,
            grid_size=config.grid_size,
            iterations=config.local_search_iterations,
            num_neighbors=config.local_search_neighbors,
            fixed_components=fixed_components,
            allow_swaps=config.allow_swaps,
        )

    logger.info(f"Post-processing complete, final loss: {final_loss:.4f}")

    return PostProcessResult(
        state=current_state,
        grid_snapped=grid_snapped,
        legalized=legalized,
        rotations_refined=rotations_refined,
        overlaps_resolved=overlaps_fixed,
        final_loss=final_loss,
    )


def finalize_placement(
    state: PlacementState,
    loss_fn: Callable[[PlacementState], float],
    grid_size: float = DEFAULT_GRID_SIZE,
    fixed_components: list[int] | None = None,
) -> tuple[Array, Array, float | None]:
    """
    Convenience function to get final positions and rotation indices.

    Applies grid snap and rotation refinement, then returns arrays
    ready for export to KiCad.

    Args:
        state: Optimized PlacementState.
        loss_fn: Loss function for rotation refinement.
        grid_size: Placement grid size in mm.
        fixed_components: Components with fixed positions/rotations.

    Returns:
        Tuple of:
        - positions: (N, 2) grid-snapped positions
        - rotation_indices: (N,) rotation indices (0-3)
        - final_loss: Final placement loss
    """
    result = postprocess(
        state,
        loss_fn,
        config=PostProcessConfig(
            grid_size=grid_size,
            rotation_search_type="greedy",
        ),
        fixed_components=fixed_components,
    )

    positions = result.state.positions
    rotation_indices = get_rotation_index(result.state.rotation_logits)

    return positions, rotation_indices, result.final_loss
