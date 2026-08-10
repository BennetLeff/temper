"""
DRC validation stage.

Phase D batch D6 of the Rust Orchestration Engine plan (2026-08-09-001): the
``run()`` orchestration (the no-oracle guard, the ``DRCOracle.validate_all()``
call, the ``_log_summary`` through the temper-drc-rs ``summarize_violations_py``
kernel, the ``threshold_decision_py`` raise decision and the
``drc_violations=tuple(violations)`` write) is implemented in Rust
(``temper-orchestration``'s ``DRCValidationStage`` /
``run_drc_validation``), crossing the FFI once per stage call. This module
keeps the public API unchanged: the ``DRCValidationStage`` Stage subclass, its
constructor and ``name``, and the ``DRCValidationError`` exception -- the
Rust-decision message is raised through the shim's exception type. The
pre-migration implementation is pinned VERBATIM as
``tests/deterministic/_drc_validation_run_py_oracle.py``.
"""

import logging

import temper_orchestration as _to

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
        """Run the full DRC validation in Rust (Phase D D6) and surface the
        raise decision as the module's ``DRCValidationError``."""
        out_state, message = _to.run_drc_validation(
            state, self.fail_on_violations, self.max_violations
        )
        if message is not None:
            raise DRCValidationError(message)
        return out_state
