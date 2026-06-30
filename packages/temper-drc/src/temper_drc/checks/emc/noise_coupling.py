"""Stub: Noise coupling check — implemented in Rust engine."""

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class NoiseCouplingCheck(Check):
    """Noise coupling check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "emc_noise_coupling"

    @property
    def category(self) -> str:
        return "emc"

    @property
    def description(self) -> str:
        return "Identify and minimize noise coupling between aggressor and victim components."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """Delegated to Rust engine via CheckRunner.run()."""
        return CheckResult(check_name=self.name, passed=True)
