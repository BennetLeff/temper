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

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


class WirelengthLoss(LossFunction):
    """
    Half-Perimeter Wire Length (HPWL) loss for minimizing total wire length.

    For each net, computes the half-perimeter of the bounding box containing
    all pins. Uses LogSumExp approximation for differentiable min/max.

    This implementation is fully JAX-compatible and uses pre-computed arrays
    from LossContext for efficient vectorized computation without Python loops.

    Attributes:
        alpha: LogSumExp smoothing parameter. Higher = sharper approximation.
            For dynamic annealing, use alpha_start/alpha_end/alpha_warmup.
        alpha_start: Starting alpha value for annealing (default: 1.0).
        alpha_end: Ending alpha value for annealing (default: 20.0).
        alpha_warmup: Fraction of epochs at alpha_start before annealing begins (default: 0.2).
        net_weight_scale: Global scaling factor for net weights.
        net_weights: Optional dictionary mapping net names or net classes to
            weight multipliers. e.g. {"GND": 0.1, "CLK": 5.0, "HighSpeed": 2.0}.
    """

    def __init__(
        self,
        alpha: float | None = None,
        alpha_start: float = 1.0,
        alpha_end: float = 20.0,
        alpha_warmup: float = 0.2,
        net_weight_scale: float = 1.0,
        net_weights: dict[str, float] | None = None,
    ):
        """
        Initialize WirelengthLoss.

        Args:
            alpha: Legacy parameter. If provided, overrides alpha_start/alpha_end
                for constant alpha behavior (backward compatible).
            alpha_start: Starting alpha value for annealing. Low alpha gives
                smooth approximation with good gradients.
            alpha_end: Ending alpha value for annealing. High alpha gives sharp
                approximation close to true HPWL.
            alpha_warmup: Fraction of training at alpha_start before annealing begins.
                For example, 0.2 means first 20% of epochs use constant alpha_start.
            net_weight_scale: Global scaling factor for net weights.
            net_weights: Optional mapping of net name/class to weight multiplier.
        """
        # Handle legacy alpha parameter for backward compatibility
        if alpha is not None:
            self.alpha_start = alpha
            self.alpha_end = alpha
            self.alpha_warmup = 1.0  # No annealing if constant alpha
        else:
            self.alpha_start = alpha_start
            self.alpha_end = alpha_end
            self.alpha_warmup = alpha_warmup

        self.net_weight_scale = net_weight_scale
        self.net_weights = net_weights or {}

    def _get_alpha(self, epoch: int, total_epochs: int) -> float:
        """
        Compute alpha based on current epoch for annealing.

        Strategy:
        - Warmup phase (0 to alpha_warmup): Constant low alpha for smooth gradients
        - Annealing phase: Linear interpolation to high alpha for sharp HPWL

        Args:
            epoch: Current epoch index.
            total_epochs: Total number of epochs.

        Returns:
            Current alpha value for LogSumExp computation.
        """
        warmup_end = self.alpha_warmup * total_epochs

        # Compute annealing progress (used when past warmup phase)
        anneal_duration = jnp.maximum((1 - self.alpha_warmup) * total_epochs, 1.0)
        progress = (epoch - warmup_end) / anneal_duration
        progress = jnp.clip(progress, 0.0, 1.0)

        annealed_alpha = self.alpha_start + progress * (self.alpha_end - self.alpha_start)

        # Use jnp.where for JAX tracing compatibility (not Python if)
        return jnp.where(epoch < warmup_end, self.alpha_start, annealed_alpha)

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
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute total HPWL across all nets using vectorized operations.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with pre-computed net pin arrays.
            epoch: Current epoch for alpha annealing.
            total_epochs: Total epochs for alpha annealing.

        Returns:
            LossResult with total HPWL value.
        """
        # Check for empty nets
        if context.net_pin_indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        # Get dynamic alpha based on epoch (supports annealing)
        alpha = self._get_alpha(epoch, total_epochs)

        # Guard against NaN/Inf in inputs
        positions = jnp.nan_to_num(positions, nan=0.0, posinf=1e6, neginf=-1e6)
        rotations = jnp.nan_to_num(rotations, nan=0.25, posinf=0.25, neginf=0.25)

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
        hpwl_per_net = self._compute_hpwl_vectorized(
            pin_positions,
            context.net_pin_mask,
            weights,
            alpha=alpha,
            return_sum=False,
        )

        # RHWL = HPWL / layer_count
        # This prevents over-penalizing wirelength on boards with many routing layers.
        rhwl_per_net = hpwl_per_net / jnp.maximum(1, context.net_layer_counts)

        total_loss = jnp.sum(rhwl_per_net)

        return LossResult(value=total_loss * self.net_weight_scale)

    def _compute_hpwl_vectorized(
        self,
        pin_positions: Array,
        mask: Array,
        weights: Array,
        alpha: float,
        return_sum: bool = True,
    ) -> Array:
        """
        Compute HPWL for all nets in parallel using masked LogSumExp.

        Args:
            pin_positions: (M, P, 2) pin positions for all nets.
            mask: (M, P) boolean mask for valid pins.
            weights: (M,) weights for each net.
            alpha: LogSumExp smoothing parameter.
            return_sum: If True, return scalar total. Otherwise return (M,) array.

        Returns:
            Scalar total weighted HPWL or (M,) array of weighted HPWLs.
        """
        # ... existing coordinate extraction ...
        x_coords = pin_positions[:, :, 0]
        y_coords = pin_positions[:, :, 1]

        # Masked x coordinates: invalid pins get -inf for max, +inf for min
        x_for_max = jnp.where(mask, x_coords, -jnp.inf)
        x_for_min = jnp.where(mask, x_coords, jnp.inf)

        # Masked y coordinates
        y_for_max = jnp.where(mask, y_coords, -jnp.inf)
        y_for_min = jnp.where(mask, y_coords, jnp.inf)

        # Compute smooth max and min along pin dimension (axis=1)
        x_max = jax.nn.logsumexp(alpha * x_for_max, axis=1) / alpha
        x_min = -jax.nn.logsumexp(-alpha * x_for_min, axis=1) / alpha

        y_max = jax.nn.logsumexp(alpha * y_for_max, axis=1) / alpha
        y_min = -jax.nn.logsumexp(-alpha * y_for_min, axis=1) / alpha

        # HPWL for each net: (M,)
        hpwl_per_net = (x_max - x_min) + (y_max - y_min)

        # Weighted values
        weighted_hpwl = weights * hpwl_per_net

        if return_sum:
            return jnp.sum(weighted_hpwl)
        return weighted_hpwl

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Wirelength is active from the start but with lower weight initially.

        Returns constant 1.0 - curriculum scheduling happens in CompositeLoss.
        """
        return 1.0


