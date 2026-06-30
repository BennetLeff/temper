"""Stub: Ground plane check — implemented in Rust engine."""

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class GroundPlaneCheck(Check):
    """Ground plane check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "emc_ground_plane"

    @property
    def category(self) -> str:
        return "emc"

    @property
    def description(self) -> str:
        return "Ensure high-di/dt or high-speed components have a ground plane return path."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """Delegated to Rust engine via CheckRunner.run()."""
        return CheckResult(check_name=self.name, passed=True)
