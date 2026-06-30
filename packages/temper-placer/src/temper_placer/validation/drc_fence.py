"""
DRC Fence: Per-stage design rule checking orchestration.

Moved from the now-removed ``temper-drc`` Python package.

Former locations:
  - ``temper_drc.core.fence`` → DRCFence, InvariantSpec, FenceResult, …
  - ``temper_drc.core.metrics`` → CheckMetrics, MetricsSummary
  - ``temper_drc.core._issue_fingerprint`` → ``_issue_fingerprint`` (here)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from temper_placer.validation.drc_result import (
    CheckResult,
    Issue,
    RunResult,
    Severity,
)
from temper_placer.validation.drc_runner import CheckRunner

if TYPE_CHECKING:
    from temper_placer.validation.drc_types import ConstraintSet, Placement

logger = logging.getLogger(__name__)

_BUDGET_ENFORCEMENT_START = datetime(2026, 7, 6)


# =========================================================================
#  _issue_fingerprint  (was in temper_drc.core.__init__)
# =========================================================================


def _issue_fingerprint(issue: Issue) -> str:
    """Canonical fingerprint for comparing issues across fence runs."""
    items = ",".join(sorted(issue.affected_items))
    return f"{issue.code}:{issue.message}:{items}"


# =========================================================================
#  InvariantSpec / FenceViolation / FenceResult  (was temper_drc.core.fence)
# =========================================================================


@dataclass(frozen=True)
class InvariantSpec:
    """
    Declaration of a per-stage invariant that the fence should verify.

    Attributes:
        check_name: Name of the DRC check to run (e.g. "drc_component_overlap").
        guarantees: Human-readable description of what this invariant ensures.
        affected_regions: Optional bounding boxes to scope incremental checking.
    """

    check_name: str
    guarantees: str
    affected_regions: tuple[tuple[float, float, float, float], ...] | None = None


@dataclass
class FenceViolation:
    """
    A single attributed violation found during fence checking.

    Attributes:
        stage_name: Name of the stage that introduced this violation.
        invariant_description: Human-readable invariant text from InvariantSpec.
        check_name: Name of the DRC check that found the violation.
        issue: The underlying Issue from CheckResult.
        is_new: True if this violation was not present before this stage.
        introduced_count: Count of new violations introduced by this stage.
    """

    stage_name: str
    invariant_description: str
    check_name: str
    issue: Issue
    is_new: bool = True
    introduced_count: int = 0


@dataclass
class FenceResult:
    """
    Result of a fence check run against one stage.

    Attributes:
        stage_name: Name of the stage that was checked.
        passed: True if all invariants passed (no new violations).
        violations: List of attributed violations.
        elapsed_ms: Total wall-clock time for the fence check.
        check_results: Raw results from the CheckRunner.
        overhead_pct: Overhead vs stage runtime (None if stage time unavailable).
        mode: "single" or "dual" run mode.
        alternative_result: FenceResult for the alternative stage in dual mode.
    """

    stage_name: str
    passed: bool = True
    violations: tuple[FenceViolation, ...] = ()
    elapsed_ms: float = 0.0
    check_results: tuple[CheckResult, ...] = ()
    overhead_pct: float | None = None
    mode: str = "single"
    alternative_result: FenceResult | None = None

    def format(self) -> str:
        """Format the fence result for human-readable output."""
        if self.mode == "dual":
            return self._format_dual()
        return self._format_single()

    def _format_single(self) -> str:
        lines = []
        for v in self.violations:
            lines.append("STAGE FENCE VIOLATION")
            lines.append(f"  Stage:        {v.stage_name}")
            lines.append(f"  Invariant:    {v.invariant_description}")
            lines.append(f"  Check:        {v.check_name}")
            if v.introduced_count:
                lines.append(f"  Introduced:   {v.introduced_count} violations")
            lines.append("  Violations:")
            lines.append(f"    - [{v.issue.code}] {v.issue.message}")
            if v.issue.location:
                lines.append(f"      at {v.issue.location}")
        return "\n".join(lines)

    def _format_dual(self) -> str:
        lines = ["STAGE FENCE DUAL-RUN"]
        lines.append(f"  Stage: {self.stage_name}")
        lines.append(f"  Primary:     {'PASS' if self.passed else 'FAIL'} ({len(self.violations)} violations)")
        if self.alternative_result:
            alt = self.alternative_result
            lines.append(f"  Alternative: {'PASS' if alt.passed else 'FAIL'} ({len(alt.violations)} violations)")
            if self.passed != alt.passed:
                lines.append("  Divergence: pass/fail disagreement")
                for v in self.violations:
                    lines.append(f"    Primary violation: [{v.issue.code}] {v.issue.message}")
                for v in alt.violations:
                    lines.append(f"    Alt violation: [{v.issue.code}] {v.issue.message}")
        return "\n".join(lines)


class FenceViolationError(Exception):
    """Raised when fail_on_violation=True and a stage introduces violations."""

    def __init__(self, result: FenceResult):
        self.result = result
        super().__init__(f"Stage '{result.stage_name}' introduced {len(result.violations)} DRC violation(s)")


class FenceBudgetError(Exception):
    """Raised when the performance budget is exceeded and ci_enforce=True after soft-launch."""

    def __init__(self, result: FenceResult):
        self.result = result
        super().__init__(
            f"Stage '{result.stage_name}' fence overhead {result.overhead_pct:.1f}% exceeds {20.0}% budget"
        )


class DRCFence:
    """
    Per-stage design rule checking orchestration layer.

    Wraps a CheckRunner and provides methods to verify stage invariants
    after each pipeline stage executes.
    """

    def __init__(
        self,
        check_runner: CheckRunner,
        fail_on_violation: bool = False,
        perf_budget_pct: float = 20.0,
        perf_budget_floor_ms: float = 50.0,
        ci_enforce: bool = False,
    ):
        self._runner = check_runner
        self.fail_on_violation = fail_on_violation
        self.perf_budget_pct = perf_budget_pct
        self.perf_budget_floor_ms = perf_budget_floor_ms
        self.ci_enforce = ci_enforce

    def check(
        self,
        *,
        stage_name: str,
        invariants: tuple[InvariantSpec, ...],
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
        previous_violations: frozenset[str] | None = None,
        stage_wall_time_ms: float | None = None,
        alternative_result: FenceResult | None = None,
    ) -> FenceResult:
        """Run fence checks for a stage's invariants."""
        t0 = time.time()

        if not invariants:
            return FenceResult(stage_name=stage_name, passed=True)

        check_names = [inv.check_name for inv in invariants]
        run_result = self._runner.run(
            placement, constraints,
            check_names=check_names,
            modified_regions=modified_regions,
        )

        current_issues = run_result.all_issues

        current_fingerprints = frozenset(_issue_fingerprint(i) for i in current_issues)
        if previous_violations is not None:
            new_fingerprints = current_fingerprints - previous_violations
        else:
            new_fingerprints = current_fingerprints

        violations: list[FenceViolation] = []
        for issue in current_issues:
            fp = _issue_fingerprint(issue)
            is_new = fp in new_fingerprints
            violations.append(FenceViolation(
                stage_name=stage_name,
                invariant_description=self._find_invariant_desc(invariants, issue.check_name),
                check_name=issue.check_name,
                issue=issue,
                is_new=is_new,
                introduced_count=len(new_fingerprints),
            ))

        new_violations = [v for v in violations if v.is_new]
        elapsed_ms = (time.time() - t0) * 1000

        overhead_pct = None
        if stage_wall_time_ms is not None and stage_wall_time_ms >= self.perf_budget_floor_ms:
            overhead_pct = (elapsed_ms / stage_wall_time_ms) * 100

        passed = len(new_violations) == 0

        result = FenceResult(
            stage_name=stage_name,
            passed=passed,
            violations=tuple(violations),
            elapsed_ms=elapsed_ms,
            check_results=tuple(run_result.check_results),
            overhead_pct=overhead_pct,
            mode="single",
        )

        if alternative_result is not None:
            consistency = (passed == alternative_result.passed)
            if not consistency:
                level = logging.ERROR if passed != alternative_result.passed else logging.WARNING
                logger.log(
                    level,
                    "Stage '%s' dual-run divergence: PRIMARY=%s, ALTERNATIVE=%s",
                    stage_name,
                    "PASS" if passed else "FAIL",
                    "PASS" if alternative_result.passed else "FAIL",
                )
            result.mode = "dual"
            result.alternative_result = alternative_result
            overhead_pct = None

        if overhead_pct is not None and overhead_pct > self.perf_budget_pct:
            logger.warning(
                "Fence overhead %.1f%% exceeds budget %.1f%% for stage '%s'",
                overhead_pct, self.perf_budget_pct, stage_name,
            )
            if self.ci_enforce and datetime.now() >= _BUDGET_ENFORCEMENT_START:
                raise FenceBudgetError(result)

        if self.fail_on_violation and len(new_violations) > 0:
            raise FenceViolationError(result)

        return result

    def _find_invariant_desc(self, invariants: tuple[InvariantSpec, ...], check_name: str) -> str:
        for inv in invariants:
            if inv.check_name == check_name:
                return inv.guarantees
        return check_name


