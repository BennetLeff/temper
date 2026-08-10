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

identity_projection = _tg.identity_projection
project_onto_board = _tg.project_onto_board
project_onto_zone = _tg.project_onto_zone
project_onto_half_plane = _tg.project_onto_half_plane
project_onto_edge_strip = _tg.project_onto_edge_strip
project_onto_side = _tg.project_onto_side


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
