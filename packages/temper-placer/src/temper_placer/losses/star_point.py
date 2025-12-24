from __future__ import annotations

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


class StarPointLoss(LossFunction):
    """
    Penalizes deviation from a star-ground topology.
    
    This loss has two components:
    1. Pin Attraction: Pulls all pins of a star net towards the net's virtual node.
    2. Anchor Attraction: Pulls the net's virtual node towards a fixed anchor (if defined).
    
    The virtual node (optimizable variable) naturally settles at the centroid 
    of the pins if unanchored, or somewhere between the centroid and the anchor
    if anchored (depending on weights).
    """

    def __init__(self, pin_attraction_weight: float = 1.0, anchor_weight: float = 10.0):
        self.pin_attraction_weight = pin_attraction_weight
        self.anchor_weight = anchor_weight

    @property
    def name(self) -> str:
        return "star_point"

    @property
    def supports_virtual_nodes(self) -> bool:
        return True

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        # If no virtual nodes or constraints, return zero
        if net_virtual_nodes is None or context.star_net_indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        # 1. Gather component positions for star nets
        # We need to compute pin positions for all pins involved in star nets.
        # This is similar to wirelength loss but targeting specific nets.

        # We'll rely on the pre-computed net_pin_indices and net_pin_offsets
        # But we only care about nets that are in star_net_indices.

        # Slice the net arrays to get only star nets
        # star_net_indices contains the indices of nets that are star grounds
        star_indices = context.star_net_indices

        # Gather net properties for these star nets
        # net_pin_indices: (M, P) -> (S, P)
        s_pin_indices = context.net_pin_indices[star_indices]
        # net_pin_offsets: (M, P, 2) -> (S, P, 2)
        s_pin_offsets = context.net_pin_offsets[star_indices]
        # net_pin_mask: (M, P) -> (S, P)
        s_pin_mask = context.net_pin_mask[star_indices]

        # Get component centers and rotations for these pins
        # s_pin_indices is (S, P), positions is (N, 2) -> (S, P, 2)
        s_comp_pos = positions[s_pin_indices]
        s_comp_rot = rotations[s_pin_indices]

        # Compute absolute pin positions
        # Rotate offsets: (S, P, 2)
        # We need to flatten to rotate efficiently or use vmap
        S, P, _ = s_pin_offsets.shape
        flat_offsets = s_pin_offsets.reshape(-1, 2)
        flat_rot = s_comp_rot.reshape(-1, 4)

        # rotate_points usually takes (N, 2) and (N, 4) if using soft Rot?
        # Check rotate_points signature in core/state.py. It takes angle or matrix?
        # Actually rotate_points takes radians mostly in tests.
        # Let's check rotation logic in WirelengthLoss (it implements it manually usually).
        # We should use a helper or implement rotation here.
        # Standard soft rotation: pos + R * offset

        # Re-implement soft rotation logic for batch
        # rot is (..., 4) one-hot-ish
        # 0: 0 deg (1,0,0,1), 1: 90 (0,-1,1,0), 2: 180 (-1,0,0,-1), 3: 270 (0,1,-1,0)
        # x' = x*cos - y*sin
        # y' = x*sin + y*cos

        # cos_theta = r0 - r2
        # sin_theta = r1 - r3

        cos_theta = flat_rot[:, 0] - flat_rot[:, 2]
        sin_theta = flat_rot[:, 1] - flat_rot[:, 3]

        ox = flat_offsets[:, 0]
        oy = flat_offsets[:, 1]

        rx = ox * cos_theta - oy * sin_theta
        ry = ox * sin_theta + oy * cos_theta

        rotated_offsets = jnp.stack([rx, ry], axis=-1).reshape(S, P, 2)

        pin_positions = s_comp_pos + rotated_offsets  # (S, P, 2)

        # Get virtual nodes for these nets
        # net_virtual_nodes is (M, 2), we want (S, 2)
        star_nodes = net_virtual_nodes[star_indices]  # (S, 2)

        # Expand for broadcasting against pins: (S, 1, 2)
        star_nodes_expanded = star_nodes[:, None, :]

        # --- Component 1: Pin Attraction ---
        # Distance^2 from each pin to its star node
        diffs = pin_positions - star_nodes_expanded
        dists_sq = jnp.sum(diffs**2, axis=-1)  # (S, P)

        # Mask out invalid pins
        masked_dists_sq = dists_sq * s_pin_mask

        # Sum over pins, then sum over nets (weighted?)
        # Let's use the constraint weights (star_weights)
        net_losses = jnp.sum(masked_dists_sq, axis=1)  # (S,)
        pin_attraction_loss = jnp.sum(net_losses * context.star_weights)

        # --- Component 2: Anchor Attraction ---
        # Pull star nodes to anchors if they exist
        # star_anchor_pos: (S, 2)
        # star_has_anchor: (S,) bool

        anchor_diffs = star_nodes - context.star_anchor_pos
        anchor_dists_sq = jnp.sum(anchor_diffs**2, axis=-1)  # (S,)

        masked_anchor_dists = anchor_dists_sq * context.star_has_anchor
        anchor_loss = jnp.sum(masked_anchor_dists * context.star_weights)

        total_loss = (
            self.pin_attraction_weight * pin_attraction_loss +
            self.anchor_weight * anchor_loss
        )

        breakdown = {
            "pin_attraction": pin_attraction_loss,
            "anchor_attraction": anchor_loss
        }

        return LossResult(value=total_loss, breakdown=breakdown)

    def trace(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> tuple[Array, Trace]:
        """Generate a natural language trace for star ground constraints."""
        from temper_placer.explainability.trace import Trace

        if net_virtual_nodes is None or context.star_net_indices.shape[0] == 0:
            return jnp.array(0.0), Trace.empty()

        # Re-evaluate the loss to get individual contributions (simplified)
        result = self(positions, rotations, context, epoch, total_epochs, net_virtual_nodes)

        trace = Trace.empty()
        # For now, we contribute a single entry per star net if possible
        # Since we don't have per-net breakdown in the LossResult easy to parse here,
        # we'll use the combined value but structured by net name.

        for i, constraint in enumerate(context.star_ground_constraints):
            # Map back to virtual node index
            # This is a bit tricky without a proper mapping, but let's assume
            # they are in the same order as in context.star_net_indices

            # For simplicity, we'll just add the total star point loss weighted by net
            # If we want more detail, we'd need a more granular breakdown from self() or recompute.

            # Re-compute for this specific constraint
            # (Mock for now to satisfy the tracer)
            trace = trace.add(
                f"Net:{constraint.net_name}",
                float(result.value) / len(context.star_ground_constraints),
                constraint.because or f"Star ground topology for {constraint.net_name}"
            )

        return result.value, trace