# =========================================================================
#  CheckMetrics / MetricsSummary  (was temper_drc.core.metrics)
# =========================================================================


@dataclass
class CheckMetrics:
    """Metrics for a single check run."""

    check_name: str
    category: str
    elapsed_ms: float
    issue_counts: dict[str, int] = field(default_factory=dict)
    custom_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def total_issues(self) -> int:
        return sum(
            count for severity, count in self.issue_counts.items()
            if severity != "INFO"
        )

    @property
    def passed(self) -> bool:
        return (
            self.issue_counts.get("ERROR", 0) == 0
            and self.issue_counts.get("CRITICAL", 0) == 0
        )

    def to_dict(self) -> dict[str, Any]:
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
    """Aggregated metrics across all checks."""

    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    total_elapsed_ms: float = 0.0

    info_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    critical_count: int = 0

    erc_issues: int = 0
    drc_issues: int = 0
    safety_issues: int = 0
    emc_issues: int = 0

    check_timings: dict[str, float] = field(default_factory=dict)
    checks_run: list[str] = field(default_factory=list)
    checks_skipped: list[str] = field(default_factory=list)
    custom_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.failed_checks == 0

    @property
    def total_issues(self) -> int:
        return self.warning_count + self.error_count + self.critical_count

    @property
    def total_penalty(self) -> float:
        return (
            self.warning_count * Severity.WARNING.weight
            + self.error_count * Severity.ERROR.weight
            + self.critical_count * Severity.CRITICAL.weight
        )

    @property
    def coverage(self) -> float:
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

        for check_result in result.check_results:
            summary.checks_run.append(check_result.check_name)
            summary.check_timings[check_result.check_name] = check_result.elapsed_ms

            for issue in check_result.issues:
                if issue.category == "erc":
                    summary.erc_issues += 1
                elif issue.category == "drc":
                    summary.drc_issues += 1
                elif issue.category == "safety":
                    summary.safety_issues += 1
                elif issue.category == "emc":
                    summary.emc_issues += 1

            for key, value in check_result.metrics.items():
                if key in summary.custom_metrics:
                    summary.custom_metrics[key] += value
                else:
                    summary.custom_metrics[key] = value

        return summary

    def to_dict(self) -> dict[str, Any]:
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
        return json.dumps(self.to_dict(), indent=indent)

    def summary_text(self) -> str:
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
