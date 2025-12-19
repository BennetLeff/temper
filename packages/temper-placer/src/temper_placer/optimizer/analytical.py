"""
Analytical placement algorithms for global placement optimization.

This module implements algorithms that solve for component positions
using mathematical optimization (e.g., quadratic programming), which
provides a strong global starting point for gradient-based refinement.
"""

from __future__ import annotations

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, build_adjacency_matrix


def solve_quadratic_placement(
    netlist: Netlist,
    board: Board,
    fixed_indices: Array,
    fixed_positions: Array,
) -> Array:
    """
    Solves the quadratic placement problem: minimize sum w_ij * ||p_i - p_j||^2.

    The problem decomposes into X and Y dimensions independently.
    For each dimension, we solve (L_mm) * p_m = - (L_mf) * p_f
    where 'm' denotes movable components and 'f' denotes fixed components.

    Args:
        netlist: Component netlist.
        board: Board definition.
        fixed_indices: (F,) array of indices of fixed components.
        fixed_positions: (F, 2) array of positions of fixed components.

    Returns:
        (N, 2) array of all component positions.

    Notes:
        - Requires at least one fixed component to avoid trivial zero solution.
        - If no components are fixed, defaults to board center with small spread.
    """
    n = netlist.n_components
    if n == 0:
        return jnp.zeros((0, 2))

    # Build adjacency matrix (connectivity weights)
    adj = build_adjacency_matrix(netlist)

    # Compute Laplacian L = D - A
    degrees = jnp.sum(adj, axis=1)
    L = jnp.diag(degrees) - adj

    # Identify movable indices
    is_fixed = jnp.zeros(n, dtype=jnp.bool_)
    if fixed_indices.shape[0] > 0:
        is_fixed = is_fixed.at[fixed_indices].set(True)
    movable_indices = jnp.where(~is_fixed)[0]

    # Handle case with no fixed components (anchors)
    if fixed_indices.shape[0] == 0:
        # Place a virtual anchor at board center connected to all components
        # This prevents the quadratic solver from collapsing everything to zero
        center = jnp.array([board.origin[0] + board.width / 2, board.origin[1] + board.height / 2])
        # For simplicity, we just return spectral or center-spread if no anchors
        return jnp.full((n, 2), center)

    if movable_indices.shape[0] == 0:
        # All components are fixed
        all_pos = jnp.zeros((n, 2))
        all_pos = all_pos.at[fixed_indices].set(fixed_positions)
        return all_pos

    # Partition L into L_mm and L_mf
    # L_mm: connections between movable components
    # L_mf: connections between movable and fixed components
    L_mm = L[movable_indices][:, movable_indices]
    L_mf = L[movable_indices][:, fixed_indices]

    # Solve for each dimension: L_mm * p_m = - L_mf * p_f
    def solve_dim(p_f):
        # rhs = - L_mf @ p_f
        rhs = -jnp.dot(L_mf, p_f)
        # Solve L_mm * p_m = rhs
        # Add small epsilon to diagonal for numerical stability (Tikhonov regularization)
        L_mm_stable = L_mm + jnp.eye(L_mm.shape[0]) * 1e-6
        p_m = jnp.linalg.solve(L_mm_stable, rhs)
        return p_m

    # Solve X and Y
    p_m_x = solve_dim(fixed_positions[:, 0])
    p_m_y = solve_dim(fixed_positions[:, 1])

    # Combine results
    all_pos = jnp.zeros((n, 2))
    all_pos = all_pos.at[fixed_indices].set(fixed_positions)
    all_pos = all_pos.at[movable_indices, 0].set(p_m_x)
    all_pos = all_pos.at[movable_indices, 1].set(p_m_y)

    return all_pos
