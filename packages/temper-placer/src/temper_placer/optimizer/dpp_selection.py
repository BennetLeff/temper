"""
DPP (Determinantal Point Process) kernel construction and subset selection.

Implements:
- _dpp_kernel_from_positions: Build similarity kernel from seed positions.
- _dpp_select: Greedy DPP MAP inference for diverse subset selection.
- _farthest_point_sampling: Fallback for ill-conditioned kernels.
"""

from __future__ import annotations

import logging

import jax.numpy as jnp
from jax import Array

logger = logging.getLogger(__name__)


def _dpp_kernel_from_positions(
    seeds: list[tuple[Array, dict]],
) -> tuple[Array, float]:
    """
    Build DPP kernel L from seed position vectors.

    Sorts each seed's components by reference ID from metadata (if available),
    computes pairwise RMS distances, and applies an RBF transformation
    with sigma set to the median pairwise distance.

    Each seed's metadata may contain a "comp_refs" key with a list of component
    reference IDs in the same order as the positions rows. When present, each
    seed is independently sorted by those reference IDs to ensure
    permutation-invariant kernel values.

    Args:
        seeds: List of (positions: (N,2), metadata: dict) tuples.

    Returns:
        Tuple of (L, condition_number) where:
            L[i,j] = exp(-RMS(x_i - x_j)^2 / (2 * sigma^2))
            sigma = median(pairwise RMS distances)
    """
    n = len(seeds)
    if n == 0:
        return jnp.eye(0), 0.0

    if n == 1:
        return jnp.eye(1), 1.0

    # Flatten each seed's positions to a 1D vector, sorting by ref ID if available
    vectors = []
    for positions, md in seeds:
        comp_refs = md.get("comp_refs", None)
        if comp_refs is not None:
            ref_ids = [(r, i) for i, r in enumerate(comp_refs)]
            ref_ids.sort()
            sorted_idx = jnp.array([i for _, i in ref_ids], dtype=jnp.int32)
            positions = positions[sorted_idx]
        vectors.append(positions.ravel())

    vec_matrix = jnp.stack(vectors, axis=0)  # (n, N*2)

    # Compute pairwise RMS distances
    diff = vec_matrix[:, None, :] - vec_matrix[None, :, :]  # (n, n, N*2)
    rms_dist = jnp.sqrt(jnp.mean(diff**2, axis=-1))  # (n, n)

    # Sigma = median of all pairwise distances
    upper_tri = jnp.triu(rms_dist, k=1)
    n_pairs = n * (n - 1) // 2
    if n_pairs == 0:
        return jnp.eye(n), 1.0

    flat = upper_tri.ravel()
    nonzero = flat[flat > 0.0]
    if len(nonzero) == 0:
        sigma = 1e-6
    else:
        sigma = float(jnp.median(nonzero))
    sigma = max(sigma, 1e-10)

    # RBF kernel
    L = jnp.exp(-(rms_dist**2) / (2.0 * sigma**2))

    # Compute condition number
    eigenvalues = jnp.linalg.eigh(L)[0]
    lambda_max = eigenvalues[-1]
    lambda_min = eigenvalues[0]
    if lambda_min <= 0.0:
        condition_number = float("inf")
    else:
        condition_number = float(lambda_max / lambda_min)

    return L, condition_number


def _dpp_select(
    L: Array,
    k: int,
    quality: Array | None = None,
    condition_number: float | None = None,
    seed_vectors: Array | None = None,
) -> list[int]:
    """
    Select k seed indices via greedy DPP MAP inference.

    The DPP probability P(Y) is proportional to det(L_Y). The greedy algorithm
    builds Y incrementally, selecting the seed that maximizes the determinant
    at each step.

    Falls back to farthest-point sampling when the kernel condition number
    exceeds 10^6.

    Args:
        L: (n, n) kernel similarity matrix.
        k: Number of seeds to select.
        quality: Optional (n,) quality vector for quality-diversity decomposition.
            If provided, L_ij = q_i * S_ij * q_j.
        condition_number: Pre-computed condition number of L.
        seed_vectors: Optional (n, d) seed vectors for farthest-point fallback.

    Returns:
        List of selected seed indices.
    """
    n = L.shape[0]
    k = min(k, n)

    # Kernel ill-conditioning fallback
    if condition_number is not None and condition_number > 1e6:
        logger.info(
            "dpp_selection: kernel condition_number=%s > 1e6, "
            "fallback=farthest_point",
            condition_number,
        )
        if seed_vectors is not None:
            return _farthest_point_sampling(seed_vectors, k)
        raise ValueError("seed_vectors required for farthest-point fallback")

    # Quality-diversity decomposition
    if quality is not None:
        q = quality
    else:
        q = jnp.ones(n)

    # Greedy DPP MAP inference
    selected: list[int] = []
    remaining = set(range(n))

    for _ in range(k):
        best_idx = -1
        best_det = -float("inf")

        for i in remaining:
            candidate = selected + [i]
            sub_L = L[jnp.array(candidate)][:, jnp.array(candidate)]
            # Apply quality
            sub_q = q[jnp.array(candidate)]
            Q = jnp.diag(sub_q)
            sub_L_q = Q @ sub_L @ Q

            sign, logdet = jnp.linalg.slogdet(sub_L_q)
            if sign <= 0:
                det_val = 0.0
            else:
                det_val = float(jnp.exp(logdet))

            if det_val > best_det:
                best_det = det_val
                best_idx = i

        if best_idx >= 0:
            selected.append(best_idx)
            remaining.discard(best_idx)

    return selected


def _farthest_point_sampling(
    vectors: Array,
    k: int,
) -> list[int]:
    """
    Select k points via farthest-point traversal.

    Picks the first point arbitrarily (index 0), then iteratively selects
    the point with the maximum minimum distance to any already-selected point.

    Args:
        vectors: (n, d) matrix of points.
        k: Number of points to select.

    Returns:
        List of selected indices.
    """
    n = vectors.shape[0]
    k = min(k, n)

    if k == 0:
        return []

    selected = [0]
    remaining = list(range(1, n))

    for _ in range(1, k):
        best_idx = -1
        best_dist = -float("inf")

        for i in remaining:
            sel_vecs = vectors[jnp.array(selected)]
            dists = jnp.sqrt(jnp.sum((vectors[i] - sel_vecs) ** 2, axis=1))
            min_dist = float(jnp.min(dists))

            if min_dist > best_dist:
                best_dist = min_dist
                best_idx = i

        if best_idx >= 0:
            selected.append(best_idx)
            remaining.remove(best_idx)

    return selected
