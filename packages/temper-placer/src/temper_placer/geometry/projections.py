"""
Projection operators — Rust-backed via temper_geometry.

This module provides projection operators for constraint satisfaction:
- Zone containment: clamp to polygon interior
- Keepout avoidance: clamp to nearest edge of complement
- Board bounds: orthogonal clamp to [margin, dim - margin]
- HV/LV half-space: project orthogonally onto boundary line
- Edge-mounting: clamp to edge-adjacent strip
- Manufacturing side: clamp to top/bottom half of board

All functions delegate to the temper_geometry Rust crate.
"""
import temper_geometry as _tg


def identity_projection(px, py):
    """Pass-through for fixed positions — returns the point unchanged.

    Args:
        px, py: Point coordinates

    Returns:
        (px, py) the same point
    """
    return _tg.identity_projection(px, py)


def project_onto_board(px, py, board_w, board_h, margin):
    """Project a point onto the board interior with edge margin.

    Clamps each coordinate independently to [margin, dim - margin].

    Args:
        px, py: Point coordinates
        board_w: Board width in mm
        board_h: Board height in mm
        margin: Edge margin in mm

    Returns:
        (x, y) projected point within the margin-bounded board rect
    """
    return _tg.project_onto_board(px, py, board_w, board_h, margin)


def project_onto_zone(px, py, zx, zy, zw, zh):
    """Project a component center onto a zone rectangle interior.

    If the point is inside the zone, returns identity. Otherwise, projects
    to the nearest point on the zone boundary.

    Args:
        px, py: Component center coordinates
        zx, zy: Zone rectangle position
        zw, zh: Zone rectangle size

    Returns:
        (x, y) projected point within the zone
    """
    return _tg.project_onto_zone(px, py, zx, zy, zw, zh)


def project_outside_keepout(px, py, kx, ky, kw, kh, half_w=0.0, half_h=0.0):
    """Project a component center outside a keepout rectangle.

    The keepout rect is expanded outward by the component half-size.
    The nearest boundary point of the expanded rect is returned.

    Args:
        px, py: Component center coordinates
        kx, ky: Keepout rectangle position
        kw, kh: Keepout rectangle size
        half_w: Component half-width in mm (default 0)
        half_h: Component half-height in mm (default 0)

    Returns:
        (x, y) projected point outside the expanded keepout rect
    """
    return _tg.project_outside_keepout(px, py, kx, ky, kw, kh, half_w, half_h)


def project_onto_half_plane(px, py, ox, oy, nx, ny):
    """Project a point onto a feasible half-plane.

    The half-plane is defined by an origin point (ox, oy) and normal (nx, ny).
    Points on the side of the normal are feasible.

    Args:
        px, py: Point coordinates
        ox, oy: Origin point on the boundary line
        nx, ny: Normal vector pointing into the feasible half-plane

    Returns:
        (x, y) projected point on the feasible side
    """
    return _tg.project_onto_half_plane(px, py, ox, oy, nx, ny)


def project_onto_edge_strip(px, py, ex1, ey1, ex2, ey2, strip_width):
    """Project a component center onto an edge-adjacent mounting strip.

    Args:
        px, py: Component center coordinates
        ex1, ey1: Edge line start
        ex2, ey2: Edge line end
        strip_width: Width of the mounting strip

    Returns:
        (x, y) projected point within the edge strip
    """
    return _tg.project_onto_edge_strip(px, py, ex1, ey1, ex2, ey2, strip_width)


def project_onto_side(px, py, board_w, board_h, side):
    """Project a component center onto a manufacturing side of the board.

    Args:
        px, py: Component center coordinates
        board_w: Board width in mm
        board_h: Board height in mm
        side: "top" or "bottom"

    Returns:
        (x, y) projected point
    """
    return _tg.project_onto_side(px, py, board_w, board_h, side)
