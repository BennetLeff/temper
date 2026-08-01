"""
Rust-accelerated PCL constraint engine bridge.

This module provides an optional Rust backend for constraint loss computation.
If the `temper_constraints` Rust crate is installed, it is used automatically.
Otherwise, the Python implementation is used with a one-time info log.

R10: Rust is an acceleration, not a requirement. Python fallback is mandatory.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_HAS_RUST: bool = False
_RUST_IMPORT_WARNED: bool = False
_temper_constraints_module: Any = None


def _try_import_rust() -> bool:
    global _HAS_RUST, _RUST_IMPORT_WARNED, _temper_constraints_module
    if _temper_constraints_module is not None:
        return True
    try:
        import temper_constraints  # type: ignore[import-untyped]

        _temper_constraints_module = temper_constraints
        _HAS_RUST = True
        return True
    except ImportError:
        _HAS_RUST = False
        if not _RUST_IMPORT_WARNED:
            logger.info(
                "Rust constraint engine not available, using Python fallback. "
                "Install with: pip install temper-constraints"
            )
            _RUST_IMPORT_WARNED = True
        return False


def has_rust_backend() -> bool:
    return _try_import_rust()


def _call_rust(fn_name: str, *args: Any) -> float:
    """Call a Rust backend function by name, returning a float.

    Raises NotImplementedError if the Rust backend is not available.
    """
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(getattr(_temper_constraints_module, fn_name)(*args))
    raise NotImplementedError("Rust backend not available")


def tier_to_weight_rust(tier_value: int) -> float:
    return _call_rust("tier_to_weight_py", tier_value)


# FFI int enums shared with temper-constraints' pyo3 surface (lib.rs):
# metric 0=edge_to_edge, 1=center_to_center, 2=pin_to_pin; axis
# 0=x, 1=y, 2=major, 3=minor; side 0=top, 1=bottom, 2=left, 3=right.
# The public Python API keeps the names; the wrappers map once.
_METRIC_CODES = {"edge_to_edge": 0, "center_to_center": 1, "pin_to_pin": 2}
_AXIS_CODES = {"x": 0, "y": 1, "major": 2, "minor": 3}
_SIDE_CODES = {"top": 0, "bottom": 1, "left": 2, "right": 3}


def _metric_code(metric: str) -> int:
    try:
        return _METRIC_CODES[metric]
    except KeyError:
        raise ValueError(f"Unknown metric: {metric}") from None


def _axis_code(axis: str) -> int:
    try:
        return _AXIS_CODES[axis]
    except KeyError:
        raise ValueError(f"Unknown axis: {axis}") from None


def _side_code(side: str) -> int:
    try:
        return _SIDE_CODES[side]
    except KeyError:
        raise ValueError(f"Unknown side: {side}") from None


def compute_adjacent_loss_rust(
    positions: list[float],
    idx_a: int,
    idx_b: int,
    max_distance_mm: float,
    weight: float,
    metric: str = "center_to_center",
    pin_a_x: float | None = None,
    pin_a_y: float | None = None,
    pin_b_x: float | None = None,
    pin_b_y: float | None = None,
) -> float:
    return _call_rust(
        "compute_adjacent_loss_py",
        positions,
        idx_a,
        idx_b,
        max_distance_mm,
        weight,
        _metric_code(metric),
        pin_a_x,
        pin_a_y,
        pin_b_x,
        pin_b_y,
    )


def compute_separation_loss_rust(
    positions_a: list[float],
    positions_b: list[float],
    min_distance_mm: float,
    weight: float,
) -> float:
    return _call_rust(
        "compute_separation_loss_py",
        positions_a,
        positions_b,
        min_distance_mm,
        weight,
    )


def compute_enclosing_loss_rust(
    positions: list[float],
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    margin_mm: float,
    weight: float,
) -> float:
    return _call_rust(
        "compute_enclosing_loss_py",
        positions,
        x_min,
        y_min,
        x_max,
        y_max,
        margin_mm,
        weight,
    )


def compute_alignment_loss_rust(
    positions: list[float],
    axis: str,
    tolerance_mm: float,
    weight: float,
) -> float:
    return _call_rust(
        "compute_alignment_loss_py",
        positions,
        _axis_code(axis),
        tolerance_mm,
        weight,
    )


def compute_edge_loss_rust(
    positions: list[float],
    side: str,
    board_width: float,
    board_height: float,
    max_distance_mm: float,
    weight: float,
) -> float:
    return _call_rust(
        "compute_edge_loss_py",
        positions,
        _side_code(side),
        board_width,
        board_height,
        max_distance_mm,
        weight,
    )


def compute_anchored_loss_position_rust(
    positions: list[float],
    target_x: float,
    target_y: float,
    weight: float,
) -> float:
    return _call_rust(
        "compute_anchored_loss_position_py",
        positions,
        target_x,
        target_y,
        weight,
    )


def compute_anchored_loss_region_rust(
    positions: list[float],
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    weight: float,
) -> float:
    return _call_rust(
        "compute_anchored_loss_region_py",
        positions,
        x_min,
        y_min,
        x_max,
        y_max,
        weight,
    )


def compute_loop_area_loss_rust(
    positions: list[float],
    max_area_mm2: float,
    weight: float,
) -> float:
    return _call_rust(
        "compute_loop_area_loss_py",
        positions,
        max_area_mm2,
        weight,
    )


def supported_constraint_types_rust() -> list[str]:
    if _try_import_rust() and _temper_constraints_module is not None:
        return list(_temper_constraints_module.supported_constraint_types_py())
    return []


def rust_version() -> str | None:
    if _try_import_rust() and _temper_constraints_module is not None:
        return str(_temper_constraints_module.version_py())
    return None
