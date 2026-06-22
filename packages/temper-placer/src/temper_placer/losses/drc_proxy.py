"""
DRC Proxy Loss — JAX-differentiable width-inflated clearance loss.

This module implements a fast, differentiable DRC-proxy term that inflates
component bounding boxes by trace_width/2 (Minkowski sum), then penalizes
intersections of inflated regions. This captures the root cause of the
width-inflation blind spot documented in docs/DRC_TRACKING.md.

Design:
- Minkowski inflation is precomputed at import time (non-JAX, Shapely).
- At evaluation time, only pairwise AABB distance checks run in JAX.
- Uses smooth_relu for differentiable penalty (following existing patterns).
"""

from __future__ import annotations

from typing import Any

import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.smooth import smooth_relu, get_beta_schedule
from temper_placer.losses.base import LossContext, LossFunction, LossResult


class DRCProxyLoss(LossFunction):
    """
    Differentiable DRC proxy loss using width-inflated occupancy.

    Penalizes component pairs whose inflated bounding boxes are closer than
    the specified clearance. The inflation (trace_width/2 on each side of
    each pad) captures the copper footprint that the center-line occupancy
    model misses.

    Constructor takes precomputed inflated half-dimensions, which should be
    computed at board load time using geometry/drc_inflate.py. This amortizes
    the expensive Shapely inflation across optimization epochs.

    Attributes:
        inflated_half_widths: (N,) half-widths after Minkowski inflation.
        inflated_half_heights: (N,) half-heights after Minkowski inflation.
        clearance_mm: Required track-to-track clearance (mm). Default 0.2mm.
        initial_beta: Starting smooth_relu beta for curriculum.
        final_beta: Final smooth_relu beta after annealing.
    """

    def __init__(
        self,
        inflated_half_widths: Array,
        inflated_half_heights: Array,
        clearance_mm: float = 0.2,
        initial_beta: float = 1.0,
        final_beta: float = 50.0,
    ):
        """
        Initialize DRCProxyLoss.

        Args:
            inflated_half_widths: (N,) half-widths after Minkowski inflation (mm).
            inflated_half_heights: (N,) half-heights after Minkowski inflation (mm).
            clearance_mm: Required clearance between inflated boxes (mm).
            initial_beta: Starting beta for smooth_relu annealing.
            final_beta: Final beta for smooth_relu annealing.
        """
        self.inflated_half_w = jnp.asarray(inflated_half_widths)
        self.inflated_half_h = jnp.asarray(inflated_half_heights)
        self.clearance_mm = clearance_mm
        self.initial_beta = initial_beta
        self.final_beta = final_beta

    @property
    def name(self) -> str:
        return "drc_proxy"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        **kwargs: Any,
    ) -> LossResult:
        """
        Compute DRC proxy loss for current placement.

        Uses annealed beta for curriculum: low beta (smooth gradients) early
        in training, high beta (strict enforcement) late in training.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators. Not used
                directly (inflation absorbs rotation via worst-case AABB).
            context: LossContext (not required for proxy — dimensions are
                precomputed in constructor).
            epoch: Current training epoch for beta annealing.
            total_epochs: Total training epochs for beta annealing.

        Returns:
            LossResult with total proxy penalty value.
        """
        n = positions.shape[0]

        if n < 2:
            return LossResult(value=jnp.array(0.0))

        beta = get_beta_schedule(
            epoch, total_epochs,
            initial_beta=self.initial_beta,
            final_beta=self.final_beta,
        )

        center_diff = positions[:, None, :] - positions[None, :, :]
        center_dist_x = jnp.abs(center_diff[:, :, 0])
        center_dist_y = jnp.abs(center_diff[:, :, 1])

        sum_half_w = self.inflated_half_w[:, None] + self.inflated_half_w[None, :]
        sum_half_h = self.inflated_half_h[:, None] + self.inflated_half_h[None, :]

        gap_x = center_dist_x - sum_half_w
        gap_y = center_dist_y - sum_half_h

        both_negative = (gap_x < 0) & (gap_y < 0)
        overlap_dist = jnp.minimum(gap_x, gap_y)
        separated_dist = jnp.maximum(gap_x, gap_y)
        distances = jnp.where(both_negative, overlap_dist, separated_dist)

        violations = smooth_relu(self.clearance_mm - distances, beta=beta)
        squared_violations = violations ** 2

        i_upper, j_upper = jnp.triu_indices(n, k=1)
        total_penalty = jnp.sum(squared_violations[i_upper, j_upper])

        return LossResult(
            value=total_penalty,
            breakdown={
                "beta": beta,
            }
        )

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        DRC proxy ramps up from 0.3 to 1.0 over the first 30% of training.
        """
        progress = epoch / max(total_epochs, 1)
        return jnp.where(progress < 0.3, 0.3 + 0.7 * (progress / 0.3), 1.0)
