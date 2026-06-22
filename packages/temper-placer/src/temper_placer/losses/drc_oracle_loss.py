"""
DRCCompositeLoss: Drop-in LossFunction wrapping temper-drc checks.

Provides a LossFunction subclass that evaluates the full temper-drc check suite
on the current placement and returns the aggregate penalty as a scalar loss value.

This is a non-differentiable term — the penalty is computed via Python-native
checks, not JAX operations. The CompositeLoss framework handles this naturally:
the loss value contributes to the total but gradients through the check logic
are zero (the signal is at the loss-value level, same pattern as DRCLoss).

Graceful degradation:
    If temper-drc is not installed, __call__ returns LossResult(value=0.0)
    with a "drc_unavailable" flag in the breakdown dict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult

if TYPE_CHECKING:
    from temper_placer.validation.drc_oracle import DRCOracle


class DRCCompositeLoss(LossFunction):
    """Loss function wrapping temper-drc composable checks.

    Evaluates the full temper-drc check suite on the current placement
    and returns the aggregate penalty as a scalar loss value.

    This is a non-differentiable term — the penalty is computed via
    Python-native checks, not JAX operations. The CompositeLoss framework
    handles this naturally: the loss value contributes to the total but
    doesn't need gradients through the check logic.

    Graceful degradation:
        If temper-drc is not installed, this loss returns 0.0 with
        a "drc_unavailable" flag in the breakdown dict.
    """

    def __init__(
        self,
        oracle: DRCOracle | None = None,
        context: LossContext | None = None,
        categories: list[str] | None = None,
    ):
        self._oracle = oracle
        self._available = oracle is not None
        self._categories = categories or ["drc", "safety"]
        self._last_penalty = 0.0

    @property
    def name(self) -> str:
        return "drc_composite"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        **kwargs: Any,
    ) -> LossResult:
        if not self._available or self._oracle is None:
            return LossResult(
                value=jnp.array(0.0),
                breakdown={"drc_unavailable": jnp.array(1.0)},
            )

        result = self._oracle.evaluate(positions, context, categories=self._categories)
        penalty = result.total_penalty
        self._last_penalty = penalty

        return LossResult(
            value=jnp.array(float(penalty)),
            breakdown={
                "drc_total_penalty": jnp.array(float(penalty)),
                "drc_checks_run": jnp.array(float(result.total_checks)),
                "drc_checks_failed": jnp.array(float(result.failed_checks)),
                "drc_errors": jnp.array(float(result.error_count)),
                "drc_warnings": jnp.array(float(result.warning_count)),
                "drc_criticals": jnp.array(float(result.critical_count)),
            },
        )

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """Ramp DRC weight from 0 to 1 over first 20% of training."""
        progress = epoch / max(total_epochs, 1)
        if progress < 0.2:
            return progress / 0.2
        return 1.0

    @property
    def last_penalty(self) -> float:
        """Most recently computed penalty value."""
        return self._last_penalty

    @property
    def is_available(self) -> bool:
        """Whether the temper-drc oracle is available."""
        return self._available


def create_drc_composite_loss(
    context: LossContext,
    categories: list[str] | None = None,
) -> DRCCompositeLoss:
    """Factory function to create a DRCCompositeLoss with graceful fallback.

    Attempts to create a DRCOracle wrapping temper-drc. If temper-drc
    is not installed, returns a DRCCompositeLoss that always evaluates
    to 0.0 with a "drc_unavailable" flag.

    Args:
        context: LossContext with netlist and clearance rules.
        categories: Optional list of check categories. Defaults to
            ["drc", "safety"].

    Returns:
        DRCCompositeLoss with oracle if available, or graceful fallback.
    """
    if categories is None:
        categories = ["drc", "safety"]

    try:
        from temper_placer.validation.drc_oracle import create_standard_drc_oracle

        oracle = create_standard_drc_oracle(context)
        return DRCCompositeLoss(oracle=oracle, categories=categories)
    except ImportError:
        return DRCCompositeLoss(oracle=None, categories=categories)
