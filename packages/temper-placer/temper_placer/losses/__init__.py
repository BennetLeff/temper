"""
Standardized loss functions for the Benders-V6 pipeline.

This package has been modernized to use NumPy exclusively, removing JAX
dependencies for the active placement and routing architecture.
"""

from temper_placer.losses.base import (
    ClearanceRule,
    CompositeLoss,
    LoopConstraint,
    LossContext,
    LossFunction,
    LossResult,
    MountingRule,
    ThermalConstraint,
    WeightedLoss,
    apply_fixed_mask_to_gradients,
    smooth_step,
)

from temper_placer.losses.wirelength import (
    WirelengthLoss,
    SteinerTreeLoss,
    compute_total_hpwl,
)

__all__ = [
    "LossFunction",
    "LossResult",
    "LossContext",
    "CompositeLoss",
    "WeightedLoss",
    "smooth_step",
    "apply_fixed_mask_to_gradients",
    "ClearanceRule",
    "LoopConstraint",
    "ThermalConstraint",
    "MountingRule",
    "WirelengthLoss",
    "SteinerTreeLoss",
    "compute_total_hpwl",
]
