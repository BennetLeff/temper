"""Stub: Isolation check — implemented in Rust engine."""

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class IsolationCheck(Check):
    """Isolation check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "safety_isolation"

    @property
    def category(self) -> str:
        return "safety"

    @property
    def description(self) -> str:
        return "Ensure no components reside in isolation zones except isolation devices."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """Delegated to Rust engine via CheckRunner.run()."""
        return CheckResult(check_name=self.name, passed=True)
