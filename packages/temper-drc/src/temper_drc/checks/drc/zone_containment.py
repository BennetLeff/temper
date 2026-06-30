"""Stub: Zone containment check — implemented in Rust engine."""

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class ZoneContainmentCheck(Check):
    """Zone containment check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "drc_zone_containment"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify that components assigned to a zone are placed within its bounds."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """Delegated to Rust engine via CheckRunner.run()."""
        return CheckResult(check_name=self.name, passed=True)
