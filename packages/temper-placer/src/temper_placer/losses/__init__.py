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
# Aesthetic losses
from temper_placer.losses.aesthetic import (
    AlignmentLoss,
    MirrorSymmetryLoss,
    RotationConsistencyLoss,
    StackedRowLoss,
    VisualGroupingLoss,
    WhitespaceLoss,
)
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
    create_jit_loss_fn,
    create_value_and_grad_fn,
    create_value_and_grad_fn_with_breakdown,
    smooth_step,
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

# Component spacing loss (specific component pairs)
from temper_placer.losses.component_spacing import (
    ComponentSpacingLoss,
)

# Coil requirement loss
from temper_placer.losses.coil import (
    CoilRequirementLoss,
    CoilRule,
    create_coil_loss,
)

# Congestion loss
from temper_placer.losses.congestion import (
    CongestionLoss,
    compute_congestion_penalty,
    compute_routing_demand,
    visualize_congestion,
)

# Channel capacity loss (routing bottleneck prevention)
from temper_placer.losses.channel_capacity import (
    ChannelCapacityLoss,
    compute_channel_capacity,
)

# Critical path length loss
from temper_placer.losses.critical_path import (
    CriticalPath,
    CriticalPathLengthLoss,
    compute_critical_path_penalty,
    create_temper_critical_paths,
)

# Crystal placement loss
from temper_placer.losses.crystal import (
    CrystalPlacementLoss,
    CrystalRule,
    create_crystal_loss,
)

# DRC loss (non-differentiable, cached)
from temper_placer.losses.drc_loss import (
    DRCCacheEntry,
    DRCHistory,
    DRCLoss,
    create_drc_loss,
)

# DRC oracle loss (temper-drc composable check integration)
from temper_placer.losses.drc_oracle_loss import (
    DRCCompositeLoss,
    create_drc_composite_loss,
)

# DRC proxy loss (differentiable width-inflated clearance)
from temper_placer.losses.drc_proxy import (
    DRCProxyLoss,
)

# Grid alignment loss
from temper_placer.losses.grid import (
    GridAlignmentLoss,
    compute_grid_penalty,
)

# Ground crossing loss
from temper_placer.losses.ground_crossing import (
    GroundCrossingLoss,
    compute_ground_crossing_penalty,
    detect_ground_domain_violations,
)

# Functional grouping losses
from temper_placer.losses.grouping import (
    GroupClusterLoss,
    GroupConfig,
    GroupSeparationLoss,
    ProximityLoss,
    ProximityRule,
    create_grouping_losses_from_constraints,
)

# Loop area loss
from temper_placer.losses.loop_area import (
    LoopAreaLoss,
    compute_loop_area_penalty,
    create_temper_loop_constraints,
)

# Manufacturing margin loss
from temper_placer.losses.manufacturing_margin import (
    ManufacturingMarginConfig,
    ManufacturingMarginLoss,
    compute_manufacturability_score,
    compute_margin_loss,
    compute_pairwise_clearances,
    create_manufacturing_margin_loss,
)

# Mechanical mounting loss
from temper_placer.losses.mechanical import (
    MechanicalMountingLoss,
    MountingRule,
    create_mechanical_loss,
)

# Net centroid attraction loss
from temper_placer.losses.net_centroid import (
    NetCentroidAttractionLoss,
)

# Net class separation loss
from temper_placer.losses.net_class import (
    NetClassRule,
    NetClassSeparationLoss,
    create_net_class_loss,
)

# Noise isolation loss
from temper_placer.losses.noise_isolation import (
    NoiseSensitiveIsolationLoss,
)

# Overlap loss
from temper_placer.losses.overlap import (
    OverlapLoss,
    compute_overlap_penalty,
)

# Planarity loss
from temper_placer.losses.planarity import (
    EdgeCrossingLoss,
)

# Pin Accessibility loss
from temper_placer.losses.pin_accessibility import (
    PinAccessibilityLoss,
)

# Power path loss (Parasitic Inductance)
from temper_placer.losses.power_path import (
    HighCurrentPathConfig,
    PowerPathLoss,
    SwitchingLoopConfig,
    create_power_path_loss,
)

