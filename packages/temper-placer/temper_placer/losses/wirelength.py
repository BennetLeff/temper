import numpy as np
from temper_placer.losses.base import LossFunction
from temper_placer.losses.types import LossContext, LossResult


class WirelengthLoss(LossFunction):
    """
    Half-Perimeter Wire Length (HPWL) loss for minimizing total wire length.

    Standardized on NumPy for the Benders-V6 pipeline.
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
        if alpha is not None:
            self.alpha_start = alpha
            self.alpha_end = alpha
            self.alpha_warmup = 1.0
        else:
            self.alpha_start = alpha_start
            self.alpha_end = alpha_end
            self.alpha_warmup = alpha_warmup

        self.net_weight_scale = net_weight_scale
        self.net_weights = net_weights or {}

    def _get_alpha(self, epoch: int, total_epochs: int) -> float:
        warmup_end = self.alpha_warmup * total_epochs

        if epoch < warmup_end:
            return self.alpha_start
        
        anneal_duration = max((1 - self.alpha_warmup) * total_epochs, 1.0)
        progress = np.clip((epoch - warmup_end) / anneal_duration, 0.0, 1.0)
        
        return self.alpha_start + progress * (self.alpha_end - self.alpha_start)

    @property
    def name(self) -> str:
        return "wirelength"

    def __call__(
        self,
        positions: np.ndarray,
        rotations: np.ndarray,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: np.ndarray | None = None,
    ) -> LossResult:
        if context.net_pin_indices.shape[0] == 0:
            return LossResult(value=0.0)

        alpha = self._get_alpha(epoch, total_epochs)

        # Compute effective weights
        weights = context.net_weights
        if self.net_weights:
            valid_nets = [n for n in context.netlist.nets if len(n.pins) >= 2]
            multipliers = []
            for net in valid_nets:
                w = self.net_weights.get(net.name)
                if w is None:
                    w = self.net_weights.get(net.net_class, 1.0)
                multipliers.append(w)
            
            mult_array = np.array(multipliers, dtype=np.float32)
            weights = weights * mult_array

        # Get component positions for all pins: (M, P, 2)
        pin_comp_positions = positions[context.net_pin_indices]

        # Compute rotation angles: (N,)
        angles = np.array([0.0, np.pi / 2, np.pi, 3 * np.pi / 2])
        comp_angles = np.sum(rotations * angles[None, :], axis=1)

        # Get angles for each pin's component: (M, P)
        pin_angles = comp_angles[context.net_pin_indices]

        # Rotate pin offsets: (M, P, 2)
        cos_a = np.cos(pin_angles)
        sin_a = np.sin(pin_angles)

        px = context.net_pin_offsets[:, :, 0]
        py = context.net_pin_offsets[:, :, 1]

        rx = px * cos_a - py * sin_a
        ry = px * sin_a + py * cos_a

        rotated_offsets = np.stack([rx, ry], axis=-1)

        # Absolute pin positions: (M, P, 2)
        pin_positions = pin_comp_positions + rotated_offsets

        # Compute HPWL for each net
        hpwl_per_net = self._compute_hpwl_vectorized(
            pin_positions,
            context.net_pin_mask,
            weights,
            alpha=alpha,
            return_sum=False,
        )

        rhwl_per_net = hpwl_per_net / np.maximum(1, context.net_layer_counts)
        total_loss = np.sum(rhwl_per_net)

        return LossResult(value=total_loss * self.net_weight_scale)

    def _compute_hpwl_vectorized(
        self,
        pin_positions: np.ndarray,
        mask: np.ndarray,
        weights: np.ndarray,
        alpha: float,
        return_sum: bool = True,
    ) -> np.ndarray | float:
        x_coords = pin_positions[:, :, 0]
        y_coords = pin_positions[:, :, 1]

        # Masked coordinates
        # For non-differentiable NumPy, we can just use np.nan or similar, 
        # but to keep it close to the LogSumExp style (which is still a good smooth proxy):
        x_for_max = np.where(mask, x_coords, -np.inf)
        x_for_min = np.where(mask, x_coords, np.inf)
        y_for_max = np.where(mask, y_coords, -np.inf)
        y_for_min = np.where(mask, y_coords, np.inf)

        # Using LogSumExp for consistency with the JAX implementation's smoothing behavior
        def logsumexp(a, axis=None):
            a_max = np.max(a, axis=axis, keepdims=True)
            a_max[~np.isfinite(a_max)] = 0
            return np.log(np.sum(np.exp(a - a_max), axis=axis)) + np.squeeze(a_max, axis=axis)

        x_max = logsumexp(alpha * x_for_max, axis=1) / alpha
        x_min = -logsumexp(-alpha * x_for_min, axis=1) / alpha
        y_max = logsumexp(alpha * y_for_max, axis=1) / alpha
        y_min = -logsumexp(-alpha * y_for_min, axis=1) / alpha

        hpwl_per_net = (x_max - x_min) + (y_max - y_min)
        weighted_hpwl = weights * hpwl_per_net

        if return_sum:
            return np.sum(weighted_hpwl)
        return weighted_hpwl


class SteinerTreeLoss(WirelengthLoss):
    """
    Rectilinear Steiner Minimum Tree (RSMT) approximation loss.
    """
    use_congestion_penalty: bool = False # Congestion field currently legacy

    @property
    def name(self) -> str:
        return "steiner_wirelength"

    def __call__(
        self,
        positions: np.ndarray,
        rotations: np.ndarray,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: np.ndarray | None = None,
    ) -> LossResult:
        # Standard HPWL base
        res = super().__call__(
            positions, rotations, context, epoch, total_epochs, net_virtual_nodes
        )
        return res

    def _compute_hpwl_vectorized(
        self,
        pin_positions: np.ndarray,
        mask: np.ndarray,
        weights: np.ndarray,
        alpha: float,
        return_sum: bool = True,
    ) -> np.ndarray | float:
        # RSMT correction: HPWL * (1.0 + 0.1 * log2(n_pins - 1))
        x_coords = pin_positions[:, :, 0]
        y_coords = pin_positions[:, :, 1]

        x_for_max = np.where(mask, x_coords, -np.inf)
        x_for_min = np.where(mask, x_coords, np.inf)
        y_for_max = np.where(mask, y_coords, -np.inf)
        y_for_min = np.where(mask, y_coords, np.inf)

        def logsumexp(a, axis=None):
            a_max = np.max(a, axis=axis, keepdims=True)
            a_max[~np.isfinite(a_max)] = 0
            return np.log(np.sum(np.exp(a - a_max), axis=axis)) + np.squeeze(a_max, axis=axis)

        x_max = logsumexp(alpha * x_for_max, axis=1) / alpha
        x_min = -logsumexp(-alpha * x_for_min, axis=1) / alpha
        y_max = logsumexp(alpha * y_for_max, axis=1) / alpha
        y_min = -logsumexp(-alpha * y_for_min, axis=1) / alpha

        hpwl_per_net = (x_max - x_min) + (y_max - y_min)
        n_pins = np.sum(mask, axis=1)
        correction = 1.0 + 0.1 * np.log2(np.maximum(n_pins - 1, 1.0))

        weighted_hpwl = weights * hpwl_per_net * correction

        if return_sum:
            return np.sum(weighted_hpwl)
        return weighted_hpwl


def compute_total_hpwl(
    positions: np.ndarray,
    rotations: np.ndarray,
    context: LossContext,
    alpha: float = 10.0,
) -> float:
    loss = WirelengthLoss(alpha=alpha)
    result = loss(positions, rotations, context)
    return float(result.value)
