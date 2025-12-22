from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Severity, Location
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement

class ComponentOverlapCheck(Check):
    """
    Checks for physical overlap between component bodies.
    
    This is a critical DRC violation.
    Only checks components on the same layer.
    """
    
    @property
    def name(self) -> str:
        return "drc_component_overlap"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Detect overlap between component bodies on the same layer."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        pairs = placement.all_pairs()
        
        overlap_count = 0
        
        for ref_a, ref_b in pairs:
            comp_a = placement.get_component(ref_a)
            comp_b = placement.get_component(ref_b)
            
            if not comp_a or not comp_b:
                continue
                
            # Skip if different layers
            if comp_a.layer != comp_b.layer:
                continue
                
            if comp_a.overlaps(comp_b):
                area = comp_a.overlap_area(comp_b)
                overlap_count += 1
                
                issues.append(Issue(
                    severity=Severity.CRITICAL,
                    code=f"{self.code_prefix}001",
                    message=f"Component overlapped: {ref_a} covers {ref_b} by {area:.2f}mm²",
                    category=self.category,
                    check_name=self.name,
                    affected_items=[ref_a, ref_b],
                    location=Location(
                        x=(comp_a.x + comp_b.x) / 2,
                        y=(comp_a.y + comp_b.y) / 2,
                        layer=comp_a.layer
                    ),
                    details={
                        "overlap_area_mm2": area,
                        "layer": comp_a.layer
                    }
                ))
        
        metrics = {
            "overlaps": overlap_count
        }

        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
            metrics=metrics
        )
