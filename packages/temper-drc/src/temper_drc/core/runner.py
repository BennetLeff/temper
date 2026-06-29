"""Check runner for orchestrating multiple checks."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, RunResult

if TYPE_CHECKING:
    from temper_drc.input.constraints import ConstraintSet
    from temper_drc.input.placement import Placement


@dataclass
class CheckRunner:
    """
    Orchestrates running multiple checks with metrics collection.

    The runner maintains a list of checks and provides methods to:
    - Add checks individually or in bulk
    - Run checks with optional category filtering
    - Collect timing and result metrics
    - Hook into check lifecycle with callbacks

    Example:
        runner = CheckRunner()
        runner.add_check(ClearanceCheck())
        runner.add_check(OverlapCheck())

        result = runner.run(placement, constraints)

        if not result.passed:
            for issue in result.all_issues:
                print(f"[{issue.code}] {issue.message}")
    """

    checks: list[Check] = field(default_factory=list)
    on_check_start: Callable[[Check], None] | None = None
    on_check_complete: Callable[[Check, CheckResult], None] | None = None

    def add_check(self, check: Check) -> CheckRunner:
        """
        Add a single check to the runner.

        Args:
            check: Check to add.

        Returns:
            Self for chaining.
        """
        self.checks.append(check)
        return self

    def add_checks(self, checks: list[Check]) -> CheckRunner:
        """
        Add multiple checks to the runner.

        Args:
            checks: List of checks to add.

        Returns:
            Self for chaining.
        """
        self.checks.extend(checks)
        return self

    def clear(self) -> CheckRunner:
        """
        Remove all checks from the runner.

        Returns:
            Self for chaining.
        """
        self.checks.clear()
        return self

    def get_checks_by_category(self, category: str) -> list[Check]:
        """Get all checks in a specific category."""
        return [c for c in self.checks if c.category == category]

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        categories: list[str] | None = None,
        check_names: list[str] | None = None,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> RunResult:
        """
        Run all applicable checks.

        Args:
            placement: Component placement data.
            constraints: PCL constraint set.
            categories: Optional list of categories to run (e.g., ["drc", "safety"]).
                       If None, runs all categories.
            check_names: Optional list of specific check names to run.
                        If None, runs all checks in selected categories.
            modified_regions: Optional list of (xmin, ymin, xmax, ymax) regions
                to limit check execution scope for incremental-capable checks.

        Returns:
            RunResult with all check results and aggregate metrics.
        """
        results: list[CheckResult] = []
        start_time = time.time()

        for check in self.checks:
            # Filter by category
            if categories and check.category not in categories:
                continue

            # Filter by name
            if check_names and check.name not in check_names:
                continue

            # Skip if not applicable
            if not check.is_applicable(placement, constraints):
                continue

            # Run the check
            if self.on_check_start:
                self.on_check_start(check)

            check_start = time.time()
            if modified_regions is not None and check.supports_incremental:
                result = check.run(placement, constraints, modified_regions=modified_regions)
            else:
                result = check.run(placement, constraints)
            result = CheckResult(
                check_name=result.check_name,
                passed=result.passed,
                issues=result.issues,
                elapsed_ms=(time.time() - check_start) * 1000,
                metrics=result.metrics,
            )
            results.append(result)

            if self.on_check_complete:
                self.on_check_complete(check, result)

        total_elapsed = (time.time() - start_time) * 1000

        return RunResult(
            check_results=results,
            total_elapsed_ms=total_elapsed,
        )

    def run_single(
        self,
        check_name: str,
        placement: Placement,
        constraints: ConstraintSet,
    ) -> CheckResult | None:
        """
        Run a single check by name.

        Args:
            check_name: Name of the check to run.
            placement: Component placement data.
            constraints: PCL constraint set.

        Returns:
            CheckResult if found and run, None if check not found.
        """
        for check in self.checks:
            if check.name == check_name and check.is_applicable(placement, constraints):
                return check.run(placement, constraints)
        return None

    @property
    def check_names(self) -> list[str]:
        """List of all check names in this runner."""
        return [c.name for c in self.checks]

    @property
    def categories(self) -> set[str]:
        """Set of all categories represented in this runner."""
        return {c.category for c in self.checks}

    def summary(self) -> str:
        """Get a summary of registered checks."""
        lines = [f"CheckRunner with {len(self.checks)} checks:"]

        by_category: dict[str, list[str]] = {}
        for check in self.checks:
            if check.category not in by_category:
                by_category[check.category] = []
            by_category[check.category].append(check.name)

        for category, names in sorted(by_category.items()):
            lines.append(f"  {category.upper()}: {', '.join(names)}")

        return "\n".join(lines)
