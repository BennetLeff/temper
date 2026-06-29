"""
Planarity and edge crossing loss functions.

This module implements loss functions that penalize intersecting net segments,
encouraging planar or near-planar placements that are easier to route with 
fewer vias.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


class EdgeCrossingLoss(LossFunction):
    """
    Penalize intersecting net segments.

    Uses a differentiable cross-product based proxy to detect intersections
    between 2-pin net segments. 

    Attributes:
        margin: Distance margin for 'near-miss' crossings.
    """

    def __init__(self, margin: float = 0.1):
        self.margin = margin

    @property
    def name(self) -> str:
        return "edge_crossing"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute total edge crossing penalty.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft rotations.
            context: LossContext.

        Returns:
            LossResult with total crossing penalty.
        """
        # Filter to 2-pin nets for simplicity and efficiency
        # We can expand to star-topology for N-pin nets later

        # Get pre-computed net data
        # net_pin_indices: (M, P), net_pin_mask: (M, P)
        mask = context.net_pin_mask

        if not context.net_pin_indices.shape[1] >= 2:
            return LossResult(value=jnp.array(0.0))

        # We compute crossing penalty for ALL nets, then mask out non-2-pin nets
        # This avoids dynamic shapes (TracerBoolConversionError) in JIT
        
        # Get pin positions for ALL nets: (M, 2, 2)
        # We take the first two pins of every net
        indices_all = context.net_pin_indices[:, :2] # (M, 2)
        offsets_all = context.net_pin_offsets[:, :2] # (M, 2, 2)

        p0_idx = indices_all[:, 0]
        p1_idx = indices_all[:, 1]

        p0_offset = offsets_all[:, 0]
        p1_offset = offsets_all[:, 1]

        # 3. Compute rotations
        angles = jnp.array([0.0, jnp.pi / 2, jnp.pi, 3 * jnp.pi / 2])

        # Get rotation for each pin's component
        # rotations is (N, 4), p0_idx is (M2,)
        rot0 = rotations[p0_idx] # (M2, 4)
        rot1 = rotations[p1_idx] # (M2, 4)

        a0 = jnp.sum(rot0 * angles[None, :], axis=1) # (M2,)
        a1 = jnp.sum(rot1 * angles[None, :], axis=1) # (M2,)

        # Rotate pin offsets
        def rotate_offset(offset, angle):
            cos_a = jnp.cos(angle)
            sin_a = jnp.sin(angle)
            rx = offset[..., 0] * cos_a - offset[..., 1] * sin_a
            ry = offset[..., 0] * sin_a + offset[..., 1] * cos_a
            return jnp.stack([rx, ry], axis=-1)

        r0 = rotate_offset(p0_offset, a0)
        r1 = rotate_offset(p1_offset, a1)

        # Absolute positions
        p0_abs = positions[p0_idx] + r0
        p1_abs = positions[p1_idx] + r1

        # Segment i: (A_i, B_i)
        A = p0_abs
        B = p1_abs

        # Pairwise comparison of all 2-pin nets
        # This is O(M2^2)
        # We use broadcasting to compute all side tests

        def compute_side(P, Q, R):
            """Side of point P relative to line QR."""
            return (R[..., 0] - Q[..., 0]) * (P[..., 1] - Q[..., 1]) - \
                   (R[..., 1] - Q[..., 1]) * (P[..., 0] - Q[..., 0])

        # A, B are (M2, 2)
        # For all pairs i, j:
        # Check if A_i, B_i are on opposite sides of segment (A_j, B_j)
        # AND if A_j, B_j are on opposite sides of segment (A_i, B_i)

        # Broadcasted points
        # Ai: (M2, 1, 2), Bi: (M2, 1, 2)
        # Aj: (1, M2, 2), Bj: (1, M2, 2)
        Ai = A[:, None, :]
        Bi = B[:, None, :]
        Aj = A[None, :, :]
        Bj = B[None, :, :]

        # Side tests
        # s1: Side of Ai relative to segment j
        s1 = compute_side(Ai, Aj, Bj) # (M2, M2)
        s2 = compute_side(Bi, Aj, Bj)

        # s3: Side of Aj relative to segment i
        s3 = compute_side(Aj, Ai, Bi)
        s4 = compute_side(Bj, Ai, Bi)

        # Differentiable intersection proxy
        # We want s1*s2 < 0 AND s3*s4 < 0
        # Smooth version: relu(-s1*s2) * relu(-s3*s4)

        # Normalize side tests by segment lengths to avoid scale dependence
        len_i_sq = jnp.sum((B - A)**2, axis=1) + 1e-6
        len_j_sq = jnp.sum((B - A)**2, axis=1) + 1e-6

        # (M, M) normalization
        norm = jnp.sqrt(len_i_sq[:, None] * len_j_sq[None, :])

        penalty_matrix = jax.nn.relu(-s1 * s2) * jax.nn.relu(-s3 * s4)
        penalty_matrix = penalty_matrix / (norm**2 + 1e-6)

        # Remove self-intersection and double counting
        eye_mask = jnp.eye(penalty_matrix.shape[0], dtype=bool)
        tri_mask = jnp.triu(jnp.ones_like(penalty_matrix, dtype=bool), k=1)
        
        # Mask out non-2-pin nets
        # Only count crossings where BOTH nets are 2-pin
        is_2pin = jnp.sum(mask, axis=1) == 2
        valid_net_mask = is_2pin[:, None] & is_2pin[None, :]
        
        # Combine masks
        final_mask = tri_mask & valid_net_mask

        total_penalty = jnp.sum(penalty_matrix * final_mask)

        return LossResult(value=total_penalty)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Ramp up planarity constraints in later training.
        """
        progress = epoch / jnp.maximum(total_epochs, 1)
        # Start at 40%, reach full at 80%
        return jnp.clip((progress - 0.4) / 0.4, 0.0, 1.0)
