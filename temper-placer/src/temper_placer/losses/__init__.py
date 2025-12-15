"""
Loss functions for temper-placer.

This module contains all differentiable loss functions organized by category:

Hard Constraints (must be satisfied):
- overlap_loss: Penalize overlapping components
- boundary_loss: Keep components within board outline
- hv_clearance_loss: Enforce 10mm HV-to-LV clearance

Design Rule Constraints:
- zone_membership_loss: Components in designated zones
- ground_crossing_loss: Avoid crossing ground domain splits
- net_class_separation_loss: Maintain clearances between net classes

Performance Objectives:
- wirelength_loss: Half-perimeter wirelength (HPWL)
- thermal_loss: Place heat sources near board edges
- loop_area_loss: Minimize critical loop areas (gate drive, power)
- congestion_loss: Balance routing demand across board

Regularization:
- spread_loss: Prevent component clustering
- rotation_entropy_loss: Encourage rotation exploration (annealed)
- center_of_mass_loss: Balance component distribution

The total loss is a weighted sum with curriculum learning for weight scheduling.
"""

# Base classes and interfaces
from temper_placer.losses.base import (
    apply_fixed_mask_to_gradients,
    ClearanceRule,
    CompositeLoss,
    create_jit_loss_fn,
    create_value_and_grad_fn,
    LoopConstraint,
    LossContext,
    LossFunction,
    LossResult,
    smooth_step,
    ThermalConstraint,
    WeightedLoss,
)

# Wirelength loss (HPWL)
from temper_placer.losses.wirelength import (
    compute_total_hpwl,
    WirelengthLoss,
)

# Overlap loss
from temper_placer.losses.overlap import (
    compute_overlap_penalty,
    OverlapLoss,
)

# Boundary loss
from temper_placer.losses.boundary import (
    BoundaryLoss,
    compute_boundary_penalty,
)

# Clearance loss (HV-LV)
from temper_placer.losses.clearance import (
    ClearanceLoss,
    compute_clearance_penalty,
)

# Loop area loss
from temper_placer.losses.loop_area import (
    compute_loop_area_penalty,
    create_temper_loop_constraints,
    LoopAreaLoss,
)

# Thermal loss
from temper_placer.losses.thermal import (
    compute_edge_distance,
    compute_thermal_penalty,
    create_temper_thermal_constraints,
    ThermalLoss,
)

# Zone membership loss
from temper_placer.losses.zone import (
    compute_zone_distance,
    compute_zone_membership_penalty,
    create_temper_zone_assignments,
    ZoneMembershipLoss,
)

# Ground crossing loss
from temper_placer.losses.ground_crossing import (
    compute_ground_crossing_penalty,
    detect_ground_domain_violations,
    GroundCrossingLoss,
)

# Congestion loss
from temper_placer.losses.congestion import (
    compute_congestion_penalty,
    compute_routing_demand,
    CongestionLoss,
    visualize_congestion,
)

# Regularization losses
from temper_placer.losses.regularization import (
    CenterOfMassLoss,
    compute_rotation_entropy,
    compute_spread_penalty,
    RotationEntropyLoss,
    SpreadLoss,
)


__all__ = [
    # Base classes
    "LossFunction",
    "LossResult",
    "LossContext",
    "CompositeLoss",
    "WeightedLoss",
    "smooth_step",
    "create_jit_loss_fn",
    "create_value_and_grad_fn",
    "apply_fixed_mask_to_gradients",
    # Constraint types
    "ClearanceRule",
    "LoopConstraint",
    "ThermalConstraint",
    # Core loss functions
    "WirelengthLoss",
    "OverlapLoss",
    "BoundaryLoss",
    "ClearanceLoss",
    "LoopAreaLoss",
    # Design rule losses
    "ThermalLoss",
    "ZoneMembershipLoss",
    "GroundCrossingLoss",
    "CongestionLoss",
    # Regularization losses
    "SpreadLoss",
    "RotationEntropyLoss",
    "CenterOfMassLoss",
    # Standalone functions
    "compute_total_hpwl",
    "compute_overlap_penalty",
    "compute_boundary_penalty",
    "compute_clearance_penalty",
    "compute_loop_area_penalty",
    "compute_thermal_penalty",
    "compute_edge_distance",
    "compute_zone_distance",
    "compute_zone_membership_penalty",
    "compute_ground_crossing_penalty",
    "detect_ground_domain_violations",
    "compute_congestion_penalty",
    "compute_routing_demand",
    "visualize_congestion",
    "compute_spread_penalty",
    "compute_rotation_entropy",
    # Factory functions
    "create_temper_loop_constraints",
    "create_temper_thermal_constraints",
    "create_temper_zone_assignments",
]
