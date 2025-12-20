"""Result types for check outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from temper_drc.core.severity import Severity


@dataclass
class Location:
    """
    Spatial location of an issue on the PCB.

    Attributes:
        x: X coordinate in mm (None if not applicable).
        y: Y coordinate in mm (None if not applicable).
        layer: PCB layer name (e.g., "F.Cu", "B.Cu").
    """

    x: float | None = None
    y: float | None = None
    layer: str | None = None

    def __str__(self) -> str:
        if self.x is not None and self.y is not None:
            loc = f"({self.x:.2f}, {self.y:.2f})"
            if self.layer:
                loc += f" on {self.layer}"
            return loc
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "x": self.x,
            "y": self.y,
            "layer": self.layer,
        }


@dataclass
class Issue:
    """
    A single check issue found during verification.

    Attributes:
        severity: Issue severity level.
        code: Machine-readable code (e.g., "DRC_CLR_001").
        message: Human-readable description.
        category: Check category ("erc", "drc", "safety", "emc").
        check_name: Name of the check that found this issue.
        affected_items: List of affected component refs or net names.
        location: Spatial location on the PCB (optional).
        details: Additional details as key-value pairs.
        constraint_id: Related PCL constraint ID (optional).
    """

    severity: Severity
    code: str
    message: str
    category: str
    check_name: str
    affected_items: list[str] = field(default_factory=list)
    location: Location | None = None
    details: dict[str, Any] = field(default_factory=dict)
    constraint_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "severity": self.severity.name,
            "code": self.code,
            "message": self.message,
            "category": self.category,
            "check_name": self.check_name,
            "affected_items": self.affected_items,
            "location": self.location.to_dict() if self.location else None,
            "details": self.details,
            "constraint_id": self.constraint_id,
        }

    def __str__(self) -> str:
        items = ", ".join(self.affected_items[:3])
        if len(self.affected_items) > 3:
            items += f" (+{len(self.affected_items) - 3} more)"
        return f"[{self.code}] {self.message} ({items})"


@dataclass
class CheckResult:
    """
    Result of running a single check.

    Attributes:
        check_name: Name of the check that was run.
        passed: Whether the check passed (no errors or critical issues).
        issues: List of issues found.
        elapsed_ms: Time taken to run the check in milliseconds.
        metrics: Custom metrics from this check.
    """

    check_name: str
    passed: bool
    issues: list[Issue] = field(default_factory=list)
    elapsed_ms: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def info_count(self) -> int:
        """Count of INFO severity issues."""
        return sum(1 for i in self.issues if i.severity == Severity.INFO)

    @property
    def warning_count(self) -> int:
        """Count of WARNING severity issues."""
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def error_count(self) -> int:
        """Count of ERROR severity issues."""
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def critical_count(self) -> int:
        """Count of CRITICAL severity issues."""
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)

    @property
    def total_issues(self) -> int:
        """Total number of issues (excluding INFO)."""
        return self.warning_count + self.error_count + self.critical_count

    @property
    def penalty(self) -> float:
        """Compute weighted penalty score from all issues."""
        return sum(issue.severity.weight for issue in self.issues)

    def merge(self, other: CheckResult) -> CheckResult:
        """
        Merge another CheckResult into this one.

        Returns a new CheckResult with combined issues and metrics.
        """
        return CheckResult(
            check_name=self.check_name,
            passed=self.passed and other.passed,
            issues=self.issues + other.issues,
            elapsed_ms=self.elapsed_ms + other.elapsed_ms,
            metrics={**self.metrics, **other.metrics},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
            "elapsed_ms": self.elapsed_ms,
            "metrics": self.metrics,
            "counts": {
                "info": self.info_count,
                "warning": self.warning_count,
                "error": self.error_count,
                "critical": self.critical_count,
            },
        }


@dataclass
class RunResult:
    """
    Result of running multiple checks.

    Attributes:
        check_results: List of individual check results.
        total_elapsed_ms: Total time for all checks in milliseconds.
    """

    check_results: list[CheckResult] = field(default_factory=list)
    total_elapsed_ms: float = 0.0

    @property
    def passed(self) -> bool:
        """True if all checks passed (no errors or critical issues)."""
        return all(r.passed for r in self.check_results)

    @property
    def all_issues(self) -> list[Issue]:
        """All issues from all checks."""
        issues = []
        for result in self.check_results:
            issues.extend(result.issues)
        return issues

    @property
    def total_checks(self) -> int:
        """Number of checks run."""
        return len(self.check_results)

    @property
    def passed_checks(self) -> int:
        """Number of checks that passed."""
        return sum(1 for r in self.check_results if r.passed)

    @property
    def failed_checks(self) -> int:
        """Number of checks that failed."""
        return sum(1 for r in self.check_results if not r.passed)

    @property
    def info_count(self) -> int:
        """Total INFO issues across all checks."""
        return sum(r.info_count for r in self.check_results)

    @property
    def warning_count(self) -> int:
        """Total WARNING issues across all checks."""
        return sum(r.warning_count for r in self.check_results)

    @property
    def error_count(self) -> int:
        """Total ERROR issues across all checks."""
        return sum(r.error_count for r in self.check_results)

    @property
    def critical_count(self) -> int:
        """Total CRITICAL issues across all checks."""
        return sum(r.critical_count for r in self.check_results)

    @property
    def total_penalty(self) -> float:
        """Sum of penalties from all checks."""
        return sum(r.penalty for r in self.check_results)

    def by_category(self, category: str) -> list[CheckResult]:
        """Filter check results by category."""
        return [
            r for r in self.check_results
            if any(i.category == category for i in r.issues) or not r.issues
        ]

    def by_severity(self, severity: Severity) -> list[Issue]:
        """Get all issues of a specific severity."""
        return [i for i in self.all_issues if i.severity == severity]

    def issues_for_component(self, ref: str) -> list[Issue]:
        """Get all issues affecting a specific component."""
        return [i for i in self.all_issues if ref in i.affected_items]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "total_elapsed_ms": self.total_elapsed_ms,
            "summary": {
                "total_checks": self.total_checks,
                "passed_checks": self.passed_checks,
                "failed_checks": self.failed_checks,
                "info": self.info_count,
                "warning": self.warning_count,
                "error": self.error_count,
                "critical": self.critical_count,
                "total_penalty": self.total_penalty,
            },
            "check_results": [r.to_dict() for r in self.check_results],
        }
