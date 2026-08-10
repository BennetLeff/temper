"""
Component overlap detection — Rust-backed via temper_geometry.

This module provides overlap detection between PCB components using
temper_geometry's Rust implementation of signed distance functions (SDF)
and axis-aligned bounding box (AABB) approximations.

All functions delegate to the temper_geometry Rust crate.
"""

import temper_geometry as _tg

# =============================================================================
# Core Box-Box Distance Functions
# =============================================================================

box_box_distance = _tg.box_box_distance
box_box_distance_aabb = _tg.box_box_distance_aabb

# =============================================================================
# Overlap Amount and Area
# =============================================================================

component_overlap_amount = _tg.component_overlap_amount
overlap_area_estimate = _tg.overlap_area_estimate

# =============================================================================
# Batch Operations for All Pairwise Overlaps
# =============================================================================

compute_pairwise_distances = _tg.compute_pairwise_distances
compute_total_overlap = _tg.compute_total_overlap
compute_overlap_penalty = _tg.compute_overlap_penalty

# =============================================================================
# Clearance Checking
# =============================================================================

check_clearance_violation = _tg.check_clearance_violation
compute_clearance_penalties = _tg.compute_clearance_penalties

# =============================================================================
# Overlap Statistics
# =============================================================================

count_overlaps = _tg.count_overlaps
get_worst_overlap = _tg.get_worst_overlap
