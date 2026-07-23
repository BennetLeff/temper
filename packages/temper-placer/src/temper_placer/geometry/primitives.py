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


def point_distance(x1, y1, x2, y2):
    """Compute Euclidean distance between two points.

    Args:
        x1, y1: First point coordinates
        x2, y2: Second point coordinates

    Returns:
        Distance between points
    """
    return _tg.point_distance(x1, y1, x2, y2)


def point_distance_squared(x1, y1, x2, y2):
    """Compute squared Euclidean distance between two points.

    Args:
        x1, y1: First point coordinates
        x2, y2: Second point coordinates

    Returns:
        Squared distance between points
    """
    return _tg.point_distance_squared(x1, y1, x2, y2)


def point_midpoint(x1, y1, x2, y2):
    """Compute midpoint between two points.

    Args:
        x1, y1: First point coordinates
        x2, y2: Second point coordinates

    Returns:
        (mx, my) midpoint coordinates
    """
    return _tg.point_midpoint(x1, y1, x2, y2)


def points_centroid(points):
    """Compute centroid (mean position) of a set of points.

    Args:
        points: Flat list of [x1, y1, x2, y2, ...] coordinates

    Returns:
        (cx, cy) centroid coordinates
    """
    return _tg.points_centroid(points)


def point_to_line_distance(px, py, ax, ay, bx, by):
    """Compute shortest distance from a point to a line segment.

    Args:
        px, py: Query point coordinates
        ax, ay: Line segment start coordinates
        bx, by: Line segment end coordinates

    Returns:
        Shortest distance from point to line segment
    """
    return _tg.point_to_line_distance(px, py, ax, ay, bx, by)


# =============================================================================
# Rectangle Operations
# =============================================================================


def rect_from_center(cx, cy, half_w, half_h):
    """Create rectangle from center point and half-dimensions.

    Args:
        cx, cy: Center point coordinates
        half_w: Half-width
        half_h: Half-height

    Returns:
        (rx, ry, rw, rh) rectangle position and size
    """
    return _tg.rect_from_center(cx, cy, half_w, half_h)


def rect_center(rx, ry, rw, rh):
    """Compute center of a rectangle.

    Args:
        rx, ry: Rectangle position
        rw, rh: Rectangle size

    Returns:
        (cx, cy) center coordinates
    """
    return _tg.rect_center(rx, ry, rw, rh)


def rect_dimensions(rx, ry, rw, rh):
    """Compute dimensions of a rectangle.

    Args:
        rx, ry: Rectangle position
        rw, rh: Rectangle size

    Returns:
        (width, height)
    """
    return _tg.rect_dimensions(rx, ry, rw, rh)


def rect_area(rx, ry, rw, rh):
    """Compute area of a rectangle.

    Args:
        rx, ry: Rectangle position
        rw, rh: Rectangle size

    Returns:
        Area of the rectangle
    """
    return _tg.rect_area(rx, ry, rw, rh)


def rect_contains_point(rx, ry, rw, rh, px, py):
    """Check if a point is inside a rectangle.

    Args:
        rx, ry: Rectangle position
        rw, rh: Rectangle size
        px, py: Point coordinates

    Returns:
        Soft containment indicator (0.0 to 1.0)
    """
    return _tg.rect_contains_point(rx, ry, rw, rh, px, py)


def rect_corners(rx, ry, rw, rh):
    """Get all four corners of a rectangle.

    Args:
        rx, ry: Rectangle position
        rw, rh: Rectangle size

    Returns:
        Flat list [x1, y1, x2, y2, x3, y3, x4, y4] of corner positions
    """
    return _tg.rect_corners(rx, ry, rw, rh)


# =============================================================================
# Axis-Aligned Bounding Box (AABB) Operations
# =============================================================================


