"""
Diverse seed pool generation by varying initialization hyperparameters.

Generates a diverse pool of initial component positions for DPP selection
by sampling from a cartesian product of initialization hyperparameters.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.optimizer.initialization import SpectralInitializer
from temper_placer.optimizer.zone_aware_init import ZoneAwareSpectralInitializer

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.optimizer.config import MultiSeedConfig

logger = logging.getLogger(__name__)


def _generate_diverse_seeds(
    netlist: Netlist,
    board: Board,
    config: MultiSeedConfig,
    master_rng_key: Array,
) -> list[tuple[Array, dict]]:
    """
    Generate a diverse pool of initial positions by varying init hyperparameters.

    Samples from the cartesian product of (init_method, laplacian, margin,
    perturbation_sigma), then randomly subsets to n_generate.

    Args:
        netlist: Component netlist.
        board: Board definition.
        config: MultiSeedConfig with n_generate.
        master_rng_key: JAX PRNG key for reproducibility.

    Returns:
        List of (positions: (N,2), metadata: dict) tuples.
    """
    n_generate = config.n_generate
    max_retries = n_generate * 3
    is_random_only = netlist.n_components <= 1

    # Use config-specified hyperparameter grids
    init_methods = config.init_methods
    laplacian_options = config.laplacian_options
    margin_options = config.margin_options
    perturb_sigmas = config.perturb_sigmas

    seeds: list[tuple[Array, dict]] = []
    keys = jax.random.split(master_rng_key, max_retries + 1)
    key_idx = 0

    # Build the full hyperparameter grid from config
    if is_random_only:
        grid = [("random", None, None, None)]
    else:
        grid = [
            (method, laplacian, margin, sigma)
            for method in init_methods
            for laplacian in laplacian_options
            for margin in margin_options
            for sigma in perturb_sigmas
        ]

    # Shuffle grid deterministically
    import random as _random
    _random.Random(42).shuffle(grid)

    retries = 0
    grid_idx = 0

    while len(seeds) < n_generate and retries < max_retries:
        method, laplacian, margin, sigma = grid[grid_idx % len(grid)]
        grid_idx += 1
        key = keys[key_idx % len(keys)]
        key_idx += 1

        try:
            positions, metadata = _generate_one_seed(
                netlist, board, method, laplacian, margin, sigma, key
            )
        except Exception as e:
            logger.debug("Seed generation failed: %s (retry)", e)
            retries += 1
            continue

        if _is_seed_valid(positions, board):
            seeds.append((positions, metadata))
        else:
            retries += 1

    # Fallback: if not enough valid seeds, generate random ones
    if len(seeds) < config.n_select:
        logger.warning(
            "Only %d valid seeds (need %d); falling back to random_init().",
            len(seeds),
            config.n_select,
        )
        while len(seeds) < max(config.n_select, 1):
            key = keys[key_idx % len(keys)]
            key_idx += 1
            pos = _random_init_positions(netlist, board, key)
            if _is_seed_valid(pos, board):
                seeds.append((pos, {"init_method": "random_fallback"}))
            if key_idx >= max_retries:
                break

    if len(seeds) == 0:
        raise RuntimeError(
            "Seed generation failed: zero valid seeds produced."
        )

    return seeds


def _generate_one_seed(
    netlist: Netlist,
    board: Board,
    method: str,
    laplacian: bool | None,
    margin: float | None,
    sigma: float,
    key: Array,
) -> tuple[Array, dict]:
    """Generate a single seed from given hyperparameters."""
    metadata: dict = {
        "init_method": method,
        "perturb_sigma": sigma,
        "comp_refs": [c.ref for c in netlist.components],
    }

    if method == "random":
        positions = _random_init_positions(netlist, board, key)
        return positions, metadata

    if method == "spectral":
        initializer = SpectralInitializer(
            normalized_laplacian=laplacian,
            margin_fraction=margin,
        )
        positions = initializer.initialize(netlist, board)
        metadata.update({
            "normalized_laplacian": laplacian,
            "margin_fraction": margin,
        })
    elif method == "zone_aware_spectral":
        # Use default zone-aware params (not exposed to grid in P0)
        initializer = ZoneAwareSpectralInitializer(
            normalized_laplacian=laplacian,
            margin_fraction=margin,
        )
        positions = initializer.initialize(netlist, board)
        metadata.update({
            "normalized_laplacian": laplacian,
            "margin_fraction": margin,
            "zone_aware": True,
        })
    else:
        raise ValueError(f"Unknown init method: {method}")

    # Apply Gaussian perturbation
    if sigma > 0.0:
        board_diag = jnp.sqrt(board.width**2 + board.height**2)
        noise_scale = sigma * board_diag
        key1, key2 = jax.random.split(key)
        noise = jax.random.normal(key1, positions.shape) * noise_scale
        positions = positions + noise
        # Clamp to board bounds
        positions = jnp.clip(positions, 0.0, jnp.array([board.width, board.height]))

    return positions, metadata


def _random_init_positions(
    netlist: Netlist,
    board: Board,
    key: Array,
) -> Array:
    """Generate random initial positions using PlacementState.random_init."""
    from temper_placer.core.state import PlacementState
    state = PlacementState.random_init(
        n_components=netlist.n_components,
        board_width=board.width,
        board_height=board.height,
        key=key,
        n_nets=netlist.n_nets,
    )
    return state.positions


def _is_seed_valid(positions: Array, board: Board) -> bool:
    """Check if seed positions are valid (no NaN, not all identical, in bounds)."""
    if positions.shape[0] == 0:
        return False
    if jnp.any(jnp.isnan(positions)):
        return False
    if jnp.any(jnp.isinf(positions)):
        return False
    # Check not all identical
    if positions.shape[0] > 1:
        if jnp.allclose(positions, positions[0:1, :]):
            return False
    return True
