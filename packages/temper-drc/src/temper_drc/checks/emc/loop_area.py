from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Location, Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class LoopAreaCheck(Check):
    """
    Checks for excessive area in critical signal loops.

    Approximates loop area using the Bounding Box Area of all components
    connected to the nets defined in the LoopConstraint.
    """

    @property
    def name(self) -> str:
        return "emc_loop_area"

    @property
    def category(self) -> str:
        return "emc"

    @property
    def description(self) -> str:
        return "Minimize radiated emissions by checking critical loop areas."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []

        for loop in constraints.critical_loops:
            # 1. Gather all unique components involved in this loop
            involved_refs = set()
            for net in loop.nets:
                refs = placement.nets.get(net, [])
                involved_refs.update(refs)

            # Need at least 2 components to form a loop/path
            if len(involved_refs) < 2:
                continue

            # 2. Calculate Bounding Box
            min_x, min_y = float('inf'), float('inf')
            max_x, max_y = float('-inf'), float('-inf')
            valid_comps = []

            for ref in involved_refs:
                comp = placement.get_component(ref)
                if comp:
                    valid_comps.append(comp)
                    min_x = min(min_x, comp.x)
                    min_y = min(min_y, comp.y)
                    max_x = max(max_x, comp.x)
                    max_y = max(max_y, comp.y)

            if not valid_comps:
                continue

            width = max(0, max_x - min_x)
            height = max(0, max_y - min_y)
            # Area approximation: Bounding Box
            # TODO: Improve with convex hull or Manhattan path length if needed.
            area = width * height

            if area > loop.max_area_mm2:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    code=f"{self.code_prefix}001",
                    message=f"Critical loop '{loop.name}' area {area:.2f}mm² > {loop.max_area_mm2}mm²",
                    category=self.category,
                    check_name=self.name,
                    affected_items=list(involved_refs),
                    location=Location(
                        x=(min_x + max_x) / 2,
                        y=(min_y + max_y) / 2
                    ),
                    details={
                        "loop_name": loop.name,
                        "actual_area_mm2": area,
                        "max_area_mm2": loop.max_area_mm2,
                        "nets": loop.nets
                    }
                ))

        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
