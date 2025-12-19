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
- power_path_loss: Minimize parasitic inductance in power paths
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
    create_value_and_grad_fn_with_breakdown,
    LoopConstraint,
    LossContext,
    LossFunction,
    LossResult,
    MountingRule,
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

# Grid alignment loss
from temper_placer.losses.grid import (
    compute_grid_penalty,
    GridAlignmentLoss,
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
    create_edge_preference_loss,
    create_heat_sensitive_distance_loss,
    create_temper_thermal_constraints,
    create_temper_thermal_losses,
    create_thermal_spread_loss,
    EdgePreferenceLoss,
    HeatSensitiveDistanceLoss,
    ThermalComponentConfig,
    ThermalLoss,
    ThermalSpreadLoss,
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

# DRC loss (non-differentiable, cached)
from temper_placer.losses.drc_loss import (
    create_drc_loss,
    DRCCacheEntry,
    DRCHistory,
    DRCLoss,
)

# Functional grouping losses
from temper_placer.losses.grouping import (
    create_grouping_losses_from_constraints,
    GroupClusterLoss,
    GroupConfig,
    GroupSeparationLoss,
    ProximityLoss,
    ProximityRule,
)

# Critical path length loss
from temper_placer.losses.critical_path import (
    compute_critical_path_penalty,
    create_temper_critical_paths,
    CriticalPath,
    CriticalPathLengthLoss,
)

# Power path loss (Parasitic Inductance)
from temper_placer.losses.power_path import (
    PowerPathLoss,
    create_power_path_loss,
    HighCurrentPathConfig,
    SwitchingLoopConfig,
)

# Return path loss (Current Return Path)
from temper_placer.losses.return_path import (
    CurrentReturnPathLoss,
    create_return_path_loss,
    ReturnPathConfig,
)

# Net class separation loss
from temper_placer.losses.net_class import (
    NetClassSeparationLoss,
    create_net_class_loss,
    NetClassRule,
)

# Planarity loss
from temper_placer.losses.planarity import (
    EdgeCrossingLoss,
)

# Noise isolation loss
from temper_placer.losses.noise_isolation import (
    NoiseSensitiveIsolationLoss,
)

# Crystal placement loss
from temper_placer.losses.crystal import (
    CrystalPlacementLoss,
    create_crystal_loss,
    CrystalRule,
)

# Mechanical mounting loss
from temper_placer.losses.mechanical import (
    MechanicalMountingLoss,
    create_mechanical_loss,
    MountingRule,
)

# Via Density loss
from temper_placer.losses.via_density import (
    ViaDensityLoss,
)

# Aesthetic losses
from temper_placer.losses.aesthetic import (
    AlignmentLoss,
    RotationConsistencyLoss,
)

# Coil requirement loss
from temper_placer.losses.coil import (
    CoilRequirementLoss,
    create_coil_loss,
    CoilRule,
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
    "create_value_and_grad_fn_with_breakdown",
    "apply_fixed_mask_to_gradients",
    # Constraint types
    "ClearanceRule",
    "LoopConstraint",
    "ThermalConstraint",
    # Core loss functions
    "WirelengthLoss",
    "OverlapLoss",
    "BoundaryLoss",
    "GridAlignmentLoss",
    "ClearanceLoss",
    "LoopAreaLoss",
    # Design rule losses
    "ThermalLoss",
    "ThermalSpreadLoss",
    "HeatSensitiveDistanceLoss",
    "EdgePreferenceLoss",
    "ThermalComponentConfig",
    "ZoneMembershipLoss",
    "GroundCrossingLoss",
    "CongestionLoss",
    "PowerPathLoss",
    "create_power_path_loss",
    "HighCurrentPathConfig",
    "SwitchingLoopConfig",
    "CurrentReturnPathLoss",
    "create_return_path_loss",
    "ReturnPathConfig",
    "NetClassSeparationLoss",
    "create_net_class_loss",
    "NetClassRule",
    "AlignmentLoss",
    "RotationConsistencyLoss",
    "EdgeCrossingLoss",
    "NoiseSensitiveIsolationLoss",
    "CrystalPlacementLoss",
    "create_crystal_loss",
    "CrystalRule",
    "MechanicalMountingLoss",
    "create_mechanical_loss",
    "MountingRule",
    "ViaDensityLoss",
    "CoilRequirementLoss",
    "create_coil_loss",
    "CoilRule",
    # Regularization losses
    "SpreadLoss",
    "RotationEntropyLoss",
    "CenterOfMassLoss",
    # Functional grouping losses
    "GroupClusterLoss",
    "ProximityLoss",
    "GroupSeparationLoss",
    "GroupConfig",
    "ProximityRule",
    "create_grouping_losses_from_constraints",
    # Standalone functions
    "compute_total_hpwl",
    "compute_overlap_penalty",
    "compute_boundary_penalty",
    "compute_grid_penalty",
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
    "create_thermal_spread_loss",
    "create_heat_sensitive_distance_loss",
    "create_edge_preference_loss",
    "create_temper_thermal_losses",
    "create_drc_loss",
    # DRC loss (non-differentiable, cached)
    "DRCLoss",
    "DRCCacheEntry",
    "DRCHistory",
    # Critical path length loss
    "CriticalPath",
    "CriticalPathLengthLoss",
    "compute_critical_path_penalty",
    "create_temper_critical_paths",
]
