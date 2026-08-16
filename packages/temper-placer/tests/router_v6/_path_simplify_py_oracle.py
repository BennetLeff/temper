"""Pinned Python oracle for ``router_v6/path_simplify.py`` (Wave-4 terminal-tree slice).

DO NOT EDIT -- THIS IS THE REFERENCE.
======================================
Every executable statement below is a **verbatim** ``git show`` extraction
from commit ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5`` (``origin/main``,
2026-08-03) of ``temper_placer/router_v6/path_simplify.py``: ``is_collinear``,
``simplify_path``, ``estimate_segment_count`` -- the whole module except its
import block and module docstring.

Nothing has been cleaned up, refactored, or fixed.
``test_path_simplify_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts each definition from the pinned commit and compares the source
text character for character.

Why this module has no float/NaN/hash traps
--------------------------------------------
``GridCell`` (``router_v6/grid_types.py``) is ``x: int, y: int, layer:
int = 0`` -- every comparison in this module (``==`` on ints) is exact and
total.  There is no ``math.hypot``, no ``int()`` truncation, no ``min``/``max``
over a NaN-poisoned iterable, and no set/dict whose iteration order could
leak into the output.  The one thing that DOES matter for a faithful Rust
port is that ``simplify_path`` iterates ``cells`` **in order** and appends to
a plain list -- any reordering (e.g. building the result via a set) would be
a behavior change even though nothing here is nondeterministic across runs.
"""

from __future__ import annotations

from temper_placer.router_v6.grid_types import GridCell

__all__ = ["is_collinear", "simplify_path", "estimate_segment_count"]


# --- path_simplify.py ---------------------------------------------------


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
    # All on same layer check (not strictly necessary but good practice)
    if not (p1.layer == p2.layer == p3.layer):
        return False

    # Horizontal line: same y, consecutive x
    if p1.y == p2.y == p3.y:
        return True

    # Vertical line: same x, consecutive y
    return p1.x == p2.x == p3.x


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
    if len(cells) <= 2:
        # Can't simplify paths with 2 or fewer points
        return cells

    simplified = [cells[0]]  # Always keep first point

    for i in range(1, len(cells) - 1):
        prev = cells[i - 1]
        curr = cells[i]
        next_cell = cells[i + 1]

        # Always keep layer transitions (via locations)
        if curr.layer != prev.layer or curr.layer != next_cell.layer:
            simplified.append(curr)
            continue

        # Keep point if direction changes (not collinear)
        if not is_collinear(prev, curr, next_cell):
            simplified.append(curr)

    simplified.append(cells[-1])  # Always keep last point

    return simplified


def estimate_segment_count(cells: list[GridCell]) -> int:
    """Estimate number of KiCad segments after simplification.

    Useful for progress reporting and validation.

    Args:
        cells: Path before simplification

    Returns:
        Estimated number of trace segments
    """
    simplified = simplify_path(cells)
    # Each pair of consecutive cells on same layer = 1 segment
    # Layer transitions don't create segments (they create vias)
    segment_count = 0
    for i in range(1, len(simplified)):
        if simplified[i].layer == simplified[i - 1].layer:
            segment_count += 1
    return segment_count
