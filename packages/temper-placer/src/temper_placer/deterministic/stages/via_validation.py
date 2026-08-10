"""Via validation and cleanup stage.

This stage removes dangling vias - vias that are not connected to traces
on at least two layers. Dangling vias cause DRC errors and indicate
routing failures.

Special handling for plane connections:
- Vias connecting to inner plane layers (In1.Cu for GND, In2.Cu for power)
  are considered valid even without traces, as they connect via copper pour.

Wave 4, **Phase 5, final leaves**: the via-connectivity counting kernel
(``_count_connected_layers``) and the via-position dedup kernel
(``ViaDeduplicationStage.run``'s sweep) are implemented in Rust in the
``temper-drc-rs`` crate (``temper_drc_rs.count_connected_layers_py`` /
``temper_drc_rs.dedup_via_positions_py``).

Phase D batch D6 of the Rust Orchestration Engine plan (2026-08-09-001): the
**stage orchestration** is implemented in Rust (``temper-orchestration``'s
``ViaValidationStage`` / ``ViaDeduplicationStage`` / ``run_via_validation`` /
``run_via_deduplication``): the state guards, the trace-endpoint and
pin-position index building, the per-via validity sweep (diff-pair skip,
plane-net special case), the ``print`` messages and the ``vias=frozenset``
writes all run Rust-side, crossing the FFI once per stage call. This module
keeps the public API (the ``ViaValidationStage`` / ``ViaDeduplicationStage``
Stage subclasses, their constructors and ``name``) and delegates ``run``
across the FFI. The pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_via_validation_run_py_oracle.py``.
"""

from dataclasses import replace

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class ViaValidationStage(Stage):
    """Validates and cleans up vias after routing.

    Removes vias that are not properly connected, which happens when:
    - Routing failed to complete a connection
    - Via was placed optimistically but target layer route failed
    - Layer transition was abandoned mid-route

    Parameters:
        tolerance_mm: Distance tolerance for considering a trace connected to a via.
                     Default 0.1mm accounts for grid snapping and floating point errors.
        require_both_layers: If True (default), removes vias not connected on both layers.
                            If False, keeps vias connected on at least one layer.
    """

    def __init__(self, tolerance_mm: float = 0.1, require_both_layers: bool = True):
        self.tolerance_mm = tolerance_mm
        self.require_both_layers = require_both_layers

    @property
    def name(self) -> str:
        return "via_validation"

    def run(self, state: BoardState) -> BoardState:
        """Run the via-cleanup orchestration in Rust (Phase D D6); crosses the
        FFI once per stage call."""
        return _to.run_via_validation(state, self.tolerance_mm, self.require_both_layers)


class ViaDeduplicationStage(Stage):
    """Remove duplicate vias at the same position.

    Multiple routing attempts may create redundant vias at the same location.
    This stage keeps only one via per unique position.
    """

    def __init__(self, tolerance_mm: float = 0.05):
        self.tolerance_mm = tolerance_mm

    @property
    def name(self) -> str:
        return "via_deduplication"

    def run(self, state: BoardState) -> BoardState:
        """Run the via-dedup orchestration in Rust (Phase D D6); crosses the
        FFI once per stage call."""
        return _to.run_via_deduplication(state, self.tolerance_mm)
