"""Grid cell coordinate type shared by the router's path geometry.

``GridCell`` was originally defined in ``router_v6/grid_converter.py``
alongside four pure-delegation functions (``grid_to_world``,
``extract_vias``, ``compute_path_length``, ``count_vias_in_path``) that
migrated to the ``temper-geometry`` crate (``via_clearance.rs``). The
delegation functions were deleted 2026-08-16 (Tier-2 shim deletion); the
type itself is production-required (``path_simplify.py`` constructs
``GridCell`` instances from the Rust ``simplify_path_py`` wire tuples and
``io/kicad_exporter.py`` consumes them), so it lives here as a plain data
holder with no compute.
"""

from dataclasses import dataclass


@dataclass
class GridCell:
    """Grid cell coordinates (x, y, layer)."""

    x: int
    y: int
    layer: int = 0
