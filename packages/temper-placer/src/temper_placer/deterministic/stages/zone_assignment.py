"""Zone assignment for the deterministic placement pipeline.

The stage orchestration is implemented in Rust (``temper-orchestration``'s
``ZoneAssignmentStage``, Phase D batch D2 of the Rust Orchestration Engine
plan 2026-08-09-001): it reads ``netlist`` from the state and delegates the
assignment compute to the already-Rust leaf kernel
(``temper_design_bundle_python.deterministic_stages.assign_component_zones``
— the Wave-4 Phase-5 first-slice migration). This module keeps the public
API (the ``ZoneAssignmentStage`` Stage subclass and its ``name``) and
delegates ``run`` across the FFI once per stage call. The differential
oracle for the pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_zone_assignment_py_oracle.py``.
"""

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class ZoneAssignmentStage(Stage):
    @property
    def name(self) -> str:
        return "zone_assignment"

    def run(self, state: BoardState) -> BoardState:
        return _to.run_zone_assignment(state)
