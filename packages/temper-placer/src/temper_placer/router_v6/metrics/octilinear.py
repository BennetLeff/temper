"""
Octilinear compliance metric and diagonal cost incentive.

Measures the fraction of track length routed at 45/135 (diagonal)
vs. 0/90 (orthogonal).  Also provides a configurable diagonal-vs-orthogonal
cost ratio for the A* pathfinder.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Final

from temper_placer.router_v6.grid_converter import GridCell

_ANGLE_TOLERANCE_DEG: Final[float] = 5.0


def add_diagonal_incentive(cost_ratio: float = 1.0) -> None:
    """Set the diagonal-vs-orthogonal cost ratio in the A* pathfinder.

    Lower values make diagonal moves cheaper, increasing diagonal share.
    Default 1.0 = no preference (sqrt(2)  1.414 for diagonals is standard).

    Modifies :data:`temper_placer.router_v6.astar_core.DIAGONAL_COST_FACTOR`.
    """
    import temper_placer.router_v6.astar_core as _astar

    _astar.DIAGONAL_COST_FACTOR = float(cost_ratio)


def _angle_deg(dx: float, dy: float) -> float:
    """Angle of a (dx, dy) vector in degrees, normalised to [0, 360)."""
    return math.degrees(math.atan2(dy, dx)) % 360.0


def _is_diagonal_angle(angle: float, tolerance: float = _ANGLE_TOLERANCE_DEG) -> bool:
    """Return True if *angle* is within *tolerance* of a 45-multiple."""
    for target in (45.0, 135.0, 225.0, 315.0):
        delta = abs(angle - target)
        if delta <= tolerance or delta >= 360.0 - tolerance:
            return True
    return False


def _segment_classification(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> tuple[float, bool]:
    """Return (euclidean_length, is_diagonal) for a segment.

    A segment of effectively-zero length returns (0.0, False).
    """
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return 0.0, False
    angle = _angle_deg(dx, dy)
    return length, _is_diagonal_angle(angle)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def octilinear_fraction(
    path: list[GridCell],
    cell_size: float = 1.0,
) -> float:
    """Return the fraction (0.0-1.0) of track length made of diagonal steps.

    Operates on a simplified grid path (output of
    :func:`~temper_placer.router_v6.path_simplify.simplify_path`).
    Layer transitions (via sites) are excluded from the denominator:
    only same-layer cell-to-cell segments contribute.

    A single-cell path (no segments) returns 0.0.
    """
    if len(path) < 2:
        return 0.0

    total_length = 0.0
    diagonal_length = 0.0

    for i in range(1, len(path)):
        prev = path[i - 1]
        curr = path[i]

        if prev.layer != curr.layer:
            continue

        seg_len, is_diag = _segment_classification(
            float(prev.x) * cell_size,
            float(prev.y) * cell_size,
            float(curr.x) * cell_size,
            float(curr.y) * cell_size,
        )
        total_length += seg_len
        if is_diag:
            diagonal_length += seg_len

    if total_length < 1e-12:
        return 0.0

    return diagonal_length / total_length


def octilinear_compliance(routed_pcb_path: Path) -> float:
    """Return fraction (0.0-1.0) of total track length at 45/135.

    Orthogonal segments (0/90) are not counted toward the score.
    Parses the KiCad PCB to extract segment angles.

    Returns 0.0 when no track segments are present.
    """
    import re

    content = routed_pcb_path.read_text(encoding="utf-8")
    segment_re = re.compile(
        r"\(\s*segment\s+"
        r"\(\s*start\s+([-\d.]+)\s+([-\d.]+)\s*\)\s+"
        r"\(\s*end\s+([-\d.]+)\s+([-\d.]+)\s*\)",
    )
    matches = segment_re.findall(content)

    if not matches:
        return 0.0

    total_length = 0.0
    diagonal_length = 0.0

    for sx, sy, ex, ey in matches:
        seg_len, is_diag = _segment_classification(
            float(sx),
            float(sy),
            float(ex),
            float(ey),
        )
        if seg_len < 1e-12:
            continue
        total_length += seg_len
        if is_diag:
            diagonal_length += seg_len

    if total_length < 1e-12:
        return 0.0

    return diagonal_length / total_length
