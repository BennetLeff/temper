from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Severity, Location
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class FloatingPinsCheck(Check):
    """
    Checks for components with no net connections.
    
    Every component in the placement should be part of at least one net.
    Floating components are flagged as warnings.
    """
    
    @property
    def name(self) -> str:
        return "erc_floating_pins"

    @property
    def category(self) -> str:
        return "erc"

    @property
    def description(self) -> str:
        return "Identify components that are not connected to any net."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        
        # 1. Build a set of all connected components
        connected_refs = set()
        for comp_refs in placement.nets.values():
            connected_refs.update(comp_refs)
            
        # 2. Check each component in placement
        for ref, comp in placement.components.items():
            if ref not in connected_refs:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    code=f"{self.code_prefix}001",
                    message=f"Component '{ref}' is not connected to any net (floating).",
                    category=self.category,
                    check_name=self.name,
                    affected_items=[ref],
                    location=Location(x=comp.x, y=comp.y, layer=comp.layer),
                    details={
                        "ref": ref,
                        "footprint": comp.footprint
                    }
                ))
                
        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
