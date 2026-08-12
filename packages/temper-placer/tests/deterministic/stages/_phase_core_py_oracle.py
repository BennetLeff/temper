"""VERBATIM pre-migration oracle for ``deterministic/stages/_phase_core.py``.

Wave 4, **Phase 5, final leaves**. Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/_phase_core.py``
at the dispatch base (origin/main a6da6f975). Do NOT edit: this file is the
Python arm of the differential. If it drifts, the differential proves nothing.

The ``_PhaseCoreMixin`` residual arithmetic is pinned as module-level
functions: ``_get_footprint_radius`` (the footprint-enclosing radius),
``_reserve_slots`` (the within-radius distance filter) and ``_distance``
(Euclidean distance). The ``hasattr(component, "bounds") and
component.bounds`` guard and the ``used_slots`` set mutation stay Python in
the shim and are not part of the oracle -- ``footprint_radius`` takes the
already-resolved ``bounds`` (or ``None``) and ``reserve_slots`` returns the
reserved slot list.

Numerical pins (see the differential):
- ``math.sqrt(w**2 + h**2) / 2 + 1.0``: ``** 2`` is exact int pow for int
  bounds and libm ``pow`` for float bounds (the two differ in the last ulp);
  ``math.sqrt`` is libm ``sqrt``.
- ``_reserve_slots`` / ``_distance``: ``math.sqrt((dx) ** 2 + (dy) ** 2)``
  with ``** 2`` as libm ``pow`` (slot/position coordinates are floats); the
  distance test is inclusive ``<= radius``.
"""

from __future__ import annotations

import math


def footprint_radius(bounds, slot_spacing: float) -> float:
    """The ``_PhaseCoreMixin._get_footprint_radius`` (body only)."""
    if bounds is None:
        return slot_spacing / 2.0
    w, h = bounds
    return math.sqrt(w**2 + h**2) / 2 + 1.0


def reserve_slots(center, radius: float, all_slots) -> list:
    """The ``_PhaseCoreMixin._reserve_slots`` distance filter (body only)."""
    cx, cy = center
    out = []
    for slot in all_slots:
        sx, sy = slot
        dist = math.sqrt((sx - cx) ** 2 + (sy - cy) ** 2)
        if dist <= radius:
            out.append(slot)
    return out


def distance(p1, p2) -> float:
    """The ``_PhaseCoreMixin._distance`` (body only)."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
