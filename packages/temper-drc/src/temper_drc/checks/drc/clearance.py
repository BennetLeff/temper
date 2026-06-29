from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Location, Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class ClearanceCheck(Check):
    """
    Checks for minimum clearance violations between components.

    Uses PCL clearance rules based on component net classes.
    Only checks components on the same layer.
    """

    @property
    def name(self) -> str:
        return "drc_clearance"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify component-to-component clearance based on net classes."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        pairs = placement.all_pairs()

        min_clearance_found = float('inf')

        for ref_a, ref_b in pairs:
            comp_a = placement.get_component(ref_a)
            comp_b = placement.get_component(ref_b)

            if not comp_a or not comp_b:
                continue

            # Skip if different layers
            if comp_a.layer != comp_b.layer:
                continue

            required_clearance = constraints.get_clearance(comp_a.net_class, comp_b.net_class)

            # If no rule (0.0), we skip
            if required_clearance <= 0:
                continue

            dist = comp_a.edge_distance_to(comp_b)
            min_clearance_found = min(min_clearance_found, dist)

            if dist < required_clearance:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    code=f"{self.code_prefix}001",
                    message=f"Clearance violation: {dist:.3f}mm < {required_clearance}mm between {ref_a} ({comp_a.net_class}) and {ref_b} ({comp_b.net_class})",
                    category=self.category,
                    check_name=self.name,
                    affected_items=[ref_a, ref_b],
                    location=Location(
                        x=(comp_a.x + comp_b.x) / 2,
                        y=(comp_a.y + comp_b.y) / 2,
                        layer=comp_a.layer
                    ),
                    details={
                        "actual_mm": dist,
                        "required_mm": required_clearance,
                        "layer": comp_a.layer
                    }
                ))

        metrics = {}
        if min_clearance_found != float('inf'):
            metrics["min_clearance_mm"] = min_clearance_found

        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
            metrics=metrics
        )
