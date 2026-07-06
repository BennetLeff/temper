"""Acceptance gate — two-tier audit + DRC verification for CP-SAT placements.

Inner gate (audit): fast geometric invariant checks.
Truth gate (DRC): KiCad DRC for physical rule compliance.

Two-tier rule is explicit:
- inner_passed=true, truth_passed=false -> NOT accepted (DRC wins)
- inner_passed=false -> NOT accepted (no need to run DRC)
- inner_passed=true, truth_passed=true -> accepted
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.placer.cp_sat.audit import (
    AuditReport,
    Placement,
    PlacementAuditor,
)
from temper_placer.validation.drc_runner import DrcError, DrcResult, run_drc

if TYPE_CHECKING:
    from temper_placer.pcl.constraints import BaseConstraint
    from temper_placer.validation.drc_runner import DrcWarning

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """Result of running one or both gates.

    Attributes:
        inner_passed: True if the inner gate (audit + physics) passed.
        truth_passed: True if the truth gate (KiCad DRC) passed.
            None if the truth gate was not run.
        audit_violations: Violations from the inner-gate audit checks.
        drc_errors: DRC errors from the truth gate (blockers).
        drc_warnings: DRC warnings from the truth gate (non-blocking).
    """

    inner_passed: bool
    truth_passed: bool | None = None
    audit_violations: list[str] = field(default_factory=list)
    drc_errors: list[DrcError] = field(default_factory=list)
    drc_warnings: list[DrcWarning] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        """True only if both gates pass.

        - inner_passed + truth_passed=None -> NOT accepted (truth not run)
        - inner_passed=false -> NOT accepted
        - inner_passed=true + truth_passed=false -> NOT accepted
        - inner_passed=true + truth_passed=true -> accepted
        """
        return self.inner_passed and self.truth_passed is True

    @property
    def disagreement_signal(self) -> bool:
        """True if inner and truth gates disagree -- a key diagnostic signal.

        This happens when Chebyshev (inner gate) approves a placement that
        Euclidean DRC (truth gate) rejects. The gap is the signal this
        two-tier design exists to detect.
        """
        return self.inner_passed and self.truth_passed is False


class AcceptanceGate:
    """Two-tier acceptance: inner audit (fast) + truth DRC (slow)."""

    def __init__(self, pcb_path: Path | None = None) -> None:
        self._pcb_path = pcb_path

    def inner_gate(
        self,
        placement: Placement,
        constraints: list[BaseConstraint],
        loop_components: dict[str, list[str]] | None = None,
    ) -> AuditReport:
        """Run geometric invariant audit checks on the placement."""
        auditor = PlacementAuditor(placement)
        return auditor.audit(constraints, loop_components=loop_components)

    def truth_gate(self, pcb_path: Path | None = None) -> DrcResult:
        """Run KiCad DRC on the placed/routed PCB."""
        path = pcb_path or self._pcb_path
        if path is None:
            raise ValueError("No PCB path provided for truth gate")
        if not path.exists():
            logger.warning("PCB file %s does not exist; truth gate failed", path)
            return DrcResult(
                error_count=1,
                warning_count=0,
                errors=[
                    DrcError(
                        rule="truth_gate",
                        severity="error",
                        location=(0.0, 0.0),
                        message=f"PCB file does not exist: {path}",
                    )
                ],
            )
        return run_drc(path)

    def accept(
        self,
        placement: Placement,
        constraints: list[BaseConstraint],
        pcb_path: Path | None = None,
        loop_components: dict[str, list[str]] | None = None,
    ) -> tuple[bool, AuditReport, DrcResult | None]:
        """Full two-tier acceptance check.

        Returns (accepted, audit_report, drc_result).
        """
        audit_report = self.inner_gate(placement, constraints, loop_components=loop_components)
        if not audit_report.all_pass:
            return False, audit_report, None

        drc_result = self.truth_gate(pcb_path)
        accepted = drc_result.error_count == 0
        return accepted, audit_report, drc_result
