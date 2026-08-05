"""Constraint satisfaction reporting.

This module provides functionality to check whether placement constraints
are satisfied and generate reports. Reporting only - no optimization.

Wave 4, Phase 4: the compute of this module is migrated to Rust in the
``temper-constraint-compiler`` crate (see ``packages/temper-constraint-compiler/
VERIFICATION.md``). ``ConstraintReporter.check`` runs every check in Rust
(``temper_constraint_compiler.check_constraints``) and reassembles the plain
result dicts into ``ConstraintResult`` dataclasses; ``ConstraintReport.to_text``
and ``to_json`` delegate the formatting/shape logic to Rust (``json.dumps``
itself stays Python stdlib). ``ConstraintStatus`` stays a Python enum (member
identity is load-bearing in consumers). The pre-migration implementation is
pinned verbatim as the differential oracle
(``tests/constraints/_reporter_py_oracle.py``).
"""

import json
from dataclasses import dataclass, field
from enum import Enum

import temper_constraint_compiler as _rust  # type: ignore[import-untyped]

from temper_placer.constraints._payload import _build_payload as build_payload


class ConstraintStatus(Enum):
    """Status of a constraint check."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    WARNING = "warning"  # Soft constraint not satisfied
    SKIPPED = "skipped"  # Component not placed


_STATUS_FROM_STRING = {s.value: s for s in ConstraintStatus}


@dataclass
class ConstraintResult:
    """Result of checking a single constraint."""

    constraint_type: str  # e.g., "ComponentSpacing", "Proximity"
    status: ConstraintStatus
    tier: str  # "hard" or "soft"
    components: list[str]  # Components involved
    message: str  # Human-readable description
    actual_value: float | None = None  # Actual measured value
    expected_value: float | None = None  # Expected/threshold value
    details: dict = field(default_factory=dict)  # Additional info

    def is_violation(self) -> bool:
        """True if this is a hard constraint violation."""
        return self.tier == "hard" and self.status == ConstraintStatus.VIOLATED

    def is_warning(self) -> bool:
        """True if this is a soft constraint warning."""
        return self.tier == "soft" and self.status == ConstraintStatus.VIOLATED


def _results_to_dicts(results: list[ConstraintResult]) -> list[dict]:
    """Marshall results into the plain-dict form the Rust side consumes."""
    return [
        {
            "type": r.constraint_type,
            "status": r.status.value,
            "tier": r.tier,
            "components": list(r.components),
            "message": r.message,
            "actual": r.actual_value,
            "expected": r.expected_value,
            "details": r.details,
        }
        for r in results
    ]


@dataclass
class ConstraintReport:
    """Aggregated report of all constraint checks."""

    results: list[ConstraintResult] = field(default_factory=list)

    @property
    def violations(self) -> list[ConstraintResult]:
        """Hard constraint violations."""
        return [r for r in self.results if r.is_violation()]

    @property
    def warnings(self) -> list[ConstraintResult]:
        """Soft constraint warnings."""
        return [r for r in self.results if r.is_warning()]

    @property
    def satisfied(self) -> list[ConstraintResult]:
        """Satisfied constraints."""
        return [r for r in self.results if r.status == ConstraintStatus.SATISFIED]

    @property
    def hard_results(self) -> list[ConstraintResult]:
        """All hard constraint results."""
        return [r for r in self.results if r.tier == "hard"]

    @property
    def soft_results(self) -> list[ConstraintResult]:
        """All soft constraint results."""
        return [r for r in self.results if r.tier == "soft"]

    def to_text(self) -> str:
        """Generate human-readable text report (Rust formatting, byte-identical)."""
        return _rust.report_to_text(_results_to_dicts(self.results))  # type: ignore[attr-defined]

    def to_json(self) -> str:
        """Generate machine-readable JSON report.

        The data-shape logic (summary counts, which entries appear) is Rust
        (``temper_constraint_compiler.report_to_json_data``); ``json.dumps``
        stays Python stdlib.
        """
        data = _rust.report_to_json_data(_results_to_dicts(self.results))  # type: ignore[attr-defined]
        return json.dumps(data, indent=2)

    def has_violations(self) -> bool:
        """True if there are any hard constraint violations."""
        return len(self.violations) > 0


class ConstraintReporter:
    """Check placement constraints and generate reports."""

    def __init__(
        self,
        constraints,
        board_bounds: tuple[float, float, float, float] | None = None,
    ):
        """Initialize reporter.

        Args:
            constraints: Placement constraints to check
            board_bounds: Board bounds as (x_min, y_min, x_max, y_max) for edge distance calculations
        """
        self.constraints = constraints
        self.board_bounds = board_bounds

    def check(self, placements: dict) -> ConstraintReport:
        """Check all constraints against placements.

        Args:
            placements: Dictionary mapping component ref to (x, y) position

        Returns:
            ConstraintReport with all check results
        """
        payload = build_payload(self.constraints, self.board_bounds)
        result_dicts = _rust.check_constraints(payload, placements)  # type: ignore[attr-defined]
        report = ConstraintReport()
        for rd in result_dicts:
            report.results.append(
                ConstraintResult(
                    constraint_type=rd["type"],
                    status=_STATUS_FROM_STRING[rd["status"]],
                    tier=rd["tier"],
                    components=rd["components"],
                    message=rd["message"],
                    actual_value=rd["actual"],
                    expected_value=rd["expected"],
                    details=rd["details"],
                )
            )
        return report
