"""
Channel capacity loss for preventing routing bottlenecks.

This loss penalizes placements where the gaps between components are
insufficient for the required number of traces to pass through.

Part of temper-b8ib: Implement ChannelCapacityLoss
"""

from __future__ import annotations

from typing import Any

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


class ChannelCapacityLoss(LossFunction):
    """Penalize insufficient routing channels between components.

    For each pair of components, computes:
    1. Gap = minimum distance between bounding boxes
    2. Capacity = (Gap - margin) / trace_pitch = max traces that fit
    3. Demand = estimated nets that must route through this gap
    4. Penalty = ReLU(Demand - Capacity)²

    This prevents tight clusters that look HPWL-optimal but can't be routed.

    Attributes:
        trace_width: Width of a single trace (mm).
        trace_spacing: Minimum spacing between traces (mm).
        min_margin: Minimum clearance on each side of channel (mm).
        demand_threshold: Only penalize if demand exceeds this fraction of capacity.
    """

    def __init__(
        self,
        trace_width: float = 0.2,
        trace_spacing: float = 0.2,
        min_margin: float = 0.5,
        demand_threshold: float = 0.8,
    ):
        """Initialize ChannelCapacityLoss.

        Args:
            trace_width: Width of a single trace (mm).
            trace_spacing: Minimum spacing between traces (mm).
            min_margin: Minimum clearance on each side of channel (mm).
            demand_threshold: Fraction of capacity before penalty applies.
        """
        self.trace_pitch = trace_width + trace_spacing  # 0.4mm per trace
        self.min_margin = min_margin
        self.demand_threshold = demand_threshold

    @property
    def name(self) -> str:
        return "channel_capacity"

    def __call__(
        self,
        positions: Array,
        rotations: Array,  # noqa: ARG002
        context: LossContext,
        epoch: int = 0,  # noqa: ARG002
        total_epochs: int = 1,  # noqa: ARG002
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
        **_kwargs: Any,
    ) -> LossResult:
        """Compute channel capacity penalty.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with component bounds and net info.

        Returns:
            LossResult with capacity shortage penalty.
        """
        n_components = positions.shape[0]

        # 1. Compute gaps between all component pairs
        gaps = self._compute_gaps(positions, context)  # (N, N)

        # 2. Compute channel capacities (how many traces fit)
        usable_gaps = jnp.maximum(0.0, gaps - 2 * self.min_margin)
        capacities = usable_gaps / self.trace_pitch  # (N, N)

        # 3. Estimate demand between pairs
        demand = self._estimate_demand(context)  # (N, N)

        if demand.shape[0] == 0:
             # Basic safety if demand could not be computed
             return LossResult(value=jnp.array(0.0), breakdown={})

        # 4. Compute shortage (demand above threshold * capacity)
        threshold_capacities = capacities * self.demand_threshold
        shortage = jnp.maximum(0.0, demand - threshold_capacities)

        # 5. Squared penalty, summed over upper triangle (avoid double counting)
        triu_mask = jnp.triu(jnp.ones((n_components, n_components)), k=1)
        penalty = jnp.sum(shortage ** 2 * triu_mask)

        # Breakdown for debugging
        max_shortage = jnp.max(shortage * triu_mask)
        avg_capacity = jnp.mean(capacities * triu_mask + jnp.eye(n_components) * 1000)

        return LossResult(
            value=penalty,
            breakdown={
                "max_shortage": max_shortage,
                "avg_channel_capacity": avg_capacity,
                "total_demand": jnp.sum(demand * triu_mask),
            }
        )

    def _compute_gaps(self, positions: Array, context: LossContext) -> Array:
        """Compute minimum gap between each pair of components.

        For axis-aligned bounding boxes, the gap is the minimum of
        horizontal and vertical separations.

        Args:
            positions: (N, 2) component positions.
            context: LossContext with component bounding boxes.

        Returns:
            (N, N) matrix of gaps between bounding boxes.
        """
        n = positions.shape[0]

        # Get dimensions from bounds array (N, 2)
        half_w = context.bounds[:, 0] / 2  # (N,)
        half_h = context.bounds[:, 1] / 2  # (N,)

        # Compute bounding box edges
        # left[i] = positions[i, 0] - half_w[i]
        left = positions[:, 0] - half_w
        right = positions[:, 0] + half_w
        bottom = positions[:, 1] - half_h
        top = positions[:, 1] + half_h

        # Horizontal gap: left[j] - right[i] (positive if j is to the right of i)
        h_gap_ij = left[None, :] - right[:, None]  # (N, N)
        h_gap_ji = left[:, None] - right[None, :]  # (N, N)
        h_gap = jnp.maximum(h_gap_ij, h_gap_ji)  # Actual horizontal separation

        # Vertical gap: bottom[j] - top[i]
        v_gap_ij = bottom[None, :] - top[:, None]  # (N, N)
        v_gap_ji = bottom[:, None] - top[None, :]  # (N, N)
        v_gap = jnp.maximum(v_gap_ij, v_gap_ji)  # Actual vertical separation

        # If boxes overlap in one dimension, gap is in the other dimension
        # If they overlap in both, gap is negative (overlap)
        # The "channel" gap is the larger of the two separations
        gap = jnp.maximum(h_gap, v_gap)

        # Set diagonal to large value (no self-gap)
        gap = gap + jnp.eye(n) * 1000.0

        return gap

    def _estimate_demand(self, context: LossContext) -> Array:
        """Estimate routing demand between each component pair.

        For each pair (i, j), counts nets that have pins on both components.
        This is a lower bound on traces that must route between them.

        Args:
            context: LossContext with net connectivity info.

        Returns:
            (N, N) matrix of estimated trace demand.
        """
        n = context.bounds.shape[0]  # type: ignore[union-attr]

        # Use pre-computed net pin indices from context
        # net_pin_indices: (M, P) where M=num_nets, P=max_pins_per_net
        # net_pin_mask: (M, P) boolean mask for valid pins

        net_pin_indices = context.net_pin_indices
        if net_pin_indices.shape[0] == 0:
            # Fallback: no net info available, assume uniform low demand for all pairs
            # except diagonal.
            return (jnp.ones((n, n)) - jnp.eye(n)) * 1.5

        net_pin_mask = context.net_pin_mask  # (M, P)

        # For each net, find which components have pins
        # component_has_pin[m, c] = True if net m has a pin on component c
        def net_to_component_mask(net_idx):
            """For one net, create (N,) mask of components with pins."""
            pins = net_pin_indices[net_idx]  # (P,)
            mask = net_pin_mask[net_idx]  # (P,)

            # Scatter: for each valid pin, mark its component
            component_mask = jnp.zeros(n)
            # Use segment_sum or scatter_add logic
            for p in range(pins.shape[0]):
                comp_idx = pins[p]
                is_valid = mask[p]
                component_mask = component_mask.at[comp_idx].add(is_valid.astype(jnp.float32))

            return component_mask > 0  # (N,) boolean

        # Vectorized version: build (M, N) matrix of component membership
        def build_component_membership():
            """Build (M, N) matrix: entry [m, c] = net m has pin on component c."""
            net_pin_indices.shape[0]
            # One-hot encode each pin's component, then sum over pins
            # This gives count of pins per component per net

            # Expand to (M, P, N) one-hot, then sum over P
            one_hot = jax.nn.one_hot(net_pin_indices, n)  # (M, P, N)
            masked = one_hot * net_pin_mask[:, :, None]  # Apply mask
            component_count = masked.sum(axis=1)  # (M, N)
            return component_count > 0  # (M, N) boolean

        component_membership = build_component_membership()  # (M, N)

        # Demand[i, j] = count of nets that have pins on BOTH i and j
        # = sum over nets of (has_pin[m, i] AND has_pin[m, j])
        membership_float = component_membership.astype(jnp.float32)  # (M, N)
        demand = jnp.einsum('mi,mj->ij', membership_float, membership_float)  # (N, N)

        # Zero out diagonal (self-demand meaningless)
        demand = demand - jnp.diag(jnp.diag(demand))

        return demand

    def weight_schedule(self, epoch: int, total_epochs: int) -> Array:
        """Channel capacity is important from early in training.

        Returns 1.0 after brief warmup to avoid harsh gradients initially.
        """
        warmup_fraction = 0.05
        warmup_limit = total_epochs * warmup_fraction
        return jnp.where(epoch < warmup_limit, 0.5, 1.0)


def compute_channel_capacity(
    positions: Array,
    widths: Array,
    heights: Array,
    trace_pitch: float = 0.4,
    margin: float = 0.5,
) -> Array:
    """Standalone function to compute channel capacities.

    Useful for debugging and visualization.

    Args:
        positions: (N, 2) component positions.
        widths: (N,) component widths.
        heights: (N,) component heights.
        trace_pitch: Trace width + spacing.
        margin: Minimum clearance on each side.

    Returns:
        (N, N) matrix of channel capacities (traces that fit).
    """
    n = positions.shape[0]

    half_w = widths / 2
    half_h = heights / 2

    left = positions[:, 0] - half_w
    right = positions[:, 0] + half_w
    bottom = positions[:, 1] - half_h
    top = positions[:, 1] + half_h

    h_gap = jnp.maximum(left[None, :] - right[:, None],
                        left[:, None] - right[None, :])
    v_gap = jnp.maximum(bottom[None, :] - top[:, None],
                        bottom[:, None] - top[None, :])

    gap = jnp.maximum(h_gap, v_gap) + jnp.eye(n) * 1000.0
    usable = jnp.maximum(0.0, gap - 2 * margin)

    return usable / trace_pitch
