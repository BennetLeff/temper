from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Severity, Location
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement

class ZoneContainmentCheck(Check):
    """
    Checks if components assigned to a zone are actually placed within it.
    
    Verifies that the component center is within the rectangular bounds
    of the assigned zone.
    """
    
    @property
    def name(self) -> str:
        return "drc_zone_containment"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify that components assigned to a zone are placed within its bounds."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        
        # Iterate over all zones defined in constraints
        for zone in constraints.zones:
            x_min, y_min, x_max, y_max = zone.bounds
            
            # Check explicit component assignments
            for ref in zone.components:
                comp = placement.get_component(ref)
                if not comp:
                    continue
                
                # Check if center is in bounds
                cx, cy = comp.center
                in_bounds = (x_min <= cx <= x_max) and (y_min <= cy <= y_max)
                
                if not in_bounds:
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        code=f"{self.code_prefix}001",
                        message=f"Component {ref} placed outside assigned zone '{zone.name}'",
                        category=self.category,
                        check_name=self.name,
                        affected_items=[ref],
                        location=Location(x=cx, y=cy, layer=comp.layer),
                        details={
                            "zone": zone.name,
                            "zone_bounds": list(zone.bounds),
                            "component_loc": [cx, cy]
                        }
                    ))
                    
        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
