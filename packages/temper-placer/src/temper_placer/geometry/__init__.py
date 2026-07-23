"""
Geometry engine for temper-placer — Rust-backed via pyo3.
"""

from __future__ import annotations

import math

import temper_geometry as _tg

# ---------------------------------------------------------------------------
# Constants from transform.py (ported to Python since they're static data)
# ---------------------------------------------------------------------------

ROTATION_ANGLES = (0.0, math.pi / 2, math.pi, 3 * math.pi / 2)
ROTATION_ANGLES_DEG = (0.0, 90.0, 180.0, 270.0)
ROTATION_MATRICES = (
    ((1.0, 0.0), (0.0, 1.0)),
    ((0.0, -1.0), (1.0, 0.0)),
    ((-1.0, 0.0), (0.0, -1.0)),
    ((0.0, 1.0), (-1.0, 0.0)),
)

# ---------------------------------------------------------------------------
# Re-exports from temper_geometry Rust crate
# ---------------------------------------------------------------------------

# Primitives
aabb_expand = _tg.aabb_expand
aabb_from_points = _tg.aabb_from_points
aabb_intersects = _tg.aabb_intersects
aabb_overlap_area = _tg.aabb_overlap_area
aabb_union = _tg.aabb_union
batch_point_distance = _tg.batch_point_distance
distance_to_board_boundary = _tg.distance_to_board_boundary
distance_to_rect_edge = _tg.distance_to_rect_edge
distance_to_specific_edge = _tg.distance_to_specific_edge
pairwise_distances = _tg.pairwise_distances
pairwise_distances_squared = _tg.pairwise_distances_squared
point_distance = _tg.point_distance
point_distance_squared = _tg.point_distance_squared
point_midpoint = _tg.point_midpoint
point_to_line_distance = _tg.point_to_line_distance
points_centroid = _tg.points_centroid
rect_area = _tg.rect_area
rect_center = _tg.rect_center
rect_contains_point = _tg.rect_contains_point
rect_corners = _tg.rect_corners
rect_dimensions = _tg.rect_dimensions
rect_from_center = _tg.rect_from_center

# Smooth
get_alpha_schedule = _tg.get_alpha_schedule
get_beta_schedule = _tg.get_beta_schedule
hpwl_smooth = _tg.hpwl_smooth
smooth_abs = _tg.smooth_abs
smooth_clip = _tg.smooth_clip
smooth_leaky_relu = _tg.smooth_leaky_relu
smooth_max = _tg.smooth_max
smooth_max_axis = _tg.smooth_max_axis
smooth_max_pair = _tg.smooth_max_pair
smooth_min = _tg.smooth_min
smooth_min_axis = _tg.smooth_min_axis
smooth_min_pair = _tg.smooth_min_pair
smooth_relu = _tg.smooth_relu
smooth_relu_penalty = _tg.smooth_relu_penalty
smooth_step = _tg.smooth_step
weighted_average_smooth = _tg.weighted_average_smooth

# Transform
batch_get_rotated_bounds = _tg.batch_get_rotated_bounds
batch_rotate_points = _tg.batch_rotate_points
get_rotated_aabb = _tg.get_rotated_aabb
get_rotated_bounds = _tg.get_rotated_bounds
get_rotation_matrix = _tg.get_rotation_matrix
gumbel_softmax = _tg.gumbel_softmax
onehot_to_rotation_degrees = _tg.onehot_to_rotation_degrees
onehot_to_rotation_radians = _tg.onehot_to_rotation_radians
rotate_point = _tg.rotate_point
rotate_points = _tg.rotate_points
rotate_rectangle_corners = _tg.rotate_rectangle_corners
rotation_degrees_to_onehot = _tg.rotation_degrees_to_onehot
rotation_index_to_onehot = _tg.rotation_index_to_onehot
sample_rotation = _tg.sample_rotation
sample_rotation_batch = _tg.sample_rotation_batch
transform_pin_position = _tg.transform_pin_position
transform_pin_positions = _tg.transform_pin_positions

