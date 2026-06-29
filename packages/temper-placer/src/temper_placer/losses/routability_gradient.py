"""
Routability gradient loss with straight-through estimator (STE).

Implements StatefulLossFunction ABC with blend/compute_loss separation.
Uses HPWL soft proxy as the differentiable path and routability scores
as the non-differentiable target via jax.lax.stop_gradient.

STE formula (FR3.3):
  ste_signal = soft_proxy + jax.lax.stop_gradient(routability_scores - soft_proxy)

Forward: routability_scores. Backward: through soft_proxy (HPWL).

Part of feat/routability-gradient-signal (U5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    LossContext,
    LossResult,
    StatefulLossFunction,
)


@dataclass
class RoutabilityGradientLoss(StatefulLossFunction):
    """
    STE-based loss that pushes components away from congestion based on
    per-component routability scores from the SAT solver.

    blend() is called once per refinement iteration to update internal
    state. compute_loss() is pure and JAX-jittable.

    Attributes:
        _ema_scores: Exponentially-weighted moving average of routability scores.
        _blend_count: Number of times blend() has been called.
        _best_scores: Monotonic best-observed scores.
        _score_history: Mean scores per iteration for convergence guards.
        _alpha_floor: Minimum EWMA blending factor.
        _frozen: Whether scores are frozen due to oscillation.
        _use_best: Whether compute_loss should use best scores.
        _weight_decay_applied: Whether weight has been decayed.
        current_weight: Weight multiplier decayed on convergence.
    """

    _ema_scores: Array | None = field(default=None, init=False)
    _blend_count: int = field(default=0, init=False)
    _best_scores: Array | None = field(default=None, init=False)
    _score_history: list[float] = field(default_factory=list, init=False)
    _alpha_floor: float = 0.1
    _frozen: bool = field(default=False, init=False)
    _use_best: bool = field(default=False, init=False)
    _weight_decay_applied: bool = field(default=False, init=False)
    current_weight: float = 50.0  # FR4.1 base weight

    @property
    def name(self) -> str:
        return "routability_gradient"

    def blend(self, state: dict) -> None:
        """
        Blend new routability scores into EWMA state (FR3.1, FR4.5).

        Args:
            state: Dict with keys:
                - "routability_scores": (N,) array of raw per-component scores in [0,1].
                - "iteration": int iteration index.
                - "completion_rate": float (optional, for weight decay).
        """
        raw_scores = jnp.asarray(state["routability_scores"])
        self._blend_count += 1
        completion_rate = state.get("completion_rate", 0.0)

        # EWMA blending (FR4.5) — blend_count counts calls, not iteration index.
        if self._ema_scores is None:
            self._ema_scores = raw_scores
            if self._best_scores is None:
                self._best_scores = raw_scores
        else:
            alpha = max(self._alpha_floor, 1.0 / self._blend_count)
            self._ema_scores = (
                alpha * raw_scores + (1.0 - alpha) * self._ema_scores
            )

        score_mean = float(jnp.mean(self._ema_scores))
        self._score_history.append(score_mean)

        # Monotonic best tracking (FR5.3)
        current_best_mean = float(jnp.mean(self._best_scores))
        if score_mean < current_best_mean:
            self._best_scores = self._ema_scores

        # Decide if compute_loss should use best scores (JIT-safe: precompute flag).
        if current_best_mean < score_mean and self._best_scores is not None:
            self._use_best = True
        else:
            self._use_best = False

        # Weight decay on convergence (FR5.1)
        routability_threshold = state.get("routability_threshold", 0.85)
        if (
            not self._weight_decay_applied
            and len(self._score_history) >= 3
            and completion_rate > routability_threshold
        ):
            a, b, c = self._score_history[-3:]
            if a > b > c:  # 3-point decreasing trend
                self.current_weight *= 0.5
                self._weight_decay_applied = True

        # Oscillation detection (FR5.2)
        if len(self._score_history) >= 3:
            last_two_deltas = [
                self._score_history[-1] - self._score_history[-2],
                self._score_history[-2] - self._score_history[-3],
            ]
            if all(d > 0 for d in last_two_deltas):
                self._frozen = True
                self._ema_scores = self._best_scores

        # Reset freeze on improving iteration
        if len(self._score_history) >= 2:
            if self._score_history[-1] < self._score_history[-2]:
                self._frozen = False

    def compute_loss(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute routability gradient loss via straight-through estimator (FR3.2-FR3.5).

        Returns:
            LossResult with routability gradient loss value and breakdown.
        """
        N = positions.shape[0]
        if self._ema_scores is None or N == 0:
            return LossResult(
                value=jnp.array(0.0),
                breakdown={
                    "routability_gradient_total": jnp.array(0.0),
                    "routability_gradient_max": jnp.array(0.0),
                    "routability_gradient_mean": jnp.array(0.0),
                    "routability_active_components": jnp.array(0.0),
                },
            )

        scores = self._ema_scores
        if scores.shape[0] < N:
            padded = jnp.zeros(N)
            padded = padded.at[: scores.shape[0]].set(scores)
            scores = padded
        elif scores.shape[0] > N:
            scores = scores[:N]

        # JIT-safe: blend() precomputes whether best scores should be used.
        if self._frozen and self._best_scores is not None:
            best = self._best_scores
            if best.shape[0] < N:
                padded = jnp.zeros(N)
                padded = padded.at[: best.shape[0]].set(best)
                best = padded
            scores = best
        elif self._use_best and self._best_scores is not None:
            best = self._best_scores
            if best.shape[0] < N:
                padded = jnp.zeros(N)
                padded = padded.at[: best.shape[0]].set(best)
                best = padded
            scores = best

        # NaN guard (NFR2.1)
        positions = jnp.nan_to_num(positions, nan=0.0, posinf=1e6, neginf=-1e6)
        scores = jnp.nan_to_num(scores, nan=0.0, posinf=1.0, neginf=0.0)
        scores = jnp.clip(scores, 0.0, 1.0)

        # Straight-through estimator (FR3.3)
        soft_proxy = _compute_net_wirelengths(positions, context, N)  # (N,)
        ste_signal = soft_proxy + jax.lax.stop_gradient(scores - soft_proxy)
        ste_signal = jnp.clip(ste_signal, -1.0, 1.0)

        # Distance-from-anchor weighting (safe sqrt to avoid NaN at zero)
        anchors = jnp.nan_to_num(positions, nan=0.0, posinf=1e6, neginf=-1e6)
        squared_diff = jnp.sum((positions - anchors) ** 2, axis=-1)
        distances = jnp.sqrt(squared_diff + 1e-8)
        distances = jnp.clip(distances, 0.0, 1e6)

        loss = jnp.sum(ste_signal * distances) * self.current_weight

        return LossResult(
            value=loss,
            breakdown={
                "routability_gradient_total": loss,
                "routability_gradient_max": jnp.max(scores),
                "routability_gradient_mean": jnp.mean(scores),
                "routability_active_components": jnp.sum(scores > 0.0),
            },
        )


