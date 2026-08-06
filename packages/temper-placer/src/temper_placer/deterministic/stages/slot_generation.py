"""Slot generation for the deterministic placement pipeline.

The pure compute is implemented in Rust in the ``temper-design-bundle`` crate
(Wave 4 **Phase 5, first slice** — deterministic leaf stages). This module
keeps the pre-migration public API unchanged and delegates
``_generate_slots_for_zone`` to
``temper_design_bundle_python.deterministic_stages.generate_slots_for_zone``;
the ``run`` orchestration (the ``state.zones`` guard and the ``frozenset``
wrap) stays Python.

Bit-exactness: the Rust kernel reproduces the oracle's naive ``+=`` slot-grid
walk bit-for-bit (starting at ``min + spacing / 2``, strict ``<`` upper
bounds, empty list when ``spacing >= zone extent``). Verified by
``tests/deterministic/stages/test_slot_generation_rust_differential.py``
(oracle: ``tests/deterministic/stages/_slot_generation_py_oracle.py``) and
the PBT suite ``test_slot_generation_pbt.py``; the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from dataclasses import replace

import temper_design_bundle_python as _tdb

from ..state import BoardState
from .base import Stage


class SlotGenerationStage(Stage):
    def __init__(self, slot_spacing_mm: float = 5.0):
        self.slot_spacing_mm = slot_spacing_mm

    @property
    def name(self) -> str:
        return "slot_generation"

    def run(self, state: BoardState) -> BoardState:
        if not state.zones:
            return state

        # Build list of (zone_name, tuple_of_slots) for storage
        zone_slots_list = []
        for zone in state.zones:
            slots = self._generate_slots_for_zone(zone, self.slot_spacing_mm)
            # Store as (zone_name, tuple_of_slot_tuples)
            zone_slots_list.append((zone.name, tuple(slots)))

        return replace(state, zone_slots=frozenset(zone_slots_list))

    def _generate_slots_for_zone(self, zone, spacing: float) -> list[tuple[float, float]]:
        """Generate a regular grid of placement slots within a zone."""
        (x_min, y_min), (x_max, y_max) = zone.bounds
        return list(
            _tdb.deterministic_stages.generate_slots_for_zone(x_min, y_min, x_max, y_max, spacing)
        )
