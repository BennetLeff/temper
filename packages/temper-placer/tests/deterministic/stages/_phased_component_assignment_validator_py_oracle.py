"""VERBATIM pre-migration oracle for the slot-grid kernels of
``deterministic/stages/phased_component_assignment_validator.py``.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment_validator.py``
at the dispatch base (origin/main). Do NOT edit: this file is the Python arm
of the differential. If it drifts, the differential proves nothing.

The four pure slot-grid kernels — ``_flatten_slots``, ``_infer_slot_spacing``,
``_build_slot_index``, ``_slots_within_radius`` — are pinned as module-level
functions. The ``validate_phased_component_assignment_hv`` function stays in
the shim (it binds router_v6 ``StageDRCFailure`` and the phasing mixins).
"""

import math
from collections.abc import Iterable

_DEFAULT_SLOT_SPACING = 5.0


def _flatten_slots(state) -> list[tuple[float, float]]:
    """All grid slots from every zone in state.zone_slots."""
    if not state.zone_slots:
        return []
    out: list[tuple[float, float]] = []
    for _zone, slots in state.zone_slots:
        out.extend(slots)
    return out


def _infer_slot_spacing(slots: list[tuple[float, float]]) -> float:
    """Infer the regular slot-grid spacing from a flat list of slots."""
    if len(slots) < 2:
        return _DEFAULT_SLOT_SPACING
    xs = sorted({sx for sx, _ in slots})
    ys = sorted({sy for _, sy in slots})
    dx_candidates = [b - a for a, b in zip(xs, xs[1:]) if b > a]
    dy_candidates = [b - a for a, b in zip(ys, ys[1:]) if b > a]
    candidates = dx_candidates + dy_candidates
    if not candidates:
        return _DEFAULT_SLOT_SPACING
    return min(candidates)


def _build_slot_index(
    slots: Iterable[tuple[float, float]],
    spacing: float,
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    """Build a 2D bucketed cell map ``(i, j) -> [slots in that cell]``."""
    index: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for slot in slots:
        i = int(round(slot[0] / spacing))
        j = int(round(slot[1] / spacing))
        index.setdefault((i, j), []).append(slot)
    return index


def _slots_within_radius(
    center: tuple[float, float],
    radius: float,
    index: dict[tuple[int, int], list[tuple[float, float]]],
    spacing: float,
) -> list[tuple[float, float]]:
    """Yield all slots within ``radius`` of ``center`` using the cell index."""
    if radius <= 0.0 or not index:
        return []
    k = int(math.ceil(radius / spacing))
    ci = int(round(center[0] / spacing))
    cj = int(round(center[1] / spacing))
    out: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    cx, cy = center
    for di in range(-k, k + 1):
        for dj in range(-k, k + 1):
            cell = (ci + di, cj + dj)
            cell_slots = index.get(cell)
            if not cell_slots:
                continue
            for slot in cell_slots:
                if slot in seen:
                    continue
                seen.add(slot)
                sx, sy = slot
                if math.hypot(sx - cx, sy - cy) <= radius:
                    out.append(slot)
    return out
