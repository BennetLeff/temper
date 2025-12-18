"""
Wirelength loss function using Half-Perimeter Wire Length (HPWL).

HPWL is a standard metric for placement quality. It approximates total
wire length as the half-perimeter of the bounding box of each net's pins.

This implementation uses LogSumExp for smooth, differentiable approximation
of min/max operations, enabling gradient-based optimization.

The implementation uses pre-computed padded arrays for JAX JIT compatibility,
avoiding Python loops that would cause recompilation on every call.
"""

from __future__ import annotations

from typing import Optional

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.smooth import smooth_max, smooth_min
from temper_placer.losses.base import LossContext, LossFunction, LossResult


class WirelengthLoss(LossFunction):
    """
    Half-Perimeter Wire Length (HPWL) loss for minimizing total wire length.

    For each net, computes the half-perimeter of the bounding box containing
    all pins. Uses LogSumExp approximation for differentiable min/max.

    This implementation is fully JAX-compatible and uses pre-computed arrays
    from LossContext for efficient vectorized computation without Python loops.

    Attributes:
        alpha: Smoothing parameter for LogSumExp. Higher = sharper approximation.
            Typically annealed from 1.0 to 20.0 during training.
        net_weight_scale: Global scaling factor for net weights.
        net_weights: Optional dictionary mapping net names or net classes to
            weight multipliers. e.g. {"GND": 0.1, "CLK": 5.0, "HighSpeed": 2.0}.
    """

    def __init__(
        self,
        alpha: float = 10.0,
        net_weight_scale: float = 1.0,
        net_weights: Optional[dict[str, float]] = None,
    ):
        """
        Initialize WirelengthLoss.

        Args:
            alpha: LogSumExp smoothing parameter.
            net_weight_scale: Global scaling factor for net weights.
            net_weights: Optional mapping of net name/class to weight multiplier.
        """
        self.alpha = alpha
        self.net_weight_scale = net_weight_scale
        self.net_weights = net_weights or {}

    @property
    def name(self) -> str:
        return "wirelength"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute total HPWL across all nets using vectorized operations.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with pre-computed net pin arrays.

        Returns:
            LossResult with total HPWL value.
        """
        # Check for empty nets
        if context.net_pin_indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        # Compute effective weights (tracing time)
        weights = context.net_weights
        if self.net_weights:
            # We must filter nets exactly as LossContext does
            valid_nets = [n for n in context.netlist.nets if len(n.pins) >= 2]
            
            multipliers = []
            for net in valid_nets:
                # Check specific net name first, then net class, then default 1.0
                w = self.net_weights.get(net.name)
                if w is None:
                    w = self.net_weights.get(net.net_class, 1.0)
                multipliers.append(w)
            
            # Create constant array embedded in graph
            mult_array = jnp.array(multipliers, dtype=jnp.float32)
            weights = weights * mult_array

        # Get pre-computed arrays from context
        # net_pin_indices: (M, P) - component indices for each net's pins
        # net_pin_offsets: (M, P, 2) - pin offsets from component center
        # net_pin_mask: (M, P) - True for valid pins, False for padding
        # net_weights: (M,) - weight for each net

        # Get component positions for all pins: (M, P, 2)
        pin_comp_positions = positions[context.net_pin_indices]

        # Compute rotation angles from soft one-hot: (N,)
        angles = jnp.array([0.0, jnp.pi / 2, jnp.pi, 3 * jnp.pi / 2])
        comp_angles = jnp.sum(rotations * angles[None, :], axis=1)  # (N,)

        # Get angles for each pin's component: (M, P)
        pin_angles = comp_angles[context.net_pin_indices]

        # Rotate pin offsets: (M, P, 2)
        cos_a = jnp.cos(pin_angles)  # (M, P)
        sin_a = jnp.sin(pin_angles)  # (M, P)

        px = context.net_pin_offsets[:, :, 0]  # (M, P)
        py = context.net_pin_offsets[:, :, 1]  # (M, P)

        rx = px * cos_a - py * sin_a  # (M, P)
        ry = px * sin_a + py * cos_a  # (M, P)

        rotated_offsets = jnp.stack([rx, ry], axis=-1)  # (M, P, 2)

        # Compute absolute pin positions: (M, P, 2)
        pin_positions = pin_comp_positions + rotated_offsets

        # Compute HPWL for each net using masked operations
        total_hpwl = self._compute_hpwl_vectorized(
            pin_positions,
            context.net_pin_mask,
            weights,
        )

        return LossResult(value=total_hpwl * self.net_weight_scale)

    def _compute_hpwl_vectorized(
        self,
        pin_positions: Array,
        mask: Array,
        weights: Array,
    ) -> Array:
        """
        Compute HPWL for all nets in parallel using masked LogSumExp.

        Args:
            pin_positions: (M, P, 2) pin positions for all nets.
            mask: (M, P) boolean mask for valid pins.
            weights: (M,) weights for each net.

        Returns:
            Scalar total weighted HPWL.
        """
        # Extract x and y coordinates: (M, P)
        x_coords = pin_positions[:, :, 0]
        y_coords = pin_positions[:, :, 1]

        # For masked smooth max/min, we use -inf/+inf for proper logsumexp behavior.
        # JAX's logsumexp correctly handles -inf (exp(-inf) = 0, contributes nothing).
        #
        # CRITICAL: We previously used large_val = 1e10, but with alpha=10,
        # this computes exp(alpha * 1e10) = exp(1e11) = Inf, causing overflow.
        # Using -inf/+inf is mathematically correct and numerically stable.

        # Masked x coordinates: invalid pins get -inf for max, +inf for min
        x_for_max = jnp.where(mask, x_coords, -jnp.inf)
        x_for_min = jnp.where(mask, x_coords, jnp.inf)

        # Masked y coordinates
        y_for_max = jnp.where(mask, y_coords, -jnp.inf)
        y_for_min = jnp.where(mask, y_coords, jnp.inf)

        # Compute smooth max and min along pin dimension (axis=1)
        # Using LogSumExp: max ≈ (1/alpha) * log(sum(exp(alpha * x)))
        # For min, we use: min(x) = -max(-x)
        x_max = jax.nn.logsumexp(self.alpha * x_for_max, axis=1) / self.alpha
        x_min = -jax.nn.logsumexp(-self.alpha * x_for_min, axis=1) / self.alpha

        y_max = jax.nn.logsumexp(self.alpha * y_for_max, axis=1) / self.alpha
        y_min = -jax.nn.logsumexp(-self.alpha * y_for_min, axis=1) / self.alpha

        # HPWL for each net: (M,)
        hpwl_per_net = (x_max - x_min) + (y_max - y_min)

        # Weighted sum
        total_hpwl = jnp.sum(weights * hpwl_per_net)

        return total_hpwl

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Wirelength is active from the start but with lower weight initially.

        Returns constant 1.0 - curriculum scheduling happens in CompositeLoss.
        """
        return 1.0


def compute_total_hpwl(
    positions: Array,
    rotations: Array,
    context: LossContext,
    alpha: float = 10.0,
) -> Array:
    """
    Standalone function to compute total HPWL.

    Useful for quick evaluation without creating a loss instance.

    Args:
        positions: (N, 2) component positions.
        rotations: (N, 4) rotation one-hots.
        context: LossContext.
        alpha: LogSumExp smoothing parameter.

    Returns:
        Scalar total HPWL value.
    """
    loss = WirelengthLoss(alpha=alpha)
    result = loss(positions, rotations, context)
    return result.value
