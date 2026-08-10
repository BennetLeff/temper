"""
Polygon operations — Rust-backed via temper_geometry.

This module provides polygon operations for:
- Loop area loss (gate drive loops, bootstrap loops)
- Zone containment checking
- Component grouping and clustering

Key algorithms (Rust implementation):
- Shoelace formula for polygon area
- Winding number for point-in-polygon
- Convex hull for component bounding
"""

import temper_geometry as _tg

# =============================================================================
# Polygon Area (Shoelace Formula)
# =============================================================================

polygon_area = _tg.polygon_area
polygon_signed_area = _tg.polygon_signed_area
triangle_area = _tg.triangle_area

# =============================================================================
# Polygon Centroid
# =============================================================================

polygon_centroid = _tg.polygon_centroid

# =============================================================================
# Point-in-Polygon Tests
# =============================================================================

point_in_polygon_winding = _tg.point_in_polygon_winding
point_in_rect = _tg.point_in_rect


def point_in_polygon_soft(px, py, vertices, smoothness=0.1):
    """Soft point-in-polygon test (differentiable).

    Args:
        px, py: Query point coordinates
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates
        smoothness: Width of transition region

    Returns:
        Soft containment indicator in range [0, 1]
    """
    return _tg.point_in_polygon_soft(px, py, vertices, smoothness)


def point_in_rect_soft(px, py, rx, ry, rw, rh, smoothness=0.1):
    """Soft check if point is inside rectangle (differentiable).

    Args:
        px, py: Query point coordinates
        rx, ry: Rectangle position
        rw, rh: Rectangle size
        smoothness: Width of transition region

    Returns:
        Soft containment indicator in range [0, 1]
    """
    return _tg.point_in_rect_soft(px, py, rx, ry, rw, rh, smoothness)

# =============================================================================
# Polygon Perimeter
# =============================================================================

polygon_perimeter = _tg.polygon_perimeter

# =============================================================================
# Loop Area for PCB Design
# =============================================================================

compute_loop_area = _tg.compute_loop_area
compute_loop_perimeter = _tg.compute_loop_perimeter
loop_area_penalty = _tg.loop_area_penalty

# =============================================================================
# Bounding Box and Hull Operations
# =============================================================================

polygon_bounding_box = _tg.polygon_bounding_box
polygon_bounding_circle = _tg.polygon_bounding_circle

# =============================================================================
# Polygon Validation
# =============================================================================

is_convex = _tg.is_convex
polygon_orientation = _tg.polygon_orientation

# =============================================================================
# Nearest Point on Polygon / Segment
# =============================================================================

nearest_point_on_segment = _tg.nearest_point_on_segment
nearest_point_on_polygon = _tg.nearest_point_on_polygon

# =============================================================================
# Polygon Transformations
# =============================================================================

translate_polygon = _tg.translate_polygon
scale_polygon = _tg.scale_polygon
rotate_polygon = _tg.rotate_polygon
