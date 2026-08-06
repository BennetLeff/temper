"""
Placement adjustments based on routing feedback.

This module provides functions to move components away from congested areas
detected during the routability feedback loop.

Wave 4, **Phase 4** (placer non-`cp_sat` slice): the per-(bottleneck,
component) push loop of ``adjust_for_congestion`` is implemented in Rust in
the ``temper-io-types/placer_core`` crate (``temper_io_types.
placer_adjust_for_congestion``). The bottleneck iteration (the
``overflow <= 0`` skip and ``bottleneck.to_coordinates(...)``) is Python
object navigation and stays here; the kernel receives precomputed
bottleneck coordinates.

Three numpy semantics are Python seams called back from the kernel, so the
oracle's bits are preserved by construction: ``dist`` = ``np.sqrt(dx**2 +
dy**2)`` (numpy ``**2`` is libm pow, not ``x*x``, and numpy's float32 sqrt
is a correctly-rounded float32 sqrt), ``np.random.uniform(0, 2*pi)`` (the
global numpy RNG, drawn in the oracle's exact iteration order), and
``np.cos``/``np.sin`` of the random angle. The kernel is dtype-aware
(numpy 2.x NEP-50 keeps a float32 array's normalized-push chain in float32,
while the exact-spot random push adds the f64 delta to the widened f32
element and rounds on store).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import temper_io_types as _t

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.router_v6.congestion import CongestionResult


def _dist_f64(dx: float, dy: float) -> float:
    """Python seam: the oracle's ``np.sqrt(dx**2 + dy**2)`` on float64."""
    return float(np.sqrt(np.float64(dx) ** 2 + np.float64(dy) ** 2))


def _dist_f32(dx: float, dy: float) -> float:
    """Python seam: the oracle's ``np.sqrt(dx**2 + dy**2)`` on float32."""
    return float(np.sqrt(np.float32(dx) ** 2 + np.float32(dy) ** 2))


def _uniform() -> float:
    """Python seam: the oracle's ``np.random.uniform(0, 2*pi)``."""
    return float(np.random.uniform(0, 2 * np.pi))


def _cos_sin(angle: float) -> tuple[float, float]:
    """Python seam: the oracle's ``np.cos(angle)`` / ``np.sin(angle)``."""
    return (float(np.cos(angle)), float(np.sin(angle)))


def adjust_for_congestion(
    positions: np.ndarray,
    netlist: Netlist,
    _board: Board,
    congestion: CongestionResult,
    push_strength: float = 2.0,
) -> np.ndarray:
    """
    Adjust component positions by pushing them away from congestion hotspots.

    Args:
        positions: (N, 2) component positions.
        netlist: Netlist.
        board: Board geometry.
        congestion: Result of congestion analysis.
        push_strength: Distance to push in mm.

    Returns:
        (N, 2) adjusted positions.
    """
    if not congestion.bottlenecks:
        return positions.copy()

    # Precompute bottleneck coordinates (Python object navigation: the
    # overflow skip and to_coordinates call stay here).
    coords: list[tuple[float, float]] = []
    for bottleneck in congestion.bottlenecks:
        if bottleneck.overflow <= 0:
            continue
        bx, by = bottleneck.to_coordinates(congestion.grid.cell_size_mm, congestion.grid.origin)
        coords.append((float(bx), float(by)))

    result = np.asarray(positions).copy()
    is_f32 = result.dtype == np.float32
    flat = np.asarray(result, dtype=np.float64).reshape(-1).tolist()
    fixed = [bool(comp.fixed) for comp in netlist.components]

    out = _t.placer_adjust_for_congestion(
        flat,
        is_f32,
        fixed,
        coords,
        push_strength,
        10.0,  # influence_radius (the oracle's literal)
        _dist_f32 if is_f32 else _dist_f64,
        _uniform,
        _cos_sin,
    )
    result.reshape(-1)[...] = np.asarray(out, dtype=result.dtype)

    return result
