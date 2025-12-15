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

The total loss is a weighted sum with curriculum learning for weight scheduling.
"""

# Imports will be added as modules are implemented
# from temper_placer.losses.constraints import overlap_loss, boundary_loss, hv_clearance_loss
# from temper_placer.losses.design_rules import zone_membership_loss, ground_crossing_loss
# from temper_placer.losses.performance import wirelength_loss, thermal_loss, loop_area_loss
# from temper_placer.losses.regularization import spread_loss, rotation_entropy_loss
# from temper_placer.losses.total import total_loss, LossWeights

__all__ = []
