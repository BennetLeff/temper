from temper_drc.checks.safety._safety_keywords import (
    ISO_COMPONENT_KEYWORDS,
    ISO_ZONE_KEYWORDS,
    resolve_safety_category,
)
from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Location, Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class IsolationCheck(Check):
    """
    Checks if components respect designated 'Isolation' or 'Switch' zones.

    Ensures that only components belonging to the isolation class (e.g. ISO)
    reside within or straddle these zones. All other components must stay clear.
    """

    @property
    def name(self) -> str:
        return "safety_isolation"

    @property
    def category(self) -> str:
        return "safety"

    @property
    def description(self) -> str:
        return "Ensure no components reside in isolation zones (gutters/slots) except isolation devices."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []

        # 1. Identify Isolation Zones -- uses ISO_ZONE_KEYWORDS
        iso_zones = []
        for zone in constraints.zones:
            if any(k in zone.name.lower() for k in ISO_ZONE_KEYWORDS):
                iso_zones.append(zone)

        # 2. Check each component
        for ref, comp in placement.components.items():
            cat = resolve_safety_category(comp.net_class)
            is_iso_device = (cat == "iso") or (
                any(k in comp.net_class.lower() for k in ISO_COMPONENT_KEYWORDS)
                or any(k in comp.footprint.lower() for k in ISO_COMPONENT_KEYWORDS)
            )

            cx, cy = comp.center

            for zone in iso_zones:
                x_min, y_min, x_max, y_max = zone.bounds

                # Check if component is inside the zone
                # We use the center point as a simple check for 'residing' in the zone
                if (x_min <= cx <= x_max and y_min <= cy <= y_max) and not is_iso_device:
                    issues.append(Issue(
                            severity=Severity.ERROR,
                            code=f"{self.code_prefix}001",
                            message=f"Safety violation: Component {ref} ({comp.net_class}) is in isolation zone '{zone.name}'",
                            category=self.category,
                            check_name=self.name,
                            affected_items=[ref],
                            location=Location(x=cx, y=cy, layer=comp.layer),
                            details={
                                "zone_name": zone.name,
                                "component_class": comp.net_class
                            }
                        ))

        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