def aabb_from_points(points):
    """Compute axis-aligned bounding box for a set of points.

    Args:
        points: Flat list of [x1, y1, x2, y2, ...] coordinates

    Returns:
        (x1, y1, x2, y2) AABB corners
    """
    return _tg.aabb_from_points(points)


def aabb_intersects(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    """Check if two AABBs intersect.

    Args:
        ax1, ay1, ax2, ay2: First AABB corners
        bx1, by1, bx2, by2: Second AABB corners

    Returns:
        Overlap indicator (positive = overlap, negative = separation)
    """
    return _tg.aabb_intersects(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2)


def aabb_overlap_area(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    """Compute overlap area between two AABBs.

    Args:
        ax1, ay1, ax2, ay2: First AABB corners
        bx1, by1, bx2, by2: Second AABB corners

    Returns:
        Overlap area (0 if no overlap)
    """
    return _tg.aabb_overlap_area(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2)


def aabb_union(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    """Compute union bounding box of two AABBs.

    Args:
        ax1, ay1, ax2, ay2: First AABB corners
        bx1, by1, bx2, by2: Second AABB corners

    Returns:
        (x1, y1, x2, y2) of union AABB
    """
    return _tg.aabb_union(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2)


def aabb_expand(x1, y1, x2, y2, margin):
    """Expand an AABB by a margin in all directions.

    Args:
        x1, y1, x2, y2: AABB corners
        margin: Amount to expand by

    Returns:
        (new_x1, new_y1, new_x2, new_y2)
    """
    return _tg.aabb_expand(x1, y1, x2, y2, margin)


# =============================================================================
# Distance to Board Edge Functions
# =============================================================================


def distance_to_rect_edge(px, py, rx, ry, rw, rh):
    """Compute distance from point to nearest edge of a rectangle.

    Positive if point is inside, negative if outside.

    Args:
        px, py: Point coordinates
        rx, ry: Rectangle position
        rw, rh: Rectangle size

    Returns:
        Signed distance to nearest edge (positive inside, negative outside)
    """
    return _tg.distance_to_rect_edge(px, py, rx, ry, rw, rh)


def distance_to_specific_edge(px, py, rx, ry, rw, rh, side):
    """Compute distance from point to a specific edge of a rectangle.

    Args:
        px, py: Point coordinates
        rx, ry: Rectangle position
        rw, rh: Rectangle size
        side: Edge identifier - "TOP", "BOTTOM", "LEFT", or "RIGHT"

    Returns:
        Distance to the specified edge
    """
    return _tg.distance_to_specific_edge(px, py, rx, ry, rw, rh, side)


def distance_to_board_boundary(px, py, board_w, board_h, margin):
    """Compute how far inside the board boundary a point is.

    Args:
        px, py: Point coordinates
        board_w: Board width
        board_h: Board height
        margin: Minimum distance from board edge

    Returns:
        Minimum distance to boundary (negative if outside)
    """
    return _tg.distance_to_board_boundary(px, py, board_w, board_h, margin)


# =============================================================================
# Batch Operations for Efficiency
# =============================================================================


def pairwise_distances(points):
    """Compute pairwise Euclidean distances between all points.

    Args:
        points: Flat list of [x1, y1, x2, y2, ...] coordinates

    Returns:
        Distance matrix as flat list (N*N)
    """
    return _tg.pairwise_distances(points)


def pairwise_distances_squared(points):
    """Compute pairwise squared Euclidean distances between all points.

    Args:
        points: Flat list of [x1, y1, x2, y2, ...] coordinates

    Returns:
        Squared distance matrix as flat list (N*N)
    """
    return _tg.pairwise_distances_squared(points)


def batch_point_distance(points_a, points_b):
    """Compute distances between corresponding points in two arrays.

    Args:
        points_a: Flat list of [x1, y1, x2, y2, ...] coordinates
        points_b: Flat list of [x1, y1, x2, y2, ...] coordinates

    Returns:
        Flat list of distances
    """
    return _tg.batch_point_distance(points_a, points_b)
