"""Apply placements from BoardState to Component.initial_position.

Phase D batch D7 of the Rust Orchestration Engine plan (2026-08-09-001): the
**run orchestration** (the ``state.netlist`` / ``state.placements`` guards,
the per-component ``dataclasses.replace(initial_position=...)`` reconstruction
and the netlist write) is implemented in Rust (``temper-orchestration``'s
``ApplyPlacementsStage`` / ``run_apply_placements``), crossing the FFI once
per stage call. This stage is pure orchestration -- it has no design-bundle
leaf kernel; the ``dataclasses.replace`` calls are driven through FFI by the
port. The pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_apply_placements_run_py_oracle.py``.
"""

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class ApplyPlacementsStage(Stage):
    """Apply placements from BoardState to Component.initial_position."""

    @property
    def name(self) -> str:
        return "apply_placements"

    def run(self, state: BoardState) -> BoardState:
        """Run the apply-placements orchestration in Rust (Phase D D7);
        crosses the FFI once per stage call."""
        return _to.run_apply_placements(state)
