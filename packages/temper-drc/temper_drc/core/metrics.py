"""Metrics collection and aggregation for check results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from temper_drc.core.result import RunResult
from temper_drc.core.severity import Severity


@dataclass
class CheckMetrics:
    """
    Metrics for a single check run.

    Attributes:
        check_name: Name of the check.
        category: Check category.
        elapsed_ms: Time taken in milliseconds.
        issue_counts: Count of issues by severity name.
        custom_metrics: Additional check-specific metrics.
    """

    check_name: str
    category: str
    elapsed_ms: float
    issue_counts: dict[str, int] = field(default_factory=dict)
    custom_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def total_issues(self) -> int:
        """Total number of issues (excluding INFO)."""
        return sum(
            count for severity, count in self.issue_counts.items()
            if severity != "INFO"
        )

    @property
    def passed(self) -> bool:
        """True if no ERROR or CRITICAL issues."""
        return (
            self.issue_counts.get("ERROR", 0) == 0 and
            self.issue_counts.get("CRITICAL", 0) == 0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "check_name": self.check_name,
            "category": self.category,
            "elapsed_ms": self.elapsed_ms,
            "issue_counts": self.issue_counts,
            "custom_metrics": self.custom_metrics,
            "total_issues": self.total_issues,
            "passed": self.passed,
        }


@dataclass
class MetricsSummary:
    """
    Aggregated metrics across all checks.

    Provides comprehensive statistics about a check run including:
    - Pass/fail counts
    - Issue counts by severity
    - Issue counts by category
    - Timing breakdown
    - Coverage information

    Attributes:
        total_checks: Number of checks run.
        passed_checks: Number of checks that passed.
        failed_checks: Number of checks that failed.
        total_elapsed_ms: Total time for all checks.
        info_count: Total INFO issues.
        warning_count: Total WARNING issues.
        error_count: Total ERROR issues.
        critical_count: Total CRITICAL issues.
        erc_issues: Issues from ERC checks.
        drc_issues: Issues from DRC checks.
        safety_issues: Issues from safety checks.
        emc_issues: Issues from EMC checks.
        check_timings: Time taken by each check.
        checks_run: Names of checks that were run.
        checks_skipped: Names of checks that were skipped.
    """

    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    total_elapsed_ms: float = 0.0

    # Counts by severity
    info_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    critical_count: int = 0

    # Counts by category
    erc_issues: int = 0
    drc_issues: int = 0
    safety_issues: int = 0
    emc_issues: int = 0

    # Timing breakdown
    check_timings: dict[str, float] = field(default_factory=dict)

    # Coverage metrics
    checks_run: list[str] = field(default_factory=list)
    checks_skipped: list[str] = field(default_factory=list)

    # Custom aggregated metrics
    custom_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """True if all checks passed."""
        return self.failed_checks == 0

    @property
    def total_issues(self) -> int:
        """Total issues (excluding INFO)."""
        return self.warning_count + self.error_count + self.critical_count

    @property
    def total_penalty(self) -> float:
        """Weighted penalty score."""
        return (
            self.warning_count * Severity.WARNING.weight +
            self.error_count * Severity.ERROR.weight +
            self.critical_count * Severity.CRITICAL.weight
        )

    @property
    def coverage(self) -> float:
        """Percentage of checks that were run."""
        total = len(self.checks_run) + len(self.checks_skipped)
        if total == 0:
            return 100.0
        return (len(self.checks_run) / total) * 100.0

    @classmethod
    def from_run_result(
        cls,
        result: RunResult,
        skipped_checks: list[str] | None = None,
    ) -> MetricsSummary:
        """
        Create metrics summary from a RunResult.

        Args:
            result: The RunResult to summarize.
            skipped_checks: Optional list of check names that were skipped.

        Returns:
            MetricsSummary with aggregated statistics.
        """
        summary = cls(
            total_checks=result.total_checks,
            passed_checks=result.passed_checks,
            failed_checks=result.failed_checks,
            total_elapsed_ms=result.total_elapsed_ms,
            info_count=result.info_count,
            warning_count=result.warning_count,
            error_count=result.error_count,
            critical_count=result.critical_count,
            checks_skipped=skipped_checks or [],
        )

        # Aggregate by category and collect timings
        for check_result in result.check_results:
            summary.checks_run.append(check_result.check_name)
            summary.check_timings[check_result.check_name] = check_result.elapsed_ms

            # Count issues by category
            for issue in check_result.issues:
                if issue.category == "erc":
                    summary.erc_issues += 1
                elif issue.category == "drc":
                    summary.drc_issues += 1
                elif issue.category == "safety":
                    summary.safety_issues += 1
                elif issue.category == "emc":
                    summary.emc_issues += 1

            # Merge custom metrics
            for key, value in check_result.metrics.items():
                if key in summary.custom_metrics:
                    summary.custom_metrics[key] += value
                else:
                    summary.custom_metrics[key] = value

        return summary

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "total_elapsed_ms": self.total_elapsed_ms,
            "by_severity": {
                "info": self.info_count,
                "warning": self.warning_count,
                "error": self.error_count,
                "critical": self.critical_count,
            },
            "by_category": {
                "erc": self.erc_issues,
                "drc": self.drc_issues,
                "safety": self.safety_issues,
                "emc": self.emc_issues,
            },
            "total_penalty": self.total_penalty,
            "coverage": self.coverage,
            "check_timings": self.check_timings,
            "checks_run": self.checks_run,
            "checks_skipped": self.checks_skipped,
            "custom_metrics": self.custom_metrics,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def summary_text(self) -> str:
        """Generate human-readable summary text."""
        status = "PASSED" if self.passed else "FAILED"
        lines = [
            f"Check Summary: {status}",
            f"  Checks: {self.passed_checks}/{self.total_checks} passed",
            f"  Time: {self.total_elapsed_ms:.1f}ms",
            "",
            "Issues by Severity:",
            f"  CRITICAL: {self.critical_count}",
            f"  ERROR: {self.error_count}",
            f"  WARNING: {self.warning_count}",
            f"  INFO: {self.info_count}",
            "",
            "Issues by Category:",
            f"  ERC: {self.erc_issues}",
            f"  DRC: {self.drc_issues}",
            f"  Safety: {self.safety_issues}",
            f"  EMC: {self.emc_issues}",
        ]

        if self.checks_skipped:
            lines.extend([
                "",
                f"Skipped: {', '.join(self.checks_skipped)}",
            ])

        return "\n".join(lines)
