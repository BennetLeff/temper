"""Check abstract base class and composite check."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from temper_drc.core.result import CheckResult

if TYPE_CHECKING:
    from temper_drc.input.constraints import ConstraintSet
    from temper_drc.input.placement import Placement


class Check(ABC):
    """
    Abstract base class for all design rule checks.

    Subclasses must implement:
    - name: Unique identifier for the check
    - category: One of "erc", "drc", "safety", "emc"
    - run(): Execute the check and return results

    Example:
        class ClearanceCheck(Check):
            @property
            def name(self) -> str:
                return "clearance"

            @property
            def category(self) -> str:
                return "drc"

            def run(self, placement, constraints) -> CheckResult:
                issues = []
                # ... check logic ...
                return CheckResult(
                    check_name=self.name,
                    passed=len(issues) == 0,
                    issues=issues,
                )
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique name identifying this check.

        Used in results, logging, and filtering.
        """

    @property
    @abstractmethod
    def category(self) -> str:
        """
        Check category.

        Must be one of: "erc", "drc", "safety", "emc".
        Used for filtering and grouping results.
        """

    @property
    def description(self) -> str:
        """
        Human-readable description of what this check does.

        Override to provide documentation for users.
        """
        return ""

    @property
    def supports_incremental(self) -> bool:
        """
        Whether this check supports region-scoped incremental execution.

        When True, the check can accept a modified_regions parameter
        to limit checking to specific board regions, reducing overhead
        for per-stage fence invocations.
        """
        return False

    @property
    def code_prefix(self) -> str:
        """
        Code prefix for issues from this check.

        Default format: {CATEGORY}_{NAME}_
        Example: DRC_CLR_ for clearance check.
        """
        cat = self.category.upper()[:3]
        name = self.name.upper()[:3]
        return f"{cat}_{name}_"

    @abstractmethod
    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """
        Run the check on the given placement.

        Args:
            placement: Component placement data.
            constraints: PCL constraint set.
            modified_regions: Optional list of (xmin, ymin, xmax, ymax) regions
                to scope checking to. Checks that support incremental execution
                limit their work to components intersecting these regions.

        Returns:
            CheckResult with any issues found.
        """

    def is_applicable(
        self,
        _placement: Placement,
        _constraints: ConstraintSet,
    ) -> bool:
        """
        Check if this check applies to the given input.

        Override to skip checks that don't apply to certain designs.
        For example, EMC loop area checks might not apply if no
        critical loops are defined.

        Args:
            placement: Component placement data.
            constraints: PCL constraint set.

        Returns:
            True if this check should run, False to skip.
        """
        return True


class CompositeCheck(Check):
    """
    Runs multiple checks and combines their results.

    Use to group related checks or create custom check suites.

    Example:
        safety_suite = CompositeCheck(
            checks=[
                HvLvSeparationCheck(),
                CreepageCheck(),
                IsolationCheck(),
            ],
            name="safety_suite",
        )
        result = safety_suite.run(placement, constraints)
    """

    def __init__(
        self,
        checks: list[Check],
        name: str = "composite",
        description: str = "",
    ):
        """
        Initialize composite check.

        Args:
            checks: List of checks to run.
            name: Name for this composite check.
            description: Optional description.
        """
        self._checks = checks
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return "composite"

    @property
    def description(self) -> str:
        if self._description:
            return self._description
        check_names = ", ".join(c.name for c in self._checks)
        return f"Composite of: {check_names}"

    @property
    def checks(self) -> list[Check]:
        """List of child checks."""
        return self._checks

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """Run all child checks and combine results."""
        result = CheckResult(check_name=self.name, passed=True)

        for check in self._checks:
            if check.is_applicable(placement, constraints):
                if modified_regions is not None and check.supports_incremental:
                    sub_result = check.run(placement, constraints, modified_regions=modified_regions)
                else:
                    sub_result = check.run(placement, constraints)
                result = result.merge(sub_result)
                if not sub_result.passed:
                    result = CheckResult(
                        check_name=result.check_name,
                        passed=False,
                        issues=result.issues,
                        elapsed_ms=result.elapsed_ms,
                        metrics=result.metrics,
                    )

        return result

    def is_applicable(
        self,
        placement: Placement,
        constraints: ConstraintSet,
    ) -> bool:
        """Applicable if any child check is applicable."""
        return any(c.is_applicable(placement, constraints) for c in self._checks)
