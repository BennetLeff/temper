from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Severity, Location
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class HVLVSeparationCheck(Check):
    """
    Checks for safe separation between High Voltage (HV) and Low Voltage (LV) nets.
    
    Safety requirements (IEC 60335) often demand large clearances (e.g. 10mm) 
    between mains-connected circuitry and user-accessible low voltage logic.
    This check applies across layers as well.
    """
    
    @property
    def name(self) -> str:
        return "safety_hv_lv_separation"

    @property
    def category(self) -> str:
        return "safety"

    @property
    def description(self) -> str:
        return "Ensure critical separation between HV and LV domains for safety compliance."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        pairs = placement.all_pairs()
        
        required_gap = constraints.hv_clearance_mm
        
        HV_KEYWORDS = ["hv", "line", "ac", "neutral", "mains"]
        LV_KEYWORDS = ["lv", "signal", "3v3", "5v", "gnd", "analog"]
        
        for ref_a, ref_b in pairs:
            comp_a = placement.get_component(ref_a)
            comp_b = placement.get_component(ref_b)
            
            if not comp_a or not comp_b:
                continue
                
            a_class = comp_a.net_class.lower()
            b_class = comp_b.net_class.lower()
            
            is_a_hv = any(k in a_class for k in HV_KEYWORDS)
            is_b_hv = any(k in b_class for k in HV_KEYWORDS)
            is_a_lv = any(k in a_class for k in LV_KEYWORDS)
            is_b_lv = any(k in b_class for k in LV_KEYWORDS)
            
            # Check if one is HV and the other is LV
            if (is_a_hv and is_b_lv) or (is_b_hv and is_a_lv):
                dist = comp_a.edge_distance_to(comp_b)
                
                if dist < required_gap:
                    issues.append(Issue(
                        severity=Severity.CRITICAL,
                        code=f"{self.code_prefix}001",
                        message=f"HV/LV Safety violation: gap {dist:.2f}mm < {required_gap}mm between {ref_a} (HV) and {ref_b} (LV)",
                        category=self.category,
                        check_name=self.name,
                        affected_items=[ref_a, ref_b],
                        location=Location(
                            x=(comp_a.x + comp_b.x) / 2,
                            y=(comp_a.y + comp_b.y) / 2
                        ),
                        details={
                            "actual_gap_mm": dist,
                            "required_gap_mm": required_gap,
                            "class_a": comp_a.net_class,
                            "class_b": comp_b.net_class
                        }
                    ))
        
        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
