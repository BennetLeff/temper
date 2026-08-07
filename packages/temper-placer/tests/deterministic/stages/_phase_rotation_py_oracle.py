"""VERBATIM pre-migration oracle for ``deterministic/stages/_phase_rotation.py``.

Wave 4, **Phase 5, final leaves**. Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/_phase_rotation.py``
at the dispatch base (origin/main a596ce61f). Do NOT edit: this file is the
Python arm of the differential. If it drifts, the differential proves nothing.

The ``_PhaseHVMixin._effective_ghost_pad_radius`` method body (the U2
isolation-slot reduction kernel) is pinned as a module-level function. The
surrounding method behaviour -- the ``use_isolation_slots`` NFR4 toggle and
the ``self._isolation_slots_by_ref.get(component_ref, [])`` lookup -- stays
Python in the shim and is not part of the oracle.

Numerical pins (see the differential):
- ``math.hypot`` is CPython's Dekker double-double ``vector_norm``, NOT libm
  ``hypot`` (they diverge in the last ulp) -- replicated in Rust by
  ``temper-design-bundle::host_math::hypot``.
- the unit vector is ``dx / d_len, dy / d_len`` with ``d_len <= 0.0`` early
  out; the projection is ``sdx * ux + sdy * uy`` accumulated with naive
  ``+=``; ``max(0.0, base_radius - reduction)`` is Python ``max`` (first
  argument on ties).
"""

from __future__ import annotations

import math


def effective_ghost_pad_radius(
    base_radius: float,
    current_pin_absolute: tuple[float, float],
    nearest_other_hv_pin_absolute: tuple[float, float],
    slots: list,
) -> float:
    """The ``_PhaseHVMixin._effective_ghost_pad_radius`` (body only)."""
    dx = nearest_other_hv_pin_absolute[0] - current_pin_absolute[0]
    dy = nearest_other_hv_pin_absolute[1] - current_pin_absolute[1]
    d_len = math.hypot(dx, dy)
    if d_len <= 0.0:
        return base_radius
    ux, uy = dx / d_len, dy / d_len

    reduction = 0.0
    for slot in slots:
        sx0, sy0 = slot.start_offset
        sx1, sy1 = slot.end_offset
        sdx = sx1 - sx0
        sdy = sy1 - sy0
        projection = sdx * ux + sdy * uy
        if projection > 0.0:
            reduction += projection
    return max(0.0, base_radius - reduction)