# Regularization losses
from temper_placer.losses.regularization import (
    CenterOfMassLoss,
    EdgeAvoidanceLoss,
    RotationEntropyLoss,
    SpreadLoss,
    compute_rotation_entropy,
    compute_spread_penalty,
)

# Return path loss (Current Return Path)
from temper_placer.losses.return_path import (
    CurrentReturnPathLoss,
    ReturnPathConfig,
    create_return_path_loss,
)

# Routability loss
from temper_placer.losses.routability import (
    RoutabilityLoss,
)

# Thermal loss
from temper_placer.losses.thermal import (
    EdgePreferenceLoss,
    HeatSensitiveDistanceLoss,
    ThermalComponentConfig,
    ThermalLoss,
    ThermalSpreadLoss,
    compute_edge_distance,
    compute_thermal_penalty,
    create_edge_preference_loss,
    create_heat_sensitive_distance_loss,
    create_temper_thermal_constraints,
    create_temper_thermal_losses,
    create_thermal_spread_loss,
)

# Via Density loss
from temper_placer.losses.via_density import (
    ViaDensityLoss,
)

# Wirelength loss (HPWL)
from temper_placer.losses.wirelength import (
    SteinerTreeLoss,
    WirelengthLoss,
    compute_total_hpwl,
)

# Zone membership loss
from temper_placer.losses.zone import (
    ZoneMembershipLoss,
    compute_zone_distance,
    compute_zone_membership_penalty,
    create_temper_zone_assignments,
)

# Zone avoidance loss (temper-3b1l)
from temper_placer.losses.zone_avoidance import (
    ZoneAvoidanceLoss,
    compute_zone_avoidance_penalty,
    signed_distance_to_polygon,
    signed_distance_to_rectangle,
)

# Routing-aware placement losses
from temper_placer.losses.routing_aware import (
    BusAlignmentLoss,
    MCUClusteringLoss,
    RoutingChannelLoss,
    compute_routing_channel_penalty,
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
    "ComponentSpacingLoss",
    "LoopAreaLoss",
    # Design rule losses
    "ThermalLoss",
    "ThermalSpreadLoss",
    "HeatSensitiveDistanceLoss",
    "EdgePreferenceLoss",
    "ThermalComponentConfig",
    "ZoneMembershipLoss",
    "ZoneAvoidanceLoss",
    "GroundCrossingLoss",
    "CongestionLoss",
    "RoutabilityLoss",
    "ChannelCapacityLoss",
    "compute_channel_capacity",
    "PowerPathLoss",
    "create_power_path_loss",
    "HighCurrentPathConfig",
    "SwitchingLoopConfig",
    "PinAccessibilityLoss",
    "CurrentReturnPathLoss",
    "create_return_path_loss",
    "ReturnPathConfig",
    "NetClassSeparationLoss",
    "create_net_class_loss",
    "NetClassRule",
    "NetCentroidAttractionLoss",
    "AlignmentLoss",
    "MirrorSymmetryLoss",
    "VisualGroupingLoss",
    "WhitespaceLoss",
    "StackedRowLoss",
    "RotationConsistencyLoss",
    "ManufacturingMarginLoss",
    "EdgeCrossingLoss",
    "SteinerTreeLoss",
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
    "EdgeAvoidanceLoss",
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
    "compute_zone_avoidance_penalty",
    "signed_distance_to_polygon",
    "signed_distance_to_rectangle",
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
    "create_manufacturing_losses",
    # DRC loss (non-differentiable, cached)
    "DRCLoss",
    "DRCCacheEntry",
    "DRCHistory",
    # Critical path length loss
    "CriticalPath",
    "CriticalPathLengthLoss",
    "compute_critical_path_penalty",
    "create_temper_critical_paths",
    # Manufacturing margin loss
    "ManufacturingMarginConfig",
    "ManufacturingMarginLoss",
    "compute_manufacturability_score",
    "compute_margin_loss",
    "compute_pairwise_clearances",
    "create_manufacturing_margin_loss",
    # Routing-aware placement losses
    "RoutingChannelLoss",
    "MCUClusteringLoss",
    "BusAlignmentLoss",
    "compute_routing_channel_penalty",
    # DRC proxy loss (differentiable width-inflated clearance)
    "DRCProxyLoss",
    # DRC oracle loss (temper-drc composable check integration)
    "DRCCompositeLoss",
    "create_drc_composite_loss",
]
