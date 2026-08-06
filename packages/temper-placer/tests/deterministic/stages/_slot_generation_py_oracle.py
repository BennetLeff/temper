"""VERBATIM pre-migration oracle for ``deterministic/stages/slot_generation.py``.

Wave 4, Phase 5, first slice (deterministic leaf stages). Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/slot_generation.py``
at the dispatch base (origin/main 6290942be). Do NOT edit: this file is the
Python arm of the differential. If it drifts, the differential proves nothing.

The method bodies of ``SlotGenerationStage._generate_slots_for_zone`` are
pinned as module-level functions (the ``run`` orchestration — iterating
``state.zones`` and building the ``frozenset`` — stays Python in the shim
and is not part of the oracle).
"""


def generate_slots_for_zone(zone, spacing: float) -> list[tuple[float, float]]:
    """Generate a regular grid of placement slots within a zone."""
    (x_min, y_min), (x_max, y_max) = zone.bounds

    slots = []

    # Start from minimum + half spacing to center slots in cells
    x = x_min + spacing / 2
    while x < x_max:
        y = y_min + spacing / 2
        while y < y_max:
            slots.append((x, y))
            y += spacing
        x += spacing

    return slots
