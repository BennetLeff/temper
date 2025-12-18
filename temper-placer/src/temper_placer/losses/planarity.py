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
        
        # Identify 2-pin nets
        pin_counts = jnp.sum(mask, axis=1)
        is_2pin = pin_counts == 2
        
        if not jnp.any(is_2pin):
            return LossResult(value=jnp.array(0.0))
            
        # Extract indices of 2-pin nets
        net_indices = jnp.where(is_2pin)[0]
        
        # Get pin positions for these nets: (M2, 2, 2)
        # where M2 is number of 2-pin nets
        indices_2pin = context.net_pin_indices[net_indices] # (M2, P)
        offsets_2pin = context.net_pin_offsets[net_indices] # (M2, P, 2)
        
        # For 2-pin nets, pin 0 and pin 1 are valid
        p0_idx = indices_2pin[:, 0]
        p1_idx = indices_2pin[:, 1]
        
        p0_offset = offsets_2pin[:, 0]
        p1_offset = offsets_2pin[:, 1]
        
        # Absolute positions (approximate - ignoring rotation for performance in crossing proxy)
        # TODO: Add rotation handling if needed
        p0_abs = positions[p0_idx] + p0_offset
        p1_abs = positions[p1_idx] + p1_offset
        
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
        
        # (M2, M2) normalization
        norm = jnp.sqrt(len_i_sq[:, None] * len_j_sq[None, :])
        
        penalty_matrix = jax.nn.relu(-s1 * s2) * jax.nn.relu(-s3 * s4)
        penalty_matrix = penalty_matrix / (norm**2 + 1e-6)
        
        # Remove self-intersection and double counting
        eye_mask = jnp.eye(penalty_matrix.shape[0], dtype=bool)
        tri_mask = jnp.triu(jnp.ones_like(penalty_matrix, dtype=bool), k=1)
        
        total_penalty = jnp.sum(penalty_matrix * tri_mask)
        
        return LossResult(value=total_penalty)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Ramp up planarity constraints in later training.
        """
        progress = epoch / jnp.maximum(total_epochs, 1)
        # Start at 40%, reach full at 80%
        return jnp.clip((progress - 0.4) / 0.4, 0.0, 1.0)
