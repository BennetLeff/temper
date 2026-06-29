from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Location, Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class GroundPlaneCheck(Check):
    """
    Checks if noisy or high-speed components are placed over a ground plane.

    Verifies that 'Switching', 'Power', or 'Clock' components are positioned
    within the bounds of a zone designated as 'GND' or 'Return'.
    """

    @property
    def name(self) -> str:
        return "emc_ground_plane"

    @property
    def category(self) -> str:
        return "emc"

    @property
    def description(self) -> str:
        return "Ensure high-di/dt or high-speed components have a ground plane return path."

    def run(self, placement: Placement, _constraints: ConstraintSet) -> CheckResult:
        issues = []

        NOISY_KEYWORDS = ["power", "switching", "clock", "pwm", "high_freq"]
        GND_KEYWORDS = ["gnd", "ground", "return"]

        # 1. Identify Ground Zones
        gnd_zones = []
        for zone_name, bounds in placement.zones.items():
            if any(k in zone_name.lower() for k in GND_KEYWORDS):
                gnd_zones.append((zone_name, bounds))

        # 2. Check each component
        for ref, comp in placement.components.items():
            comp_class = comp.net_class.lower()
            is_noisy = any(k in comp_class for k in NOISY_KEYWORDS)

            if not is_noisy:
                continue

            # Must be inside at least one ground zone
            inside_gnd = False
            cx, cy = comp.center

            for _name, bounds in gnd_zones:
                x_min, y_min, x_max, y_max = bounds
                if x_min <= cx <= x_max and y_min <= cy <= y_max:
                    inside_gnd = True
                    break

            if not inside_gnd:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    code=f"{self.code_prefix}001",
                    message=f"Noisy component {ref} ({comp.net_class}) is not placed over a ground plane.",
                    category=self.category,
                    check_name=self.name,
                    affected_items=[ref],
                    location=Location(x=cx, y=cy, layer=comp.layer),
                    details={
                        "component_class": comp.net_class,
                        "available_gnd_zones": [z[0] for z in gnd_zones]
                    }
                ))

        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