def _compute_net_wirelengths(
    positions: Array,
    context: LossContext,
    N: int = 0,
) -> Array:
    """
    Soft proxy: per-component HPWL normalized to [0, 1] (FR3.5).

    Uses vectorized scatter-add to aggregate HPWL per net to per-component,
    avoiding Python for-loops for JAX JIT compatibility.

    Returns:
        (N,) array of normalized per-component HPWL values.
    """
    if N == 0:
        N = positions.shape[0]

    # Check for empty context data
    net_pin_indices = getattr(context, "net_pin_indices", None)
    net_pin_offsets = getattr(context, "net_pin_offsets", None)
    net_pin_mask = getattr(context, "net_pin_mask", None)

    if net_pin_indices is None or net_pin_indices.shape[0] == 0:
        return jnp.zeros(N)

    # Get pin positions per net: (M, P, 2)
    pin_comp_positions = positions[net_pin_indices]

    # Apply pin offsets
    pin_positions = pin_comp_positions + net_pin_offsets

    # Mask invalid pins
    mask = net_pin_mask
    x_coords = jnp.where(mask, pin_positions[:, :, 0], jnp.inf)
    y_coords = jnp.where(mask, pin_positions[:, :, 1], jnp.inf)
    x_coords_max = jnp.where(mask, pin_positions[:, :, 0], -jnp.inf)
    y_coords_max = jnp.where(mask, pin_positions[:, :, 1], -jnp.inf)

    # HPWL per net: (M,)
    hpwl_per_net = (
        jnp.max(x_coords_max, axis=1)
        - jnp.min(x_coords, axis=1)
        + jnp.max(y_coords_max, axis=1)
        - jnp.min(y_coords, axis=1)
    )

    # Vectorized aggregation to components.
    # Each pin has a component index; we average HPWL across all pins of a net
    # and add the share to each component that the net touches.
    M = hpwl_per_net.shape[0]
    P = net_pin_indices.shape[1]

    # Count valid pins per net: (M,)
    pin_counts = jnp.sum(mask, axis=1).astype(jnp.float32)
    pin_counts = jnp.maximum(pin_counts, 1.0)

    # hpwl_share per pin: broadcast (M,) -> (M, P)
    hpwl_share = (hpwl_per_net / pin_counts)[:, None] * mask.astype(jnp.float32)

    # Flatten to 1D for scatter
    flat_indices = net_pin_indices.reshape(-1)
    flat_shares = hpwl_share.reshape(-1)

    # Scatter-add into component array
    comp_wl = jnp.zeros(N).at[flat_indices].add(flat_shares, mode="drop")

    # Normalize to [0, 1]
    max_wl = jnp.max(comp_wl)
    comp_wl = jnp.where(max_wl > 0, comp_wl / max_wl, comp_wl)

    return comp_wl
