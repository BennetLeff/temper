"""
Board and Zone data structures.

This module defines the PCB board geometry and placement zones:
- Board: Overall board dimensions, outline, mounting holes
- Zone: Named regions for component placement constraints
- LayerStackup: Layer definitions for routing estimation

Delegation shim (Wave 4 Phase 3): the data model lives in Rust
(``temper_design_bundle_python``, see packages/temper-design-bundle/src/
board.rs). This module keeps the numpy float32 surface as module-level
deterministic wrappers (R10/KTD6 — the priority.py precedent of keeping
non-data helpers in the delegation module; consumers were adapted to
``polygon_array(board)`` / ``get_bounds_array(board)`` /
``get_relative_bounds_array(board)`` inside this migration PR per R12),
the module constants and layer-helper functions derived from the
``LayerIndex`` pyclass, and the frame-inspecting ``_test_only_2layer``
test helper as a module function (KTD7).
"""

from __future__ import annotations

from typing import TypeAlias

import numpy as np
from temper_design_bundle_python import (  # noqa: F401 — re-exports: the shim's public API
    Board,
    Component,
    GroundDomain,
    Layer,
    LayerIndex,
    LayerStackup,
    MountingHole,
    Pad,
    Rect,
    Trace,
    Via,
    Zone,
)

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement


# Canonical 4-layer order (top to bottom).
STANDARD_LAYER_ORDER: tuple[LayerIndex, ...] = (
    LayerIndex.F_CU,
    LayerIndex.IN1_CU,
    LayerIndex.IN2_CU,
    LayerIndex.B_CU,
)

# Inner plane layers (GND/PWR) on a 4-layer board.
PLANE_LAYER_INDICES: frozenset[LayerIndex] = frozenset({LayerIndex.IN1_CU, LayerIndex.IN2_CU})

_LAYER_INDEX_TO_KICAD_NAME: dict[LayerIndex, str] = {
    LayerIndex.F_CU: "F.Cu",
    LayerIndex.IN1_CU: "In1.Cu",
    LayerIndex.IN2_CU: "In2.Cu",
    LayerIndex.B_CU: "B.Cu",
}

# Canonical layer names for the Temper 4-layer board.
# Derived from STANDARD_LAYER_ORDER / _LAYER_INDEX_TO_KICAD_NAME.
CANONICAL_4LAYER_LAYER_NAMES: frozenset[str] = frozenset(str(idx) for idx in STANDARD_LAYER_ORDER)
CANONICAL_LAYER_COUNT: int = len(STANDARD_LAYER_ORDER)

LAYER_IDX_TO_NAME: dict[LayerIndex, str] = _LAYER_INDEX_TO_KICAD_NAME
LAYER_NAME_TO_IDX: dict[str, LayerIndex] = {
    name: idx for idx, name in _LAYER_INDEX_TO_KICAD_NAME.items()
}


def _coerce_layer_index(name_or_index: str | LayerIndex) -> LayerIndex:
    if isinstance(name_or_index, LayerIndex):
        return name_or_index
    return LAYER_NAME_TO_IDX[name_or_index]


def is_plane_layer(name_or_index: str | LayerIndex) -> bool:
    """Return True if the layer is a plane layer (In1.Cu or In2.Cu)."""
    return _coerce_layer_index(name_or_index) in PLANE_LAYER_INDICES


def is_signal_layer(name_or_index: str | LayerIndex) -> bool:
    """Return True if the layer is a signal layer (F.Cu or B.Cu)."""
    return not is_plane_layer(name_or_index)


def side_to_layer_name(side: int) -> str:
    """Map a board side (0=top, 1=bottom) to its KiCad layer name.

    Raises ValueError for sides other than 0 or 1.
    """
    if side == 0:
        return "F.Cu"
    if side == 1:
        return "B.Cu"
    raise ValueError(f"side must be 0 or 1, got {side!r}")


def layer_name_to_index(name: str) -> LayerIndex:
    """Map a KiCad layer name to its LayerIndex. Raises KeyError on miss."""
    return LAYER_NAME_TO_IDX[name]


def polygon_array(board: Board) -> Array | None:
    """Get outline as a (P, 2) float32 array (R10 shim wrapper)."""
    if not board.outline_polygon:
        return None
    return np.array(board.outline_polygon, dtype=np.float32)


def get_bounds_array(board: Board) -> Array:
    """Get [x_min, y_min, x_max, y_max] absolute board bounds (R10)."""
    ox, oy = board.origin
    return np.array([ox, oy, ox + board.width, oy + board.height], dtype=np.float32)


def get_relative_bounds_array(board: Board) -> Array:
    """Get [0, 0, width, height] relative board bounds (R10)."""
    return np.array([0.0, 0.0, board.width, board.height], dtype=np.float32)


def _test_only_2layer() -> LayerStackup:
    """TEST-ONLY: Create a 2-layer stackup for focused unit tests.

    Not a production path. The canonical Temper board is 4-layer.
    Use ``LayerStackup.default_4layer()`` for any production or integration
    code. Kept as a module function (KTD7): it walks the caller's frame,
    which has no honest Rust equivalent.

    Raises RuntimeError if called from outside a test file.
    """
    import sys
    import warnings

    frame = sys._getframe(1)
    caller_file = frame.f_code.co_filename
    if "/test" not in caller_file and "/tests/" not in caller_file:
        raise RuntimeError(
            "_test_only_2layer() may only be called from test files. "
            f"Called from {caller_file}. Use default_4layer() instead."
        )

    warnings.warn(
        "_test_only_2layer() is for test use only. Use default_4layer() for production.",
        stacklevel=2,
    )
    return LayerStackup(
        layers=(
            Layer("F.Cu", "signal", copper_weight=1.0, is_routable=True),
            Layer("B.Cu", "signal", copper_weight=1.0, is_routable=True),
        ),
        thickness=1.6,
    )