class SteinerTreeLoss(WirelengthLoss):
    """
    Rectilinear Steiner Minimum Tree (RSMT) approximation loss.

    RSMT provides a more accurate estimate of routed wirelength than HPWL,
    especially for nets with many pins. This implementation uses a
    differentiable correction factor based on the number of pins in each net.

    Additionally, it can incorporate a congestion penalty that scales wirelength
    cost by the local density of components, discouraging nets from passing
    through highly congested areas.

    Correction factor formula (empirical):
    RSMT ≈ HPWL * (1.0 + 0.1 * log2(n_pins - 1)) for n_pins > 2
    """

    use_congestion_penalty: bool = True

    @property
    def name(self) -> str:
        return "steiner_wirelength"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        # Standard Steiner computation
        res = super().__call__(
            positions, rotations, context, epoch, total_epochs, net_virtual_nodes
        )

        if not self.use_congestion_penalty:
            return res

        # Apply congestion penalty
        from temper_placer.losses.congestion import get_congestion_field

        # Get spatial congestion map
        congestion_grid = get_congestion_field(positions, context)

        # For each net, estimate its congestion cost
        # We simplify by taking the average congestion of the net's bounding box
        # net_pin_indices: (M, P)
        pin_comp_positions = positions[context.net_pin_indices]
        all_positions = pin_comp_positions + context.net_pin_offsets

        # Masked bounding boxes (M, 2)
        masked_positions = jnp.where(
            context.net_pin_mask[:, :, None],
            all_positions,
            jnp.array([jnp.inf, jnp.inf]),
        )
        masked_positions_max = jnp.where(
            context.net_pin_mask[:, :, None],
            all_positions,
            jnp.array([-jnp.inf, -jnp.inf]),
        )

        bb_min = jnp.min(masked_positions, axis=1)
        bb_max = jnp.max(masked_positions_max, axis=1)
        bb_center = (bb_min + bb_max) / 2.0

        # Map centers to grid coordinates
        board_bounds = context.board.get_relative_bounds_array()
        x_min, y_min, x_max, y_max = board_bounds
        rows, cols = congestion_grid.shape

        grid_x = jnp.clip((bb_center[:, 0] - x_min) / (x_max - x_min) * cols, 0, cols - 1).astype(
            jnp.int32
        )
        grid_y = jnp.clip((bb_center[:, 1] - y_min) / (y_max - y_min) * rows, 0, rows - 1).astype(
            jnp.int32
        )

        # Extract congestion at each net's center
        net_congestion = congestion_grid[grid_y, grid_x]

        # Final cost is Steiner length * (1.0 + congestion_impact)
        # Using a soft multiplier
        total_cost = res.value * (1.0 + 0.5 * jnp.mean(net_congestion))

        return LossResult(value=total_cost)

    def _compute_hpwl_vectorized(
        self,
        pin_positions: Array,
        mask: Array,
        weights: Array,
        alpha: float,
        return_sum: bool = True,
    ) -> Array:
        """
        Compute RSMT approximation using HPWL and pin-count correction.
        """
        # Extract x and y coordinates: (M, P)
        x_coords = pin_positions[:, :, 0]
        y_coords = pin_positions[:, :, 1]

        # Masked coordinates
        x_for_max = jnp.where(mask, x_coords, -jnp.inf)
        x_for_min = jnp.where(mask, x_coords, jnp.inf)
        y_for_max = jnp.where(mask, y_coords, -jnp.inf)
        y_for_min = jnp.where(mask, y_coords, jnp.inf)

        # Compute smooth max and min using dynamic alpha
        x_max = jax.nn.logsumexp(alpha * x_for_max, axis=1) / alpha
        x_min = -jax.nn.logsumexp(-alpha * x_for_min, axis=1) / alpha
        y_max = jax.nn.logsumexp(alpha * y_for_max, axis=1) / alpha
        y_min = -jax.nn.logsumexp(-alpha * y_for_min, axis=1) / alpha

        # HPWL per net: (M,)
        hpwl_per_net = (x_max - x_min) + (y_max - y_min)

        # Compute correction factors based on pin counts
        # mask is (M, P), sum along P gives n_pins per net: (M,)
        n_pins = jnp.sum(mask, axis=1)

        # Correction factor: 1.0 for 2-3 pins, increases logarithmically thereafter
        # Using jnp.log2(n - 1) * 0.1 as a heuristic
        # We use jnp.maximum to handle 1 or 2 pins safely
        correction = 1.0 + 0.1 * jnp.log2(jnp.maximum(n_pins - 1, 1.0))

        # Weighted values
        weighted_hpwl = weights * hpwl_per_net * correction

        if return_sum:
            return jnp.sum(weighted_hpwl)
        return weighted_hpwl


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
