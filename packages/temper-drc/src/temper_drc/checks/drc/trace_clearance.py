"""DRC check: trace-to-trace minimum clearance."""

from __future__ import annotations

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Location, Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class TraceClearanceCheck(Check):
    """Checks minimum clearance between routed trace segments.

    Reads segments from placement.trace_placement (set by the fence adapter).
    When no trace data is present, the check is a no-op (returns passed).
    """

    @property
    def name(self) -> str:
        return "drc_trace_clearance"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify trace-to-trace minimum clearance on each layer."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        trace_placement = getattr(placement, "trace_placement", None)
        if trace_placement is None:
            return CheckResult(check_name=self.name, passed=True)

        segments = getattr(trace_placement, "segments", [])
        if not segments:
            return CheckResult(check_name=self.name, passed=True)

        import math

        min_clearance = getattr(
            constraints, "default_trace_clearance_mm", 0.2
        ) or 0.2

        issues: list[Issue] = []
        n = len(segments)
        for i in range(n):
            for j in range(i + 1, n):
                si = segments[i]
                sj = segments[j]
                if si.net_name == sj.net_name:
                    continue
                if si.layer != sj.layer:
                    continue
                dist = _segment_to_segment_distance(
                    si.start, si.end, sj.start, sj.end
                )
                if dist < min_clearance:
                    issues.append(
                        Issue(
                            severity=Severity.ERROR,
                            code=f"{self.code_prefix}001",
                            message=(
                                f"Trace clearance violation: {dist:.3f}mm "
                                f"< {min_clearance}mm between "
                                f"nets '{si.net_name}' and "
                                f"'{sj.net_name}' on {si.layer}"
                            ),
                            category=self.category,
                            check_name=self.name,
                            affected_items=[si.net_name, sj.net_name],
                            location=Location(x=None, y=None, layer=si.layer),
                        )
                    )

        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )


def _segment_to_segment_distance(
    a_start: tuple[float, float],
    a_end: tuple[float, float],
    b_start: tuple[float, float],
    b_end: tuple[float, float],
) -> float:
    """Minimum distance between two line segments in 2D."""
    import math

    def _point_segment_dist(
        px: float, py: float, sx: float, sy: float, ex: float, ey: float
    ) -> float:
        dx = ex - sx
        dy = ey - sy
        if dx == 0 and dy == 0:
            return math.sqrt((px - sx) ** 2 + (py - sy) ** 2)
        t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)))
        proj_x = sx + t * dx
        proj_y = sy + t * dy
        return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)

    return min(
        _point_segment_dist(*a_start, *b_start, *b_end),
        _point_segment_dist(*a_end, *b_start, *b_end),
        _point_segment_dist(*b_start, *a_start, *a_end),
        _point_segment_dist(*b_end, *a_start, *a_end),
    )
