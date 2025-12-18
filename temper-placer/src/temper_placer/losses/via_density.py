from typing import Tuple
import jax.numpy as jnp
from temper_placer.losses.base import LossFunction, LossResult, LossContext


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

        self, positions: jnp.ndarray, rotations: jnp.ndarray, context: LossContext
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

        # Intersection condition: max(min_a, min_b) < min(max_a, max_b)
        inter_min = jnp.maximum(min_a, min_b)
        inter_max = jnp.minimum(max_a, max_b)

        # Check overlap in both X and Y
        overlap_dim = inter_min < inter_max
        overlap = jnp.logical_and(overlap_dim[..., 0], overlap_dim[..., 1])

        # Remove diagonal (self-intersection)
        # Using a trick: logical_and with ~eye
        eye_mask = jnp.eye(overlap.shape[0], dtype=bool)
        overlap = jnp.logical_and(overlap, ~eye_mask)

        # Also remove invalid nets from calculation
        valid_broadcast = valid_nets[:, None] & valid_nets[None, :]
        overlap = jnp.logical_and(overlap, valid_broadcast)

        # Count crossings (divide by 2 because matrix is symmetric)
        # Using soft counting? No, crossing is boolean.
        # But for gradient descent, we need differentiable signal.
        # Boolean overlap has 0 gradient!

        # Differentiable Overlap:
        # Measures "depth" of overlap.
        # depth = min(max_a, max_b) - max(min_a, min_b)
        # if depth > 0, overlap exists.
        # We want to minimize (depth_x * depth_y) if both > 0

        depth = inter_max - inter_min  # (M, M, 2)

        # Smooth activation for depth > 0
        # ReLU-like: max(0, depth)
        positive_depth = jnp.maximum(0.0, depth)

        # Intersection area (approximate crossing severity)
        intersection_area = positive_depth[..., 0] * positive_depth[..., 1]

        # Mask diagonal
        intersection_area = jnp.where(eye_mask, 0.0, intersection_area)

        # Sum area as proxy for crossing count/severity
        # (This is better than count for optimization)
        total_crossing_severity = jnp.sum(intersection_area) / 2.0

        # Combine
        # Note: crossing_severity is in mm^2, so we might need to scale it to be comparable to "count".
        # Let's say 100mm^2 overlap ~= 1 via worth of trouble?
        # The prompt says "crossing_weight * crossings".
        # If we use area, it drives nets apart.
        # A hard count is hard to optimize. Area is good proxy.
        # Let's normalize area by some factor, say 10mm^2 = 1 unit?
        # Or just rely on the weight.

        total_loss = self.via_cost * (
            self.span_weight * total_span_vias + self.crossing_weight * total_crossing_severity
        )

        return LossResult(
            value=total_loss,
            breakdown={"span_vias": total_span_vias, "crossing_severity": total_crossing_severity},
        )
