"""
Geometry primitives — Rust-backed via temper_geometry.

This module provides geometric functions for:
- Point operations (distance, midpoint)
- Rectangle representation and operations
- Axis-aligned bounding box (AABB) operations
- Distance to board edge calculations

All functions delegate to the temper_geometry Rust crate.
"""

import temper_geometry as _tg

# =============================================================================
# Point Operations
# =============================================================================

point_distance = _tg.point_distance
point_distance_squared = _tg.point_distance_squared
point_midpoint = _tg.point_midpoint
points_centroid = _tg.points_centroid
point_to_line_distance = _tg.point_to_line_distance

# =============================================================================
# Rectangle Operations
# =============================================================================

rect_from_center = _tg.rect_from_center
rect_center = _tg.rect_center
rect_dimensions = _tg.rect_dimensions
rect_area = _tg.rect_area
rect_contains_point = _tg.rect_contains_point
rect_corners = _tg.rect_corners

# =============================================================================
# Axis-Aligned Bounding Box (AABB) Operations
# =============================================================================

aabb_from_points = _tg.aabb_from_points
aabb_intersects = _tg.aabb_intersects
aabb_overlap_area = _tg.aabb_overlap_area
aabb_union = _tg.aabb_union
aabb_expand = _tg.aabb_expand

# =============================================================================
# Distance to Board Edge Functions
# =============================================================================

distance_to_rect_edge = _tg.distance_to_rect_edge
distance_to_specific_edge = _tg.distance_to_specific_edge
distance_to_board_boundary = _tg.distance_to_board_boundary

# =============================================================================
# Batch Operations for Efficiency
# =============================================================================

pairwise_distances = _tg.pairwise_distances
pairwise_distances_squared = _tg.pairwise_distances_squared
batch_point_distance = _tg.batch_point_distance
