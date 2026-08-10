# ORACLE COPY -- DO NOT EDIT, DO NOT "FIX".
#
# Verbatim copy of the pre-migration source of
#   packages/temper-placer/src/temper_placer/deterministic/stages/slot_generation.py
# at the D2 dispatch base (origin/main, bd85d76e). Relative imports are
# adapted to absolute paths so the oracle imports from the test tree; every
# other line is the verbatim pre-migration source.
#
# This is the R1a behavioural oracle for the D2 Rust Stage-engine port in
# packages/temper-orchestration (plan 2026-08-09-001, Phase D batch D2). It
# must keep the ORIGINAL pure-Python semantics forever, including any warts.
# If a differential test fails, the Rust side is wrong until proven
# otherwise -- never edit this file to make a test pass.
#
# test_deterministic_d2_rust_differential.py recomputes the sha256 of
# everything below the marker and fails if this file drifts.
# --- BEGIN PINNED BODY ---
from dataclasses import replace

import temper_design_bundle_python as _tdb

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage


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
