"""VERBATIM pre-migration oracle for ``deterministic/stages/_phase_validation.py``.

Wave 4, **Phase 5, final leaves**. Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/_phase_validation.py``
at the dispatch base (origin/main a596ce61f). Do NOT edit: this file is the
Python arm of the differential. If it drifts, the differential proves nothing.

The ``_PhaseValidationMixin.find_critical_bottleneck_violations`` kernel (the
body from the ``critical_by_cell`` build onward) is pinned as a module-level
function. The ``self.channel_map`` guard / ``cmap`` attribute reads stay
Python in the shim and are not part of the oracle.

VERBATIM SUBTLETY (anti-vacuity pin): the violation dict's ``severity`` key
reads ``bn.severity`` where ``bn`` is the *loop variable of the first loop*
over ``bottlenecks`` -- NOT ``cell_bn.severity``. In CPython a loop variable
stays bound to the last iterated element, so every violation carries the
severity of the LAST bottleneck in the input list, regardless of which cell
matched. A "corrected" implementation (``cell_bn.severity``) diverges whenever
that last bottleneck is not ``"CRITICAL"``; the differential pins the bug.

Numerical pins:
- grid coords are ``int(math.floor((float(x_mm) * 1000.0) / cell_um))`` --
  the `float()` coercion first, then ``* 1000.0``, then ``/ cell_um``, then
  ``math.floor`` (negative coordinates floor toward -inf, not truncate).
- out-of-grid cells (``gx < 0 or gx >= width``) are skipped, matching the
  board-edge 'no penalty' semantics.
- per cell, the FIRST bottleneck wins ties in ``critical_by_cell`` (the
  ``existing is None or bn.score > existing.score`` comparison keeps the
  first-seen on equal score); placements iterate in dict insertion order.
"""

from __future__ import annotations

import math


def find_critical_bottleneck_violations(
    placements: dict,
    bottlenecks: list,
    cell_um: float,
    width: int,
    height: int,
) -> list[dict]:
    """The ``_PhaseValidationMixin.find_critical_bottleneck_violations`` (body only)."""
    critical_by_cell: dict[tuple[int, int], object] = {}
    for bn in bottlenecks:
        if bn.severity != "CRITICAL":
            continue
        key = (bn.x, bn.y)
        existing = critical_by_cell.get(key)
        if existing is None or bn.score > existing.score:
            critical_by_cell[key] = bn

    violations: list[dict] = []
    for ref, pos in placements.items():
        if not isinstance(pos, (tuple, list)) or len(pos) < 2:
            continue
        x_mm, y_mm = pos[0], pos[1]
        gx = int(math.floor((float(x_mm) * 1000.0) / cell_um))
        gy = int(math.floor((float(y_mm) * 1000.0) / cell_um))
        if gx < 0 or gx >= width or gy < 0 or gy >= height:
            continue
        cell_bn = critical_by_cell.get((gx, gy))
        if cell_bn is None:
            continue
        violations.append(
            {
                "ref": ref,
                "x": gx,
                "y": gy,
                "layer": cell_bn.layer,
                "severity": bn.severity,
            }
        )
    return violations
