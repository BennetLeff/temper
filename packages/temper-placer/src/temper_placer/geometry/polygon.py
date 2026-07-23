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


def polygon_area(vertices):
    """Compute area of a polygon using the shoelace formula.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        Polygon area (always positive)
    """
    return _tg.polygon_area(vertices)


def polygon_signed_area(vertices):
    """Compute signed area of a polygon (positive for CCW, negative for CW).

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        Signed polygon area
    """
    return _tg.polygon_signed_area(vertices)


def triangle_area(ax, ay, bx, by, cx, cy):
    """Compute area of a triangle from three points.

    Args:
        ax, ay: First vertex coordinates
        bx, by: Second vertex coordinates
        cx, cy: Third vertex coordinates

    Returns:
        Triangle area (always positive)
    """
    return _tg.triangle_area(ax, ay, bx, by, cx, cy)


# =============================================================================
# Polygon Centroid
# =============================================================================


def polygon_centroid(vertices):
    """Compute centroid of a polygon.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        (cx, cy) centroid coordinates
    """
    return _tg.polygon_centroid(vertices)


# =============================================================================
# Point-in-Polygon Tests
# =============================================================================


def point_in_polygon_winding(px, py, vertices):
    """Check if a point is inside a polygon using winding number.

    Args:
        px, py: Query point coordinates
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        1.0 if inside, 0.0 if outside
    """
    return _tg.point_in_polygon_winding(px, py, vertices)


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


def point_in_rect(px, py, rx, ry, rw, rh):
    """Check if point is inside axis-aligned rectangle.

    Args:
        px, py: Query point coordinates
        rx, ry: Rectangle position
        rw, rh: Rectangle size

    Returns:
        1.0 if inside, 0.0 if outside
    """
    return _tg.point_in_rect(px, py, rx, ry, rw, rh)


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


def polygon_perimeter(vertices):
    """Compute perimeter of a polygon.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        Polygon perimeter
    """
    return _tg.polygon_perimeter(vertices)


# =============================================================================
# Loop Area for PCB Design
# =============================================================================


def compute_loop_area(pin_positions):
    """Compute area of a current loop formed by pins.

    Args:
        pin_positions: Flat list of [x1, y1, x2, y2, ...] pin coordinates

    Returns:
        Loop area
    """
    return _tg.compute_loop_area(pin_positions)


def compute_loop_perimeter(pin_positions):
    """Compute perimeter of a current loop.

    Args:
        pin_positions: Flat list of [x1, y1, x2, y2, ...] pin coordinates

    Returns:
        Loop perimeter
    """
    return _tg.compute_loop_perimeter(pin_positions)


def loop_area_penalty(pin_positions, max_area_mm2, weight=1.0):
    """Compute penalty for loop area exceeding maximum.

    Args:
        pin_positions: Flat list of [x1, y1, x2, y2, ...] pin coordinates
        max_area_mm2: Maximum allowed loop area
        weight: Penalty weight

    Returns:
        Squared penalty for area exceeding max_area_mm2
    """
    return _tg.loop_area_penalty(pin_positions, max_area_mm2, weight)


# =============================================================================
# Bounding Box and Hull Operations
# =============================================================================


def polygon_bounding_box(vertices):
    """Compute axis-aligned bounding box of a polygon.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        (x1, y1, x2, y2) of bounding box
    """
    return _tg.polygon_bounding_box(vertices)


def polygon_bounding_circle(vertices):
    """Compute approximate bounding circle of a polygon.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        (cx, cy, radius)
    """
    return _tg.polygon_bounding_circle(vertices)


# =============================================================================
# Polygon Validation
# =============================================================================


def is_convex(vertices):
    """Check if a polygon is convex.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        True if convex, False otherwise
    """
    return _tg.is_convex(vertices)


def polygon_orientation(vertices):
    """Determine orientation of a polygon.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        1.0 for CCW, -1.0 for CW
    """
    return _tg.polygon_orientation(vertices)


# =============================================================================
# Nearest Point on Polygon / Segment
# =============================================================================


def nearest_point_on_segment(px, py, sx1, sy1, sx2, sy2):
    """Find the nearest point on line segment to the query point.

    Args:
        px, py: Query point coordinates
        sx1, sy1: Segment start coordinates
        sx2, sy2: Segment end coordinates

    Returns:
        (nx, ny) nearest point on the segment
    """
    return _tg.nearest_point_on_segment(px, py, sx1, sy1, sx2, sy2)


def nearest_point_on_polygon(px, py, vertices):
    """Find the nearest point on a polygon boundary to the query point.

    Args:
        px, py: Query point coordinates
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        (nx, ny) nearest point on the polygon boundary
    """
    return _tg.nearest_point_on_polygon(px, py, vertices)


# =============================================================================
# Polygon Transformations
# =============================================================================


def translate_polygon(vertices, dx, dy):
    """Translate a polygon by an offset.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates
        dx, dy: Translation offset

    Returns:
        Flat list of translated vertex coordinates
    """
    return _tg.translate_polygon(vertices, dx, dy)


def scale_polygon(vertices, sx, sy):
    """Scale a polygon.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates
        sx, sy: Scale factors

    Returns:
        Flat list of scaled vertex coordinates
    """
    return _tg.scale_polygon(vertices, sx, sy)


def rotate_polygon(vertices, angle_rad):
    """Rotate a polygon around its centroid.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates
        angle_rad: Rotation angle in radians (CCW positive)

    Returns:
        Flat list of rotated vertex coordinates
    """
    return _tg.rotate_polygon(vertices, angle_rad)
