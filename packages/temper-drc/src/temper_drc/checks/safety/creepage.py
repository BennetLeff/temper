"""Stub: Creepage check — implemented in Rust engine."""

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class CreepageCheck(Check):
    """Creepage check — delegates to Rust engine via CheckRunner."""

    def __init__(self, min_iso_width_mm: float = 6.0):
        self._min_iso_width_mm = min_iso_width_mm

    @property
    def name(self) -> str:
        return "safety_creepage"

    @property
    def category(self) -> str:
        return "safety"

    @property
    def description(self) -> str:
        return "Verify minimum creepage (isolation width) requirements per IEC 60335."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """Delegated to Rust engine via CheckRunner.run()."""
        return CheckResult(check_name=self.name, passed=True)
