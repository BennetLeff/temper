"""Slot generation for the deterministic placement pipeline.

The stage orchestration is implemented in Rust (``temper-orchestration``'s
``SlotGenerationStage``, Phase D batch D2 of the Rust Orchestration Engine
plan 2026-08-09-001): it reads ``zones`` from the state and delegates the
slot-grid walk to the already-Rust leaf kernel (``temper_design_bundle_python
.deterministic_stages.generate_slots_for_zone`` — the Wave-4 Phase-5
first-slice migration). This module keeps the public API (the
``SlotGenerationStage`` Stage subclass, its constructor and ``name``) and
delegates ``run`` across the FFI once per stage call. The differential
oracle for the pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_slot_generation_py_oracle.py``.
"""

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class SlotGenerationStage(Stage):
    def __init__(self, slot_spacing_mm: float = 5.0):
        self.slot_spacing_mm = slot_spacing_mm

    @property
    def name(self) -> str:
        return "slot_generation"

    def run(self, state: BoardState) -> BoardState:
        return _to.run_slot_generation(state, self.slot_spacing_mm)
