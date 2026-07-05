"""Acceptance gate — two-tier audit + DRC verification for CP-SAT placements.

Inner gate (audit): fast geometric invariant checks.
Truth gate (DRC): KiCad DRC for physical rule compliance.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


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
