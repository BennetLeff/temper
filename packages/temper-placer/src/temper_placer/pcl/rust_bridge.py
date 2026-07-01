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


def tier_to_weight_rust(tier_value: int) -> float:
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(_temper_constraints_module.tier_to_weight_py(tier_value))
    raise NotImplementedError("Rust backend not available")


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
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(
            _temper_constraints_module.compute_adjacent_loss_py(
                positions, idx_a, idx_b, max_distance_mm, weight,
                metric, pin_a_x, pin_a_y, pin_b_x, pin_b_y,
            )
        )
    raise NotImplementedError("Rust backend not available")


def compute_separation_loss_rust(
    positions_a: list[float],
    positions_b: list[float],
    min_distance_mm: float,
    weight: float,
) -> float:
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(
            _temper_constraints_module.compute_separation_loss_py(
                positions_a, positions_b, min_distance_mm, weight,
            )
        )
    raise NotImplementedError("Rust backend not available")


def compute_enclosing_loss_rust(
    positions: list[float],
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    margin_mm: float,
    weight: float,
) -> float:
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(
            _temper_constraints_module.compute_enclosing_loss_py(
                positions, x_min, y_min, x_max, y_max, margin_mm, weight,
            )
        )
    raise NotImplementedError("Rust backend not available")


def compute_alignment_loss_rust(
    positions: list[float],
    axis: str,
    tolerance_mm: float,
    weight: float,
) -> float:
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(
            _temper_constraints_module.compute_alignment_loss_py(
                positions, axis, tolerance_mm, weight,
            )
        )
    raise NotImplementedError("Rust backend not available")


def compute_edge_loss_rust(
    positions: list[float],
    side: str,
    board_width: float,
    board_height: float,
    max_distance_mm: float,
    weight: float,
) -> float:
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(
            _temper_constraints_module.compute_edge_loss_py(
                positions, side, board_width, board_height, max_distance_mm, weight,
            )
        )
    raise NotImplementedError("Rust backend not available")


def compute_anchored_loss_position_rust(
    positions: list[float],
    target_x: float,
    target_y: float,
    weight: float,
) -> float:
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(
            _temper_constraints_module.compute_anchored_loss_position_py(
                positions, target_x, target_y, weight,
            )
        )
    raise NotImplementedError("Rust backend not available")


def compute_anchored_loss_region_rust(
    positions: list[float],
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    weight: float,
) -> float:
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(
            _temper_constraints_module.compute_anchored_loss_region_py(
                positions, x_min, y_min, x_max, y_max, weight,
            )
        )
    raise NotImplementedError("Rust backend not available")


def compute_loop_area_loss_rust(
    positions: list[float],
    max_area_mm2: float,
    weight: float,
) -> float:
    if _try_import_rust() and _temper_constraints_module is not None:
        return float(
            _temper_constraints_module.compute_loop_area_loss_py(
                positions, max_area_mm2, weight,
            )
        )
    raise NotImplementedError("Rust backend not available")


def supported_constraint_types_rust() -> list[str]:
    if _try_import_rust() and _temper_constraints_module is not None:
        return list(_temper_constraints_module.supported_constraint_types_py())
    return []


def rust_version() -> str | None:
    if _try_import_rust() and _temper_constraints_module is not None:
        return str(_temper_constraints_module.version_py())
    return None
