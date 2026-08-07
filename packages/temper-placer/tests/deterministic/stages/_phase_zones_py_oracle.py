"""VERBATIM pre-migration oracle for ``deterministic/stages/_phase_zones.py``.

Wave 4, **Phase 5, final leaves**. Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/_phase_zones.py``
at the dispatch base (origin/main a596ce61f). Do NOT edit: this file is the
Python arm of the differential. If it drifts, the differential proves nothing.

The ``_PhasePlacementMixin._compute_wirelength`` method body (HPWL) is pinned
as a module-level function. The ``net_pins`` shape is the module's
``dict[str, list[tuple[ref, pin_name]]]``; ``current_placements`` is
``dict[str, tuple[float, float]]``.

Numerical pins (see the differential):
- HPWL is ``(max(xs) - min(xs)) + (max(ys) - min(ys))`` over the positions
  list: ``[candidate_slot]`` followed by every already-placed other net
  member in net_pins LIST order (pin order is preserved, not sorted).
- the net is skipped unless ``any(ref == component_ref for ref, _ in pins)``;
  the net contributes nothing unless ``len(positions) > 1``.
- accumulation is a plain ``total_hpwl += hpwl`` fold; ``min``/``max`` are
  CPython builtins (first-minimum-wins on ties, NaN semantics).
"""

from __future__ import annotations


def compute_wirelength(
    component_ref: str,
    candidate_slot: tuple[float, float],
    net_pins: dict,
    current_placements: dict,
) -> float:
    """The ``_PhasePlacementMixin._compute_wirelength`` (body only)."""
    total_hpwl = 0.0

    for _net_name, pins in net_pins.items():
        component_on_net = any(ref == component_ref for ref, _ in pins)
        if not component_on_net:
            continue

        positions = [candidate_slot]
        for ref, _ in pins:
            if ref != component_ref and ref in current_placements:
                positions.append(current_placements[ref])

        if len(positions) > 1:
            xs = [p[0] for p in positions]
            ys = [p[1] for p in positions]
            hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
            total_hpwl += hpwl

    return total_hpwl
