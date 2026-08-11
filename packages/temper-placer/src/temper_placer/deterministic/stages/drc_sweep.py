"""Post-routing DRC sweep to remove violating geometry.

This stage runs after routing to identify and remove tracks/vias that
cause DRC violations. It's a cleanup pass that prevents bad geometry
from being exported.

The `TrackDeduplicationStage` dedup compute is implemented in Rust in the
``temper-drc-rs`` crate (Wave 4 **Phase 5, batch 2** — deterministic leaf
stages): the direction-normalised `round(x/tol) * tol` (CPython
round-half-to-even) segment key and the duplicate count delegate to
``temper_drc_rs.deduplicate_traces_py``.

Phase D batch D6 of the Rust Orchestration Engine plan (2026-08-09-001): the
**stage orchestration** of all three stages is implemented in Rust
(``temper-orchestration``'s ``DRCSweepStage`` / ``TrackDeduplicationStage`` /
``ShortCircuitDetectionStage`` / ``run_drc_sweep`` /
``run_track_deduplication`` / ``run_short_circuit_detection``): the state
guards, the isinstance filters, the DRCOracle call-backs, the track/via
rebuilds with the non-Trace pass-through, the removed-nets accounting, the
pin_net_map build (CPython ``round(x, 2)`` keys) and the ``print`` messages
all run Rust-side, crossing the FFI once per stage call. This module keeps
the public API (the three Stage subclasses, their constructors and ``name``)
and delegates ``run`` across the FFI. The pre-migration implementation is
pinned VERBATIM in ``tests/deterministic/_drc_sweep_run_py_oracle.py``.
"""

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class DRCSweepStage(Stage):
    """Post-routing DRC sweep that removes violating geometry.

    This stage:
    1. Uses the DRC oracle to check all tracks and vias
    2. Removes geometry that causes clearance violations
    3. Removes tracks that short to other nets
    4. Reports what was removed for debugging

    Should run after ViaValidationStage but before final DRC validation.
    """

    def __init__(self, tolerance: float = 0.01):
        """Initialize DRC sweep.

        Args:
            tolerance: Position tolerance in mm for matching geometry
        """
        self.tolerance = tolerance

    @property
    def name(self) -> str:
        return "drc_sweep"

    def run(self, state: BoardState) -> BoardState:
        """Run the DRC sweep orchestration in Rust (Phase D D6); crosses the
        FFI once per stage call."""
        return _to.run_drc_sweep(state, self.tolerance)


class TrackDeduplicationStage(Stage):
    """Remove duplicate track segments.

    Multiple routing attempts may create redundant traces at the same
    position. This stage removes duplicates.
    """

    def __init__(self, tolerance_mm: float = 0.05):
        self.tolerance_mm = tolerance_mm

    @property
    def name(self) -> str:
        return "track_deduplication"

    def run(self, state: BoardState) -> BoardState:
        """Run the track-dedup orchestration in Rust (Phase D D6); crosses the
        FFI once per stage call."""
        return _to.run_track_deduplication(state, self.tolerance_mm)


class ShortCircuitDetectionStage(Stage):
    """Detect and remove tracks that short to other nets.

    This stage analyzes track connectivity and removes segments
    that connect to pads of different nets (shorts).
    """

    def __init__(self, tolerance_mm: float = 0.1):
        self.tolerance_mm = tolerance_mm

    @property
    def name(self) -> str:
        return "short_circuit_detection"

    def run(self, state: BoardState) -> BoardState:
        """Run the short-circuit detection orchestration in Rust (Phase D D6);
        crosses the FFI once per stage call."""
        return _to.run_short_circuit_detection(state, self.tolerance_mm)