# Overlap
box_box_distance = _tg.box_box_distance
box_box_distance_aabb = _tg.box_box_distance_aabb
check_clearance_violation = _tg.check_clearance_violation
component_overlap_amount = _tg.component_overlap_amount
compute_clearance_penalties = _tg.compute_clearance_penalties
compute_overlap_penalty = _tg.compute_overlap_penalty
compute_pairwise_distances = _tg.compute_pairwise_distances
compute_total_overlap = _tg.compute_total_overlap
count_overlaps = _tg.count_overlaps
get_worst_overlap = _tg.get_worst_overlap
overlap_area_estimate = _tg.overlap_area_estimate

# SDF
sdf_box_2d = _tg.sdf_box_2d
sdf_capsule = _tg.sdf_capsule
sdf_circle = _tg.sdf_circle
sdf_convex_polygon = _tg.sdf_convex_polygon
sdf_intersection = _tg.sdf_intersection
sdf_offset = _tg.sdf_offset
sdf_polygon = _tg.sdf_polygon
sdf_rectangle = _tg.sdf_rectangle
sdf_round = _tg.sdf_round
sdf_rounded_rectangle = _tg.sdf_rounded_rectangle
sdf_shell = _tg.sdf_shell
sdf_smooth_intersection = _tg.sdf_smooth_intersection
sdf_smooth_union = _tg.sdf_smooth_union
sdf_subtraction = _tg.sdf_subtraction
sdf_to_mask = _tg.sdf_to_mask
sdf_to_penalty = _tg.sdf_to_penalty

# Polygon
compute_loop_area = _tg.compute_loop_area
compute_loop_perimeter = _tg.compute_loop_perimeter
is_convex = _tg.is_convex
loop_area_penalty = _tg.loop_area_penalty
nearest_point_on_polygon = _tg.nearest_point_on_polygon
nearest_point_on_segment = _tg.nearest_point_on_segment
point_in_polygon_soft = _tg.point_in_polygon_soft
point_in_polygon_winding = _tg.point_in_polygon_winding
point_in_rect = _tg.point_in_rect
point_in_rect_soft = _tg.point_in_rect_soft
polygon_area = _tg.polygon_area
polygon_bounding_box = _tg.polygon_bounding_box
polygon_bounding_circle = _tg.polygon_bounding_circle
polygon_centroid = _tg.polygon_centroid
polygon_orientation = _tg.polygon_orientation
polygon_perimeter = _tg.polygon_perimeter
polygon_signed_area = _tg.polygon_signed_area
rotate_polygon = _tg.rotate_polygon
scale_polygon = _tg.scale_polygon
translate_polygon = _tg.translate_polygon
triangle_area = _tg.triangle_area

# Projections
identity_projection = _tg.identity_projection
project_onto_board = _tg.project_onto_board
project_onto_edge_strip = _tg.project_onto_edge_strip
project_onto_half_plane = _tg.project_onto_half_plane
project_onto_side = _tg.project_onto_side
project_onto_zone = _tg.project_onto_zone
project_outside_keepout = _tg.project_outside_keepout

# DRC inflate
from temper_placer.geometry.drc_inflate import (  # noqa: E402, F401
    compute_drc_proxy_score,
    compute_inflated_half_dims_from_bounds,
    inflate_pad_polygon,
    precompute_from_pad_polygons,
    precompute_inflated_dims,
)

# ---------------------------------------------------------------------------
# sdf_gradient — kept as Python wrapper since Rust can't take a callable
# ---------------------------------------------------------------------------


def sdf_gradient(p: tuple[float, float], sdf_fn, eps: float = 1e-4) -> tuple[float, float]:
    """Compute the gradient of an SDF at point p using central finite differences."""
    px, py = p
    dx = (sdf_fn((px + eps, py)) - sdf_fn((px - eps, py))) / (2 * eps)
    dy = (sdf_fn((px, py + eps)) - sdf_fn((px, py - eps))) / (2 * eps)
    length = math.sqrt(dx * dx + dy * dy)
    if length > 1e-12:
        dx /= length
        dy /= length
    return (dx, dy)


__all__ = [n for n in dir() if not n.startswith("_") and n not in ("math", "n")]
