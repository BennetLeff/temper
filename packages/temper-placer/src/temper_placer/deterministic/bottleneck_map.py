"""
BottleneckMap: per-cell congestion score grid for seed filtering.

Defines a frozen dataclass with O(1) cell-indexed lookup and a loader
that prefers the value on :class:`BoardState` and falls back to a
``placement.channels.json`` sidecar file. The loader never raises on a
miss; downstream callers decide what ``None`` means.

The grid is a regular Cartesian mesh that covers the board. Cell index
is computed by flooring ``(coord - origin) / cell_size``. Out-of-bounds
samples are clamped to ``0.0`` so that components placed at or beyond
the map's extent never get filtered as "high congestion".

@req(2026-06-23-004, R3)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.deterministic.state import BoardState


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BottleneckMap:
    """Per-cell congestion score grid.

    Attributes:
        cell_size_mm: Edge length of one cell in millimeters.
        width: Number of cells along the X axis.
        height: Number of cells along the Y axis.
        origin_xy: ``(x, y)`` in millimeters of the lower-left cell's
            lower-left corner. Cell ``(col, row)`` covers
            ``[origin_x + col*cell_size, origin_x + (col+1)*cell_size)`` and
            the analogous Y interval.
        scores: 2D row-major sequence of length ``width*height`` with
            congestion scores in ``[0.0, 1.0]``. Higher values mean harder
            to route. Index ``(col, row)`` resolves to ``scores[row*width+col]``.
    """

    cell_size_mm: float
    width: int
    height: int
    origin_xy: tuple[float, float]
    scores: tuple[float, ...]

    def score_at(self, x: float, y: float) -> float:
        """Return the congestion score at world position ``(x, y)``.

        Out-of-bounds samples return ``0.0`` rather than raising, so a
        missing or partial map never causes the caller to over-reject.
        """
        if self.width <= 0 or self.height <= 0 or self.cell_size_mm <= 0:
            return 0.0
        origin_x, origin_y = self.origin_xy
        rel_x = x - origin_x
        rel_y = y - origin_y
        if rel_x < 0 or rel_y < 0:
            return 0.0
        col = int(rel_x // self.cell_size_mm)
        row = int(rel_y // self.cell_size_mm)
        if col >= self.width or row >= self.height:
            return 0.0
        return self.scores[row * self.width + col]


def _coerce_score(value: Any) -> float:
    """Coerce a JSON-loaded value into a float in [0, 1].

    Booleans, strings, and ``None`` are rejected; out-of-range numerics
    are clamped so a slightly malformed sidecar cannot crash the filter.
    """
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Cannot coerce {value!r} to score")
    result = float(value)
    if result < 0.0:
        return 0.0
    if result > 1.0:
        return 1.0
    return result


def _from_sidecar_payload(payload: dict[str, Any]) -> BottleneckMap | None:
    """Build a :class:`BottleneckMap` from a parsed JSON payload.

    Returns ``None`` when the payload is missing the required keys or the
    dimensions are inconsistent. Logs a warning so a malformed sidecar
    is visible without aborting the placer.
    """
    try:
        cell_size = float(payload["cell_size_mm"])
        width = int(payload["width"])
        height = int(payload["height"])
        origin = payload.get("origin_xy") or [0.0, 0.0]
        if len(origin) < 2:
            raise ValueError("origin_xy must have two elements")
        origin_xy = (float(origin[0]), float(origin[1]))
        raw_scores = payload["scores"]
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("placement.channels.json missing required field: %s", exc)
        return None

    expected = width * height
    if width <= 0 or height <= 0:
        logger.warning("placement.channels.json has non-positive dimensions")
        return None
    if len(raw_scores) < expected:
        logger.warning(
            "placement.channels.json has %d scores, expected %d; truncating",
            len(raw_scores),
            expected,
        )
    scores: list[float] = []
    for raw in raw_scores[:expected]:
        try:
            scores.append(_coerce_score(raw))
        except ValueError:
            scores.append(0.0)

    return BottleneckMap(
        cell_size_mm=cell_size,
        width=width,
        height=height,
        origin_xy=origin_xy,
        scores=tuple(scores),
    )


def load_bottleneck_map(
    board_state: "BoardState",
    sidecar_path: str | Path | None = None,
) -> BottleneckMap | None:
    """Load the bottleneck map for ``board_state``.

    Lookup order:

    1. ``board_state.bottleneck_analysis`` if it is already a
       :class:`BottleneckMap` instance (the new per-cell representation).
    2. ``sidecar_path`` if provided and the file exists, parsed as a
       ``placement.channels.json`` payload.
    3. ``None`` when neither source yields a map. The caller is expected
       to treat ``None`` as "no filter" (silent disable).
    """
    attr = getattr(board_state, "bottleneck_analysis", None)
    if isinstance(attr, BottleneckMap):
        return attr

    if sidecar_path is None:
        return None

    path = Path(sidecar_path)
    if not path.is_file():
        return None
    try:
        with open(path) as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read placement.channels.json: %s", exc)
        return None
    if not isinstance(payload, dict):
        logger.warning("placement.channels.json root must be an object")
        return None
    return _from_sidecar_payload(payload)
