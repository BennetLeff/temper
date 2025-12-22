from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Severity, Location
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement

class CourtyardCheck(Check):
    """
    Checks for courtyard violations.
    
    Ensures components have sufficient safety margin around them for assembly.
    Simulates courtyards by adding a configurable margin to component bodies.
    """
    
    def __init__(self, margin_mm: float = 0.05):
        """
        Initialize check.
        
        Args:
            margin_mm: Safety margin to add to EACH component.
                       The minimum gap between components becomes 2 * margin_mm.
        """
        self._margin_mm = margin_mm

    @property
    def name(self) -> str:
        return "drc_courtyard"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return f"Verify component courtyard spacing (margin: {self._margin_mm}mm)."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        pairs = placement.all_pairs()
        
        required_gap = self._margin_mm * 2
        
        for ref_a, ref_b in pairs:
            comp_a = placement.get_component(ref_a)
            comp_b = placement.get_component(ref_b)
            
            if not comp_a or not comp_b:
                continue
                
            # Skip if different layers
            if comp_a.layer != comp_b.layer:
                continue
                
            dist = comp_a.edge_distance_to(comp_b)
            
            # Use a small epsilon to avoid floating point noise on exact matches
            if dist < required_gap - 1e-6:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    code=f"{self.code_prefix}001",
                    message=f"Courtyard violation: gap {dist:.3f}mm < {required_gap}mm between {ref_a} and {ref_b}",
                    category=self.category,
                    check_name=self.name,
                    affected_items=[ref_a, ref_b],
                    location=Location(
                        x=(comp_a.x + comp_b.x) / 2,
                        y=(comp_a.y + comp_b.y) / 2,
                        layer=comp_a.layer
                    ),
                    details={
                        "actual_gap_mm": dist,
                        "required_gap_mm": required_gap,
                        "margin_per_comp_mm": self._margin_mm
                    }
                ))
        
        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
