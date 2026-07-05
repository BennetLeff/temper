"""
Two-tier acceptance gate for placement quality.

Inner gate (fast, per-solve): audit checks + physics oracle.
Truth gate (slow, per-acceptance): KiCad DRC against 6mm rules.

Two-tier rule is explicit:
- inner_passed=true, truth_passed=false → NOT accepted (DRC wins)
- inner_passed=false → NOT accepted (no need to run DRC)
- inner_passed=true, truth_passed=true → accepted
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.validation.drc_runner import DrcError, DrcWarning, DrcResult


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

        - inner_passed + truth_passed=None → NOT accepted (truth not run)
        - inner_passed=false → NOT accepted
        - inner_passed=true + truth_passed=false → NOT accepted
        - inner_passed=true + truth_passed=true → accepted
        """
        return self.inner_passed and self.truth_passed is True

    @property
    def disagreement_signal(self) -> bool:
        """True if inner and truth gates disagree — a key diagnostic signal.

        This happens when Chebyshev (inner gate) approves a placement that
        Euclidean DRC (truth gate) rejects. The gap is the signal this
        two-tier design exists to detect.
        """
        return self.inner_passed and self.truth_passed is False


class AcceptanceGate:
    """Two-tier acceptance gate for placement quality.

    Inner gate: Runs audit checks + physics oracle (fast, per-solve).
    Truth gate: Runs KiCad DRC (slow, per-acceptance).

    Usage::

        gate = AcceptanceGate()
        result = gate.inner_gate(placement, constraints)

        if result.inner_passed:
            result = gate.truth_gate(pcb_path)
            if result.accepted:
                print("Placement accepted.")
    """

    def inner_gate(
        self,
        _placement: object = None,
        _constraints: object = None,
        audit_violations: list[str] | None = None,
    ) -> GateResult:
        """Run inner gate: audit checks + physics oracle.

        For now, this is a structural placeholder. The actual audit checks
        (6 types from constraint-completion U6) and physics oracle scores
        (thermal, clearance_3mm/6mm, dual-rail) are integrated by the
        F2 constraint-completion workstream.

        When audit checks are empty (no violations), inner_gate passes.
        When physics oracle scores are acceptable, inner_gate passes.

        Args:
            _placement: PlacementResult from the solver.
            _constraints: ConstraintCollection with PCL rules.
            audit_violations: Pre-computed audit violations (for testing).

        Returns:
            GateResult with inner_passed state.
        """
        violations = audit_violations or []
        inner_passed = len(violations) == 0

        return GateResult(
            inner_passed=inner_passed,
            audit_violations=violations,
        )

    def truth_gate(self, pcb_path: Path) -> GateResult:
        """Run truth gate: KiCad DRC validation.

        Runs ``drc_runner.run_drc(pcb_path)`` and checks for zero errors.
        Errors block; warnings are surfaced but do not block.

        Args:
            pcb_path: Path to the .kicad_pcb file.

        Returns:
            GateResult with truth_passed state and DRC details.
        """
        from temper_placer.validation.drc_runner import DrcRunnerError, run_drc

        try:
            drc_result: DrcResult = run_drc(pcb_path)
        except (DrcRunnerError, FileNotFoundError) as e:
            return GateResult(
                inner_passed=True,
                truth_passed=False,
                drc_errors=[
                    type("DrcError", (), {
                        "rule": "drc_runner",
                        "severity": "error",
                        "location": (0.0, 0.0),
                        "message": str(e),
                        "components": [],
                    })()
                ],
            )

        truth_passed = len(drc_result.errors) == 0

        return GateResult(
            inner_passed=True,
            truth_passed=truth_passed,
            drc_errors=list(drc_result.errors),
            drc_warnings=list(drc_result.warnings),
        )

    def accept(
        self,
        placement: object,
        constraints: object,
        pcb_path: Path,
        audit_violations: list[str] | None = None,
    ) -> GateResult:
        """Full acceptance flow: inner gate → truth gate.

        Runs inner gate first. Only if it passes, runs truth gate.
        Returns a GateResult with both stages populated.

        Args:
            placement: PlacementResult from the solver.
            constraints: ConstraintCollection with PCL rules.
            pcb_path: Path to the .kicad_pcb file.
            audit_violations: Pre-computed audit violations (for testing).

        Returns:
            GateResult with both inner_passed and truth_passed.
        """
        inner_result = self.inner_gate(placement, constraints, audit_violations)

        if not inner_result.inner_passed:
            return inner_result

        truth_result = self.truth_gate(pcb_path)
        truth_result.audit_violations = inner_result.audit_violations
        return truth_result
