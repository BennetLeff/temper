import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


class ViaDensityLoss(LossFunction):
    """
    Estimate via requirements from placement to minimize layer transitions.

    Uses two heuristics:
    1. Net Span: Long nets likely need layer changes.
    2. Net Crossings: Intersecting net bounding boxes imply routing conflicts (vias).
    """

    def __init__(
        self,
        via_cost: float = 0.01,
        crossing_weight: float = 1.0,
        span_weight: float = 0.5,
        span_unit_mm: float = 20.0,  # 1 via per 20mm
    ):
        self.via_cost = via_cost
        self.crossing_weight = crossing_weight
        self.span_weight = span_weight
        self.span_unit_mm = span_unit_mm

    @property
    def name(self) -> str:
        return "via_density"

    def __call__(
        self,
        positions: jnp.ndarray,
        _rotations: jnp.ndarray,
        context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        _net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        # 1. Get positions of all pins for all nets
        # indices: (M, P), offsets: (M, P, 2)
        # positions: (N, 2)

        # Gather pin positions: (M, P, 2)
        pin_positions = positions[context.net_pin_indices] + context.net_pin_offsets

        # Mask: (M, P) -> (M, P, 1) for broadcasting
        mask = context.net_pin_mask[..., None]

        # 2. Compute Bounding Boxes for each net
        # To ignore masked values in min/max, we set them to +/- infinity
        inf = 1e6  # Sufficiently large for PCB coordinates

        masked_pos_min = jnp.where(mask, pin_positions, inf)
        masked_pos_max = jnp.where(mask, pin_positions, -inf)

        # (M, 2) - min/max x,y for each net
        net_min_xy = jnp.min(masked_pos_min, axis=1)
        net_max_xy = jnp.max(masked_pos_max, axis=1)

        # Handle cases where a net might have become invalid/empty (though precompute filters <2 pins)
        # If min > max (due to all masked), set span to 0
        # Use <= to allow zero-width or zero-height nets (e.g. horizontal/vertical lines)
        # inf <= -inf is False, so completely masked nets remain invalid.
        valid_nets = jnp.all(net_min_xy <= net_max_xy, axis=1)

        # 3. Estimate Vias from Span
        # Diagonal size of bounding box
        span_sq = jnp.sum((net_max_xy - net_min_xy) ** 2, axis=1)
        span = jnp.sqrt(span_sq + 1e-6)

        # Filter invalid nets
        span = jnp.where(valid_nets, span, 0.0)

        total_span_vias = jnp.sum(span) / self.span_unit_mm

        # 4. Estimate Vias from Crossings (AABB Intersection)
        # Broadcast for pairwise comparison: (M, 1, 2) vs (1, M, 2)
        min_a = net_min_xy[:, None, :]
        max_a = net_max_xy[:, None, :]
        min_b = net_min_xy[None, :, :]
        max_b = net_max_xy[None, :, :]

        # Intersection area (approximate crossing severity)
        inter_min = jnp.maximum(min_a, min_b)
        inter_max = jnp.minimum(max_a, max_b)
        positive_depth = jnp.maximum(0.0, inter_max - inter_min)
        intersection_area = positive_depth[..., 0] * positive_depth[..., 1]

        # 5. Refine with net directions (Planarity Proxy)
        # For 2-pin nets, the direction is clear.
        # For N-pin, we use the vector from first to last valid pin as proxy direction.

        # Extract first and last valid pins for each net: (M, 2)
        # We use context.net_pin_mask to find them.
        def get_direction(pin_pos, mask):
            # Masked positions
            valid_pos = jnp.where(mask[..., None], pin_pos, 0.0)

            # Simple proxy: vector from first pin to center of others
            first_pos = valid_pos[0]
            center_pos = jnp.sum(valid_pos, axis=0) / jnp.maximum(jnp.sum(mask), 1.0)
            return center_pos - first_pos

        # Vectorized across nets
        net_vectors = jax.vmap(get_direction)(pin_positions, context.net_pin_mask)

        # Normalize vectors
        norms = jnp.sqrt(jnp.sum(net_vectors**2, axis=-1) + 1e-9)
        unit_vectors = net_vectors / norms[:, None]

        # Compute abs(sin(theta)) between all net pairs: |v1 x v2|
        # (M, 1, 2) cross (1, M, 2) -> (M, M)
        sin_theta = jnp.abs(
            unit_vectors[:, None, 0] * unit_vectors[None, :, 1] -
            unit_vectors[:, None, 1] * unit_vectors[None, :, 0]
        )

        # Refined crossing severity: area * sin(theta)
        # Parallel nets have sin(theta) = 0, so no crossing penalty
        # Perpendicular nets have sin(theta) = 1, max penalty
        refined_crossing = intersection_area * sin_theta

        # Mask diagonal and invalid nets
        eye_mask = jnp.eye(intersection_area.shape[0], dtype=bool)
        valid_broadcast = valid_nets[:, None] & valid_nets[None, :]

        refined_crossing = jnp.where(eye_mask, 0.0, refined_crossing)
        refined_crossing = jnp.where(valid_broadcast, refined_crossing, 0.0)

        # Sum as proxy for crossing count/severity
        total_crossing_severity = jnp.sum(refined_crossing) / 2.0

        # Combine
        total_loss = self.via_cost * (
            self.span_weight * total_span_vias + self.crossing_weight * total_crossing_severity
        )

        return LossResult(
            value=total_loss,
            breakdown={"span_vias": total_span_vias, "crossing_severity": total_crossing_severity},
        )
