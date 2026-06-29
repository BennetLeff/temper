from temper_drc.checks.safety._safety_keywords import (
    ISO_COMPONENT_KEYWORDS,
    resolve_safety_category,
)
from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Severity, Location
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class CreepageCheck(Check):
    """
    Checks for minimum creepage (isolation width) requirements.
    
    Specifically monitors isolation components (Optocouplers, Transformers, Isolators)
    to ensure their package provides sufficient physical distance across the 
    isolation barrier.
    """
    
    def __init__(self, min_iso_width_mm: float = 6.0):  # allow-safety-constant: HV isolation default
        """
        Initialize check.
        
        Args:
            min_iso_width_mm: Minimum required width for isolation packages.
        """
        self._min_iso_width_mm = min_iso_width_mm

    @property
    def name(self) -> str:
        return "safety_creepage"

    @property
    def category(self) -> str:
        return "safety"

    @property
    def description(self) -> str:
        return f"Verify isolation component width for creepage safety (min: {self._min_iso_width_mm}mm)."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        
        for ref, comp in placement.components.items():
            cat = resolve_safety_category(comp.net_class)
            is_iso = (cat == "iso") or (
                any(k in comp.net_class.lower() for k in ISO_COMPONENT_KEYWORDS)
                or any(k in comp.footprint.lower() for k in ISO_COMPONENT_KEYWORDS)
            )
            
            if is_iso:
                # For an isolation component, the 'width' (or max dimension) 
                # defines the separation distance across the barrier.
                package_width = max(comp.width, comp.height)
                
                if package_width < self._min_iso_width_mm:
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        code=f"{self.code_prefix}001",
                        message=f"Creepage violation: component {ref} width {package_width:.1f}mm < {self._min_iso_width_mm}mm",
                        category=self.category,
                        check_name=self.name,
                        affected_items=[ref],
                        location=Location(x=comp.x, y=comp.y, layer=comp.layer),
                        details={
                            "actual_width_mm": package_width,
                            "required_width_mm": self._min_iso_width_mm
                        }
                    ))
        
        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
