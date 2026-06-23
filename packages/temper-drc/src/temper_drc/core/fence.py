"""DRC Fence: Per-stage design rule checking orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from temper_drc.core.result import CheckResult, Issue
from temper_drc.core.runner import CheckRunner

if TYPE_CHECKING:
    from temper_drc.input.constraints import ConstraintSet
    from temper_drc.input.placement import Placement

logger = logging.getLogger(__name__)

_BUDGET_ENFORCEMENT_START = datetime(2026, 7, 6)


def _issue_fingerprint(issue: Issue) -> str:
    """Canonical fingerprint for comparing issues across fence runs."""
    items = ",".join(sorted(issue.affected_items))
    return f"{issue.code}:{issue.message}:{items}"


@dataclass(frozen=True)
class InvariantSpec:
    """
    Declaration of a per-stage invariant that the fence should verify.

    Attributes:
        check_name: Name of the temper_drc check to run (e.g. "drc_component_overlap").
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
        lines = [f"STAGE FENCE DUAL-RUN"]
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

    Features:
    - Violation attribution: diffs pre-stage vs post-stage violations
    - Dual-run mode for strangler fig transitions
    - Performance budget monitoring with soft-launch CI enforcement
    - Incremental check scoping for bounded overhead

    Example:
        runner = CheckRunner()
        runner.add_checks(create_standard_checks())
        fence = DRCFence(runner, fail_on_violation=True)

        result = fence.check(
            stage_name="placement",
            invariants=(InvariantSpec("drc_component_overlap", "No overlaps"),),
            placement=placement,
            constraints=constraints,
        )
        if not result.passed:
            print(result.format())
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
        """
        Run fence checks for a stage's invariants.

        Returns:
            FenceResult with pass/fail status, violations, timing, and overhead.
        """
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

        # Compute attribution: identify new violations
        current_fingerprints = frozenset(_issue_fingerprint(i) for i in current_issues)
        if previous_violations is not None:
            new_fingerprints = current_fingerprints - previous_violations
        else:
            new_fingerprints = current_fingerprints

        # Build attributed violations
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

        # Compute overhead
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

        # Dual-run mode: check divergence with alternative stage output
        if alternative_result is not None:
            consistency = (passed == alternative_result.passed)
            if not consistency:
                level = logging.ERROR if passed != alternative_result.passed else logging.WARNING
                logger.log(level,
                    "Stage '%s' dual-run divergence: PRIMARY=%s, ALTERNATIVE=%s",
                    stage_name,
                    "PASS" if passed else "FAIL",
                    "PASS" if alternative_result.passed else "FAIL",
                )
            result.mode = "dual"
            result.alternative_result = alternative_result
            # Suppress budget warning for dual-run (transient, ~2x overhead expected)
            overhead_pct = None

        # Perf budget check (suppressed for dual-run)
        if overhead_pct is not None and overhead_pct > self.perf_budget_pct:
            logger.warning(
                "Fence overhead %.1f%% exceeds budget %.1f%% for stage '%s'",
                overhead_pct, self.perf_budget_pct, stage_name,
            )
            if self.ci_enforce and datetime.now() >= _BUDGET_ENFORCEMENT_START:
                raise FenceBudgetError(result)

        # Violation enforcement
        if self.fail_on_violation and not result.passed:
            raise FenceViolationError(result)

        return result

    def _find_invariant_desc(self, invariants: tuple[InvariantSpec, ...], check_name: str) -> str:
        for inv in invariants:
            if inv.check_name == check_name:
                return inv.guarantees
        return check_name
