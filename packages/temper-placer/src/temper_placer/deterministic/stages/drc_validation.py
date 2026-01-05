import logging
from dataclasses import replace

from ..state import BoardState
from .base import Stage

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

        # Log summary
        self._log_summary(violations)

        # Check thresholds
        if self.fail_on_violations and violations:
            raise DRCValidationError(f"{len(violations)} DRC violations found")

        if self.max_violations > 0 and len(violations) > self.max_violations:
            raise DRCValidationError(
                f"{len(violations)} violations exceeds max {self.max_violations}"
            )

        # Store as tuple for immutability in frozen BoardState
        return replace(state, drc_violations=tuple(violations))

    def _log_summary(self, violations):
        if not violations:
            logger.info("DRC validation passed: 0 violations")
            return

        # Count by type
        by_type = {}
        for v in violations:
            by_type[v.type] = by_type.get(v.type, 0) + 1

        logger.warning(f"DRC validation: {len(violations)} violations")
        for vtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            logger.warning(f"  {vtype}: {count}")
