from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class NetConnectivityCheck(Check):
    """
    Checks for net connectivity issues.

    Verifies that all nets have at least two connections.
    Nets with 0 or 1 connection are flagged as errors.
    """

    @property
    def name(self) -> str:
        return "erc_net_connectivity"

    @property
    def category(self) -> str:
        return "erc"

    @property
    def description(self) -> str:
        return "Ensure all nets have at least 2 connections (no single-pin nets)."

    def run(self, placement: Placement, _constraints: ConstraintSet) -> CheckResult:
        issues = []

        for net_name, comp_refs in placement.nets.items():
            count = len(comp_refs)
            if count < 2:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    code=f"{self.code_prefix}001",
                    message=f"Net '{net_name}' has only {count} connection(s). Minimum 2 required.",
                    category=self.category,
                    check_name=self.name,
                    affected_items=comp_refs,
                    location=None, # Net is global or distributed
                    details={
                        "net_name": net_name,
                        "connection_count": count
                    }
                ))

        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
