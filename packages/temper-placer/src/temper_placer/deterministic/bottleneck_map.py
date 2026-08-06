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

Wave 4, **Phase 5** (deterministic hubs slice): the ``score_at`` hot-path
lookup and the ``_coerce_score`` numeric clamp are implemented in Rust in the
``temper-design-bundle`` crate (``temper_design_bundle_python.deterministic_hubs``).
This module keeps the pre-migration public API unchanged and delegates.
``BottleneckMap`` stays a Python frozen dataclass — ``dataclasses.replace``
and the pinned ``FrozenInstanceError`` behaviour (tests/deterministic/
test_bottleneck_map.py) are load-bearing for the deterministic + router_v6
suites. The loader orchestration (board-state attribute preference, file read,
JSON parse) stays Python; the payload → map building and per-point lookup are
Rust-backed.

Bit-exactness: ``score_at`` pins CPython float floor-division
``int(rel_x // cell_size_mm)`` (CPython's fmod-based ``_float_div_mod``, NOT a
naive ``(a/b).floor()``) and the O(1) row-major index; ``_coerce_score``
rejects bool/None with the oracle's exact ``ValueError`` text and clamps to
``[0.0, 1.0]``. Verified by
``tests/deterministic/test_bottleneck_map_rust_differential.py`` (oracle:
``tests/deterministic/_bottleneck_map_py_oracle.py``) and the PBT suite
``tests/deterministic/test_bottleneck_map_pbt.py``; the structural proof is in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import temper_design_bundle_python as _tdb

if TYPE_CHECKING:
    from temper_placer.deterministic.state import BoardState


logger = logging.getLogger(__name__)

_DH = _tdb.deterministic_hubs


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

        Delegates to the Rust kernel (CPython floor-division + row-major
        lookup).
        """
        return _DH.bottleneck_score_at(
            self.cell_size_mm,
            self.width,
            self.height,
            self.origin_xy[0],
            self.origin_xy[1],
            list(self.scores),
            x,
            y,
        )


def _coerce_score(value: Any) -> float:
    """Coerce a JSON-loaded value into a float in [0, 1].

    Booleans, strings, and ``None`` are rejected; out-of-range numerics
    are clamped so a slightly malformed sidecar cannot crash the filter.

    Delegates to the Rust kernel (rejects bool/None with the oracle's
    ``ValueError`` text; clamps to ``[0.0, 1.0]``).
    """
    return _DH.bottleneck_coerce_score(value)


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
    board_state: BoardState,
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
