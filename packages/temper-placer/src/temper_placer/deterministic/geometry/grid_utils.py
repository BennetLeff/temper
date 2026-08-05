"""Grid utility helpers for the deterministic router (snapping, nudging).

The pure compute is implemented in Rust in the ``temper-geometry`` crate
(Wave 4 **Phase 5, first slice** — deterministic leaf stages). This module
keeps the pre-migration public API unchanged and delegates.

Bit-exactness: ``snap_to_grid`` pins CPython's round-half-to-even
``round(pos / grid_size) * grid_size`` (Rust ``f64::round`` is
half-away-from-zero and would drift on every ``.5`` tick; the Rust kernel
also normalises the ``int(-0.0)`` sign case); ``add_endpoint_nudge`` pins
the ``** 2`` / ``** 0.5`` libm-``pow`` arithmetic and the strict
``> 1e-4`` threshold. Verified by
``tests/deterministic/test_grid_utils_rust_differential.py`` (oracle:
``tests/deterministic/_grid_utils_py_oracle.py``) and the PBT suite
``tests/deterministic/test_grid_utils_pbt.py``; the structural proof is in
``packages/temper-geometry/VERIFICATION.md``.
"""

from __future__ import annotations

import temper_geometry as _tg


def snap_to_grid(pos: tuple[float, float], grid_size: float = 0.25) -> tuple[float, float]:
    """Snap position to nearest grid point."""
    return _tg.snap_to_grid(pos[0], pos[1], grid_size)


def add_endpoint_nudge(
    path: list[tuple[float, float]],
    actual_start: tuple[float, float],
    actual_end: tuple[float, float],
) -> list[tuple[float, float]]:
    """Add short segments connecting grid-snapped path to actual pad centers."""
    if not path:
        return []
    flat = [x for p in path for x in p]
    result = _tg.add_endpoint_nudge(
        flat, actual_start[0], actual_start[1], actual_end[0], actual_end[1]
    )
    return [(result[i], result[i + 1]) for i in range(0, len(result), 2)]


__all__ = ["snap_to_grid", "add_endpoint_nudge"]
