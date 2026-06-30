"""Stub: Courtyard check — implemented in Rust engine."""

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class CourtyardCheck(Check):
    """Courtyard check — delegates to Rust engine via CheckRunner."""

    def __init__(self, margin_mm: float = 0.05):
        self._margin_mm = margin_mm

    @property
    def name(self) -> str:
        return "drc_courtyard"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify courtyard clearance between component bodies."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """Delegated to Rust engine via CheckRunner.run()."""
        return CheckResult(check_name=self.name, passed=True)
