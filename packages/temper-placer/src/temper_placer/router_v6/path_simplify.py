"""
Path simplification for router export.

Removes redundant waypoints from grid paths by eliminating collinear points.
This reduces the number of trace segments in the exported PCB.

Wave 4 (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
``is_collinear``, ``simplify_path``, and ``estimate_segment_count`` delegate to
``temper_geometry`` (``is_collinear_py``, ``simplify_path_py``,
``estimate_segment_count_py`` in ``via_clearance.rs``). These kernels were
first migrated to ``temper-rust-router`` (#856); this tier **re-homes** them
into ``temper-geometry``, the Wave-4 home crate for router_v6 geometry
(the duplicate ``temper-rust-router`` copies were deleted in the cross-crate
kernel dedupe; ``temper-geometry`` is the sole copy, pinned by both
``tests/router_v6/test_path_simplify_rust_differential.py`` and
``tests/router_v6/test_via_clearance_tier2_rust_differential.py``).
"""

import temper_geometry as _tg

from temper_placer.router_v6.grid_converter import GridCell


def _cell_wire(cell: GridCell) -> tuple[int, int, int]:
    return (cell.x, cell.y, cell.layer)


def is_collinear(p1: GridCell, p2: GridCell, p3: GridCell) -> bool:
    """Check if three points lie on the same axis-aligned line.

    Args:
        p1, p2, p3: Three consecutive grid cells

    Returns:
        True if all three points are on same horizontal or vertical line

    Example:
        >>> p1, p2, p3 = GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)
        >>> is_collinear(p1, p2, p3)
        True  # All on horizontal line at y=0

        >>> p1, p2, p3 = GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 1, 0)
        >>> is_collinear(p1, p2, p3)
        False  # L-shaped path
    """
    return _tg.is_collinear_py(_cell_wire(p1), _cell_wire(p2), _cell_wire(p3))


def simplify_path(cells: list[GridCell]) -> list[GridCell]:
    """Remove redundant points along straight segments.

    Keeps only waypoints where direction changes or layer transitions occur.
    Always preserves first and last points.

    Args:
        cells: Original path as list of grid cells

    Returns:
        Simplified path with redundant points removed

    Example:
        >>> # Straight line: collapse to endpoints
        >>> cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        >>> simplify_path(cells)
        [GridCell(0, 0, 0), GridCell(2, 0, 0)]

        >>> # L-shaped: keep corner
        >>> cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 1, 0)]
        >>> simplify_path(cells)
        [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 1, 0)]

        >>> # Layer change: always preserved
        >>> cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 0, 1)]
        >>> simplify_path(cells)
        [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 0, 1)]
    """
    wire = [_cell_wire(c) for c in cells]
    return [GridCell(x, y, layer) for x, y, layer in _tg.simplify_path_py(wire)]


def estimate_segment_count(cells: list[GridCell]) -> int:
    """Estimate number of KiCad segments after simplification.

    Useful for progress reporting and validation.

    Args:
        cells: Path before simplification

    Returns:
        Estimated number of trace segments
    """
    wire = [_cell_wire(c) for c in cells]
    return _tg.estimate_segment_count_py(wire)
