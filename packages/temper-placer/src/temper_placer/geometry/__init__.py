"""
Geometry engine for temper-placer.

This module provides differentiable geometric primitives and operations:
- Signed Distance Functions (SDF) for shapes
- Overlap detection between component bounding boxes
- Boundary containment checking
- Zone membership testing
- Polygon operations (area, centroid, point-in-polygon)
- Smooth approximations for differentiable optimization

All operations are implemented in JAX for automatic differentiation.
The SDF approach provides smooth gradients even when shapes don't overlap,
guiding the optimizer toward valid configurations.
"""

# Primitives: basic geometric operations
# Overlap detection: collision and clearance
from temper_placer.geometry.overlap import (
    box_box_distance,
    box_box_distance_aabb,
    check_clearance_violation,
    component_overlap_amount,
    compute_clearance_penalties,
    compute_overlap_penalty,
    compute_pairwise_distances,
    compute_total_overlap,
    count_overlaps,
    get_worst_overlap,
    overlap_area_estimate,
)

# Polygon operations: area, containment, transforms
from temper_placer.geometry.polygon import (
    compute_loop_area,
    compute_loop_perimeter,
    is_convex,
    loop_area_penalty,
    point_in_polygon_soft,
    point_in_polygon_winding,
    point_in_rect,
    point_in_rect_soft,
    polygon_area,
    polygon_bounding_box,
    polygon_bounding_circle,
    polygon_centroid,
    polygon_orientation,
    polygon_perimeter,
    polygon_signed_area,
    rotate_polygon,
    scale_polygon,
    translate_polygon,
    triangle_area,
)
from temper_placer.geometry.primitives import (
    aabb_expand,
    # AABB operations
    aabb_from_points,
    aabb_intersects,
    aabb_overlap_area,
    aabb_union,
    batch_point_distance,
    distance_to_board_boundary,
    # Distance to board edge
    distance_to_rect_edge,
    distance_to_specific_edge,
    pairwise_distances,
    pairwise_distances_squared,
    # Point operations
    point_distance,
    point_distance_squared,
    point_midpoint,
    point_to_line_distance,
    points_centroid,
    rect_area,
    # Rectangle operations
    rect_center,
    rect_contains_point,
    rect_corners,
    rect_dimensions,
    rect_from_center,
)

# Signed Distance Functions: smooth shape representations
from temper_placer.geometry.sdf import (
    sdf_box_2d,
    sdf_capsule,
    sdf_circle,
    sdf_convex_polygon,
    sdf_gradient,
    sdf_intersection,
    sdf_offset,
    sdf_polygon,
    sdf_rectangle,
    sdf_round,
    sdf_rounded_rectangle,
    sdf_shell,
    sdf_smooth_intersection,
    sdf_smooth_union,
    sdf_subtraction,
    sdf_to_mask,
    sdf_to_penalty,
    sdf_union,
)

# Smooth operations: differentiable approximations
from temper_placer.geometry.smooth import (
    get_alpha_schedule,
    get_beta_schedule,
    hpwl_smooth,
    smooth_abs,
    smooth_clip,
    smooth_leaky_relu,
    smooth_max,
    smooth_max_axis,
    smooth_max_pair,
    smooth_min,
    smooth_min_axis,
    smooth_min_pair,
    smooth_relu,
    smooth_relu_penalty,
    smooth_step,
    weighted_average_smooth,
)

# Transform operations: rotation with Gumbel-Softmax
from temper_placer.geometry.transform import (
    # Constants
    ROTATION_ANGLES,
    ROTATION_ANGLES_DEG,
    ROTATION_MATRICES,
    batch_get_rotated_bounds,
    batch_rotate_points,
    get_rotated_aabb,
    get_rotated_bounds,
    # Rotation matrix functions
    get_rotation_matrix,
    # Gumbel-Softmax sampling for differentiable discrete rotation
    gumbel_softmax,
    onehot_to_rotation_degrees,
    onehot_to_rotation_radians,
    # Point rotation
    rotate_point,
    rotate_points,
    # Rectangle rotation
    rotate_rectangle_corners,
    rotation_degrees_to_onehot,
    # One-hot encoding
    rotation_index_to_onehot,
    sample_rotation,
    sample_rotation_batch,
    # Pin transforms
    transform_pin_position,
    transform_pin_positions,
)

__all__ = [
    # Primitives
    "point_distance",
    "point_distance_squared",
    "point_midpoint",
    "point_to_line_distance",
    "points_centroid",
    "batch_point_distance",
    "pairwise_distances",
    "pairwise_distances_squared",
    "rect_center",
    "rect_corners",
    "rect_area",
    "rect_dimensions",
    "rect_from_center",
    "rect_contains_point",
    "aabb_from_points",
    "aabb_union",
    "aabb_intersects",
    "aabb_overlap_area",
    "aabb_expand",
    "distance_to_rect_edge",
    "distance_to_specific_edge",
    "distance_to_board_boundary",
    # Smooth
    "smooth_min",
    "smooth_max",
    "smooth_min_pair",
    "smooth_max_pair",
    "smooth_min_axis",
    "smooth_max_axis",
    "smooth_relu",
    "smooth_relu_penalty",
    "smooth_abs",
    "smooth_step",
    "smooth_clip",
    "smooth_leaky_relu",
    "hpwl_smooth",
    "weighted_average_smooth",
    "get_alpha_schedule",
    "get_beta_schedule",
    # Transform
    "ROTATION_ANGLES",
    "ROTATION_ANGLES_DEG",
    "ROTATION_MATRICES",
    "get_rotation_matrix",
    "rotate_point",
    "rotate_points",
    "batch_rotate_points",
    "rotate_rectangle_corners",
    "get_rotated_bounds",
    "get_rotated_aabb",
    "batch_get_rotated_bounds",
    "rotation_index_to_onehot",
    "rotation_degrees_to_onehot",
    "onehot_to_rotation_radians",
    "onehot_to_rotation_degrees",
    "transform_pin_position",
    "transform_pin_positions",
    "gumbel_softmax",
    "sample_rotation",
    "sample_rotation_batch",
    # Overlap
    "box_box_distance",
    "box_box_distance_aabb",
    "component_overlap_amount",
    "overlap_area_estimate",
    "compute_overlap_penalty",
    "compute_total_overlap",
    "count_overlaps",
    "get_worst_overlap",
    "compute_pairwise_distances",
    "check_clearance_violation",
    "compute_clearance_penalties",
    # SDF
    "sdf_circle",
    "sdf_rectangle",
    "sdf_box_2d",
    "sdf_rounded_rectangle",
    "sdf_capsule",
    "sdf_polygon",
    "sdf_convex_polygon",
    "sdf_union",
    "sdf_intersection",
    "sdf_subtraction",
    "sdf_smooth_union",
    "sdf_smooth_intersection",
    "sdf_round",
    "sdf_offset",
    "sdf_shell",
    "sdf_to_penalty",
    "sdf_to_mask",
    "sdf_gradient",
    # Polygon
    "polygon_area",
    "polygon_signed_area",
    "polygon_centroid",
    "polygon_perimeter",
    "polygon_orientation",
    "polygon_bounding_box",
    "polygon_bounding_circle",
    "is_convex",
    "triangle_area",
    "point_in_polygon_winding",
    "point_in_polygon_soft",
    "point_in_rect",
    "point_in_rect_soft",
    "scale_polygon",
    "rotate_polygon",
    "translate_polygon",
    "compute_loop_area",
    "compute_loop_perimeter",
    "loop_area_penalty",
]
