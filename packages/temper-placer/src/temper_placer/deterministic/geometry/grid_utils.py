"""Grid utility helpers for the deterministic router (snapping, nudging).

The pure compute is implemented in Rust in the ``temper-geometry`` crate
(Wave 4 **Phase 5, first slice** — deterministic leaf stages). This module
keeps the pre-migration public API unchanged and delegates.

Bit-exactness: ``snap_to_grid`` pins CPython's round-half-to-even
``round(pos / grid_size) * grid_size`` (Rust ``f64::round`` is
half-away-from-zero and would drift on every ``.5`` tick; the Rust kernel
also normalises the ``int(-0.0)`` sign case); ``add_endpoint_nudge`` pins
the ``** 2`` / ``** 0.5`` libm-``pow`` arithmetic and the strict
``> 1e-4`` threshold. The tuple contract is 2-tuples: a path element
without a ``[1]`` raises the oracle's ``IndexError`` (see
``add_endpoint_nudge`` — non-2-tuple element shapes are a recorded,
fail-closed deviation). Verified by
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
    if len(flat) % 2 != 0:
        # The oracle's tuple contract fails with IndexError when an element
        # has no [1] (e.g. a 1-tuple: `path[0][1]`). Fail closed with the
        # SAME class before the kernel: an odd flat length makes the flat
        # kernel pair coordinates ACROSS element boundaries (silent shape
        # corruption) or panic (RuntimeError via catch_unwind).
        # Recorded deviation: the oracle PRESERVES the original shape of a
        # non-2-tuple element in its output (it reads only [0]/[1] of the
        # first/last element and extends the path verbatim), while the shim
        # refuses any non-2-tuple element with IndexError. The flat kernel
        # contract cannot express element boundaries (the end-nudge reads
        # the flat's LAST pair), so full shape parity would need a kernel
        # API change for an input class the router never produces (always
        # 2-tuples). Fail-closed, never corrupt.
        raise IndexError("tuple index out of range")
    result = _tg.add_endpoint_nudge(
        flat, actual_start[0], actual_start[1], actual_end[0], actual_end[1]
    )
    return [(result[i], result[i + 1]) for i in range(0, len(result), 2)]


__all__ = ["snap_to_grid", "add_endpoint_nudge"]
