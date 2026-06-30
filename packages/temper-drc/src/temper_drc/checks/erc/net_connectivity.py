"""Stub: Net connectivity check — implemented in Rust engine."""

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class NetConnectivityCheck(Check):
    """Net connectivity check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "erc_net_connectivity"

    @property
    def category(self) -> str:
        return "erc"

    @property
    def description(self) -> str:
        return "Ensure all nets have at least 2 connections (no single-pin nets)."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """Delegated to Rust engine via CheckRunner.run()."""
        return CheckResult(check_name=self.name, passed=True)
