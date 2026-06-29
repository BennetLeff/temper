"""DRC check: via-to-via minimum spacing."""

from __future__ import annotations

import math

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Location, Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class ViaSpacingCheck(Check):
    """Checks minimum spacing between all placed vias.

    Reads vias from placement.via_placement (set by the fence adapter).
    When no via data is present, the check is a no-op (returns passed).
    """

    @property
    def name(self) -> str:
        return "drc_via_spacing"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify via-to-via minimum spacing on matching layer pairs."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        via_placement = getattr(placement, "via_placement", None)
        if via_placement is None:
            return CheckResult(check_name=self.name, passed=True)

        vias = getattr(via_placement, "vias", [])
        if not vias:
            return CheckResult(check_name=self.name, passed=True)

        min_spacing = getattr(
            constraints, "default_via_spacing_mm", 0.6
        ) or 0.6

        issues: list[Issue] = []
        n = len(vias)
        for i in range(n):
            for j in range(i + 1, n):
                vi = vias[i]
                vj = vias[j]
                if vi.net_name == vj.net_name:
                    continue
                dx = vi.position[0] - vj.position[0]
                dy = vi.position[1] - vj.position[1]
                center_dist = math.sqrt(dx * dx + dy * dy)
                edge_dist = center_dist - vi.radius - vj.radius
                if edge_dist < min_spacing:
                    issues.append(
                        Issue(
                            severity=Severity.ERROR,
                            code=f"{self.code_prefix}001",
                            message=(
                                f"Via spacing violation: {edge_dist:.3f}mm "
                                f"< {min_spacing}mm between "
                                f"vias on nets '{vi.net_name}' and "
                                f"'{vj.net_name}' at "
                                f"({vi.position[0]:.1f},{vi.position[1]:.1f}) "
                                f"and ({vj.position[0]:.1f},{vj.position[1]:.1f})"
                            ),
                            category=self.category,
                            check_name=self.name,
                            affected_items=[vi.net_name, vj.net_name],
                            location=Location(
                                x=(vi.position[0] + vj.position[0]) / 2,
                                y=(vi.position[1] + vj.position[1]) / 2,
                                layer=None,
                            ),
                        )
                    )

        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )
