"""
D6 run-orchestration oracle for `deterministic/stages/drc_validation.py`.

Verbatim pre-D6 snapshot of the module at the D6 dispatch base (origin/main
`13525f78`), with ONLY the documented relative-import rewrites below. The body
below `# --- BEGIN PINNED BODY ---` is byte-identical to the module; the D6
Rust port (`temper-orchestration`'s `DRCValidationStage`) is the differential
subject.
"""

import logging
from dataclasses import replace

import temper_drc_rs as _drc

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage

# --- BEGIN PINNED BODY ---

logger = logging.getLogger(__name__)


class DRCValidationError(Exception):
    """Raised when DRC violations exceed configured thresholds."""

    pass


class DRCValidationStage(Stage):
    """
    Validates the board against design rules using the DRCOracle.
    Stores any violations found in the BoardState.
    """

    def __init__(self, fail_on_violations: bool = False, max_violations: int = 0):
        """
        Args:
            fail_on_violations: If True, raise DRCValidationError on any violation.
            max_violations: If > 0, raise DRCValidationError if violations exceed this count.
        """
        self.fail_on_violations = fail_on_violations
        self.max_violations = max_violations

    @property
    def name(self) -> str:
        return "drc_validation"

    def run(self, state: BoardState) -> BoardState:
        if not state.drc_oracle:
            logger.warning("No DRCOracle in state, skipping DRC validation")
            return state

        # Run full validation
        violations = state.drc_oracle.validate_all()

        # Log summary (count-by-type computed by the Rust kernel)
        self._log_summary(violations)

        # Check thresholds — the raise decision (should_raise + message) is
        # the migrated Rust kernel (`threshold_decision`), so it cannot drift
        # from the pinned oracle. The DRCValidationError raise itself stays
        # Python.
        should_raise, message = _drc.threshold_decision_py(
            self.fail_on_violations, self.max_violations, len(violations)
        )
        if should_raise:
            raise DRCValidationError(message)

        # Store as tuple for immutability in frozen BoardState
        return replace(state, drc_violations=tuple(violations))

    def _log_summary(self, violations):
        if not violations:
            logger.info("DRC validation passed: 0 violations")
            return

        # Count by type — the kernel reproduces the oracle's counting and
        # the descending-count sort (ties in first-seen type order).
        total, by_type = _drc.summarize_violations_py(violations)

        logger.warning(f"DRC validation: {total} violations")
        for vtype, count in by_type:
            logger.warning(f"  {vtype}: {count}")
