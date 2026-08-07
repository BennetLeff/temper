"""VERBATIM pre-migration oracle for ``deterministic/stages/via_validation.py``.

Wave 4, **Phase 5, final leaves**. Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/via_validation.py``
at the dispatch base (origin/main a596ce61f). Do NOT edit: this file is the
Python arm of the differential. If it drifts, the differential proves nothing.

Two kernels are pinned as module-level functions:

- ``ViaValidationStage._count_connected_layers`` (the per-layer trace/pin
  distance sweep). The ``_is_plane_net`` / ``is_plane_layer`` predicates are
  precomputed by the shim and passed in as ``is_plane`` / ``plane_layers``.
- ``ViaDeduplicationStage.run``'s position-dedup sweep (kept-positions +
  duplicate count). The shim maps the kept indices back onto the via objects.

Numerical pins:
- ``count_connected_layers``: ``tol_sq = tol * tol`` is a PLAIN MULTIPLY
  (NOT ``tol ** 2``), while every distance is ``(vx - tx) ** 2`` (CPython
  ``**`` = libm ``pow``). The Rust must replicate the split.
- the per-layer sweep uses ``<= tol_sq`` and ``break`` on the first hit;
  because only existence matters, set iteration order is irrelevant.
- plane layers short-circuit before the trace/pin lookups.
- ``dedup_via_positions``: ``tol_sq = tolerance**2`` (libm ``pow``), first-
  seen-wins in INPUT order, ``<=`` boundary, ``duplicates`` counted per
  rejected element.
"""

from __future__ import annotations


def count_connected_layers(
    via_position: tuple[float, float],
    via_layers: list,
    tolerance: float,
    trace_index: dict,
    pin_index: dict,
    is_plane: bool,
    plane_layers: set,
) -> int:
    """The ``ViaValidationStage._count_connected_layers`` (body only)."""
    connected_layers = set()
    tol = tolerance
    tol_sq = tol * tol
    vx, vy = via_position

    for layer in via_layers:
        if is_plane and layer in plane_layers:
            connected_layers.add(layer)
            continue

        if layer in trace_index:
            for tx, ty in trace_index[layer]:
                dist_sq = (vx - tx) ** 2 + (vy - ty) ** 2
                if dist_sq <= tol_sq:
                    connected_layers.add(layer)
                    break

        if layer not in connected_layers and layer in pin_index:
            for px, py in pin_index[layer]:
                dist_sq = (vx - px) ** 2 + (vy - py) ** 2
                if dist_sq <= tol_sq:
                    connected_layers.add(layer)
                    break

    return len(connected_layers)


def dedup_via_positions(
    positions: list[tuple[float, float]],
    tolerance: float,
) -> tuple[list[tuple[float, float]], int]:
    """The ``ViaDeduplicationStage.run`` position-dedup sweep (body only)."""
    unique_positions: list[tuple[float, float]] = []
    seen_positions: list[tuple[float, float]] = []
    tol_sq = tolerance**2
    duplicates = 0

    for vx, vy in positions:
        is_duplicate = False
        for sx, sy in seen_positions:
            if (vx - sx) ** 2 + (vy - sy) ** 2 <= tol_sq:
                is_duplicate = True
                duplicates += 1
                break
        if not is_duplicate:
            unique_positions.append((vx, vy))
            seen_positions.append((vx, vy))

    return unique_positions, duplicates
