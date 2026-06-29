"""Constraint satisfaction reporting.

This module provides functionality to check whether placement constraints
are satisfied and generate reports. Reporting only - no optimization.
"""

import json
import math
from dataclasses import dataclass, field
from enum import Enum

from temper_placer.io.config_loader import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    PlacementConstraints,
    ProximityRule,
    RoutingCorridor,
    ThermalConstraint,
)


class ConstraintStatus(Enum):
    """Status of a constraint check."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    WARNING = "warning"  # Soft constraint not satisfied
    SKIPPED = "skipped"  # Component not placed


@dataclass
class ConstraintResult:
    """Result of checking a single constraint."""

    constraint_type: str  # e.g., "ComponentSpacing", "Proximity"
    status: ConstraintStatus
    tier: str  # "hard" or "soft"
    components: list[str]  # Components involved
    message: str  # Human-readable description
    actual_value: float | None = None  # Actual measured value
    expected_value: float | None = None  # Expected/threshold value
    details: dict = field(default_factory=dict)  # Additional info

    def is_violation(self) -> bool:
        """True if this is a hard constraint violation."""
        return self.tier == "hard" and self.status == ConstraintStatus.VIOLATED

    def is_warning(self) -> bool:
        """True if this is a soft constraint warning."""
        return self.tier == "soft" and self.status == ConstraintStatus.VIOLATED


@dataclass
class ConstraintReport:
    """Aggregated report of all constraint checks."""

    results: list[ConstraintResult] = field(default_factory=list)

    @property
    def violations(self) -> list[ConstraintResult]:
        """Hard constraint violations."""
        return [r for r in self.results if r.is_violation()]

    @property
    def warnings(self) -> list[ConstraintResult]:
        """Soft constraint warnings."""
        return [r for r in self.results if r.is_warning()]

    @property
    def satisfied(self) -> list[ConstraintResult]:
        """Satisfied constraints."""
        return [r for r in self.results if r.status == ConstraintStatus.SATISFIED]

    @property
    def hard_results(self) -> list[ConstraintResult]:
        """All hard constraint results."""
        return [r for r in self.results if r.tier == "hard"]

    @property
    def soft_results(self) -> list[ConstraintResult]:
        """All soft constraint results."""
        return [r for r in self.results if r.tier == "soft"]

    def to_text(self) -> str:
        """Generate human-readable text report."""
        lines = ["=== Constraint Satisfaction Report ===", ""]

        # Hard constraints
        hard = self.hard_results
        if hard:
            lines.append("HARD CONSTRAINTS (must satisfy):")
            for result in hard:
                symbol = "✓" if result.status == ConstraintStatus.SATISFIED else "✗"
                annotation = " ← VIOLATION" if result.is_violation() else ""
                lines.append(f"  {symbol} {result.message}{annotation}")
            lines.append("")

        # Soft constraints
        soft = self.soft_results
        if soft:
            lines.append("SOFT CONSTRAINTS (prefer):")
            for result in soft:
                if result.status == ConstraintStatus.SATISFIED:
                    symbol = "✓"
                elif result.status == ConstraintStatus.VIOLATED:
                    symbol = "⚠"
                else:
                    symbol = "○"
                lines.append(f"  {symbol} {result.message}")
            lines.append("")

        # Summary
        lines.append("SUMMARY:")
        hard_satisfied = len([r for r in hard if r.status == ConstraintStatus.SATISFIED])
        soft_satisfied = len([r for r in soft if r.status == ConstraintStatus.SATISFIED])

        if hard:
            lines.append(f"  Hard: {hard_satisfied}/{len(hard)} satisfied")
        if soft:
            lines.append(f"  Soft: {soft_satisfied}/{len(soft)} satisfied")

        if self.violations:
            lines.append(f"  VIOLATIONS: {len(self.violations)}")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Generate machine-readable JSON report."""
        data = {
            "summary": {
                "total_constraints": len(self.results),
                "hard_satisfied": len(
                    [r for r in self.hard_results if r.status == ConstraintStatus.SATISFIED]
                ),
                "hard_total": len(self.hard_results),
                "soft_satisfied": len(
                    [r for r in self.soft_results if r.status == ConstraintStatus.SATISFIED]
                ),
                "soft_total": len(self.soft_results),
                "violations": len(self.violations),
                "warnings": len(self.warnings),
            },
            "violations": [
                {
                    "type": r.constraint_type,
                    "components": r.components,
                    "message": r.message,
                    "actual": r.actual_value,
                    "expected": r.expected_value,
                    "details": r.details,
                }
                for r in self.violations
            ],
            "warnings": [
                {
                    "type": r.constraint_type,
                    "components": r.components,
                    "message": r.message,
                    "actual": r.actual_value,
                    "expected": r.expected_value,
                }
                for r in self.warnings
            ],
            "all_results": [
                {
                    "type": r.constraint_type,
                    "status": r.status.value,
                    "tier": r.tier,
                    "components": r.components,
                    "message": r.message,
                    "actual": r.actual_value,
                    "expected": r.expected_value,
                }
                for r in self.results
            ],
        }
        return json.dumps(data, indent=2)

    def has_violations(self) -> bool:
        """True if there are any hard constraint violations."""
        return len(self.violations) > 0


class ConstraintReporter:
    """Check placement constraints and generate reports."""

    def __init__(
        self,
        constraints: PlacementConstraints,
        board_bounds: tuple[float, float, float, float] | None = None,
    ):
        """Initialize reporter.

        Args:
            constraints: Placement constraints to check
            board_bounds: Board bounds as (x_min, y_min, x_max, y_max) for edge distance calculations
        """
        self.constraints = constraints
        self.board_bounds = board_bounds

    def check(self, placements: dict[str, tuple[float, float]]) -> ConstraintReport:
        """Check all constraints against placements.

        Args:
            placements: Dictionary mapping component ref to (x, y) position

        Returns:
            ConstraintReport with all check results
        """
        report = ConstraintReport()

        # Check spacing rules
        for rule in self.constraints.component_spacing_rules:
            result = self._check_spacing(rule, placements)
            report.results.append(result)

        # Check proximity rules (in groups)
        for group in self.constraints.component_groups:
            for prox_rule in group.proximity_rules:
                result = self._check_proximity(prox_rule, placements)
                report.results.append(result)

        # Check thermal constraints
        for thermal in self.constraints.thermal_constraints:
            result = self._check_thermal(thermal, placements)
            report.results.append(result)

        # Check group spread
        for group in self.constraints.component_groups:
            result = self._check_group_spread(group, placements)
            report.results.append(result)

        # Check escape clearances
        for escape in self.constraints.escape_clearances:
            results = self._check_escape_clearance(escape, placements)
            report.results.extend(results)

        # Check routing corridors
        for corridor in self.constraints.routing_corridors:
            results = self._check_routing_corridor(corridor, placements)
            report.results.extend(results)

        return report

    def _check_spacing(self, rule: ComponentSpacingRule, placements: dict) -> ConstraintResult:
        """Check ComponentSpacingRule."""
        comp_a, comp_b = rule.component_a, rule.component_b

        # Check if both components are placed
        if comp_a not in placements or comp_b not in placements:
            return ConstraintResult(
                constraint_type="ComponentSpacing",
                status=ConstraintStatus.SKIPPED,
                tier=rule.tier,
                components=[comp_a, comp_b],
                message=f"ComponentSpacing: {comp_a} - {comp_b} (not placed)",
            )

        # Calculate distance
        pos_a = placements[comp_a]
        pos_b = placements[comp_b]
        distance = self._distance(pos_a, pos_b)

        # Check against threshold
        satisfied = distance >= rule.min_separation_mm
        status = ConstraintStatus.SATISFIED if satisfied else ConstraintStatus.VIOLATED

        message = f"ComponentSpacing: {comp_a} - {comp_b} ({distance:.1f}mm {'≥' if satisfied else '<'} {rule.min_separation_mm}mm)"

        return ConstraintResult(
            constraint_type="ComponentSpacing",
            status=status,
            tier=rule.tier,
            components=[comp_a, comp_b],
            message=message,
            actual_value=distance,
            expected_value=rule.min_separation_mm,
        )

    def _check_proximity(self, rule: ProximityRule, placements: dict) -> ConstraintResult:
        """Check ProximityRule."""
        comp_a, comp_b = rule.component_a, rule.component_b

        # Check if both components are placed
        if comp_a not in placements or comp_b not in placements:
            return ConstraintResult(
                constraint_type="Proximity",
                status=ConstraintStatus.SKIPPED,
                tier=rule.tier,
                components=[comp_a, comp_b],
                message=f"Proximity: {comp_a} - {comp_b} (not placed)",
            )

        # Calculate distance
        pos_a = placements[comp_a]
        pos_b = placements[comp_b]
        distance = self._distance(pos_a, pos_b)

        # Check against threshold
        satisfied = distance <= rule.max_distance_mm
        status = ConstraintStatus.SATISFIED if satisfied else ConstraintStatus.VIOLATED

        message = f"Proximity: {comp_a} - {comp_b} ({distance:.1f}mm {'≤' if satisfied else '>'} {rule.max_distance_mm}mm)"

        return ConstraintResult(
            constraint_type="Proximity",
            status=status,
            tier=rule.tier,
            components=[comp_a, comp_b],
            message=message,
            actual_value=distance,
            expected_value=rule.max_distance_mm,
        )

    def _check_thermal(self, thermal: ThermalConstraint, placements: dict) -> ConstraintResult:
        """Check ThermalConstraint edge preference.

        Note: ThermalConstraint.components is a list, but we check each component individually.
        For simplicity, we check the first placed component only.
        """
        # Get first placed component from the thermal components list
        placed_comps = [c for c in thermal.components if c in placements]

        if not placed_comps:
            return ConstraintResult(
                constraint_type="Thermal",
                status=ConstraintStatus.SKIPPED,
                tier="soft",  # Thermal is always soft
                components=thermal.components,
                message=f"Thermal: {', '.join(thermal.components)} (not placed)",
            )

        comp = placed_comps[0]  # Check first one

        if not thermal.prefer_edge or not self.board_bounds:
            # No edge preference or no bounds to check against
            return ConstraintResult(
                constraint_type="Thermal",
                status=ConstraintStatus.SATISFIED,
                tier="soft",
                components=[comp],
                message=f"Thermal: {comp} (no edge preference)",
            )

        pos = placements[comp]
        edge_distance = self._min_edge_distance(pos, self.board_bounds)

        # Check against threshold - use max_distance_from_edge_mm
        threshold = thermal.max_distance_from_edge_mm
        satisfied = edge_distance <= threshold
        status = ConstraintStatus.SATISFIED if satisfied else ConstraintStatus.VIOLATED

        message = f"Thermal: {comp} edge distance ({edge_distance:.1f}mm {'≤' if satisfied else '>'} {threshold:.1f}mm preferred)"

        return ConstraintResult(
            constraint_type="Thermal",
            status=status,
            tier="soft",
            components=[comp],
            message=message,
            actual_value=edge_distance,
            expected_value=threshold,
        )

    def _check_group_spread(self, group: ComponentGroup, placements: dict) -> ConstraintResult:
        """Check ComponentGroup max_spread_mm."""
        # Get placed components in group
        placed_comps = [c for c in group.components if c in placements]

        if len(placed_comps) < 2:
            return ConstraintResult(
                constraint_type="GroupSpread",
                status=ConstraintStatus.SKIPPED,
                tier="soft",  # Group spread is always soft
                components=group.components,
                message=f"GroupSpread: {group.name} (< 2 components placed)",
            )

        # Calculate bounding box diagonal
        positions = [placements[c] for c in placed_comps]
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]

        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        diagonal = math.sqrt(width**2 + height**2)

        # Check against threshold
        satisfied = diagonal <= group.max_spread_mm
        status = ConstraintStatus.SATISFIED if satisfied else ConstraintStatus.VIOLATED

        message = f"GroupSpread: {group.name} ({diagonal:.1f}mm {'≤' if satisfied else '>'} {group.max_spread_mm}mm)"

        return ConstraintResult(
            constraint_type="GroupSpread",
            status=status,
            tier="soft",
            components=placed_comps,
            message=message,
            actual_value=diagonal,
            expected_value=group.max_spread_mm,
        )

    def _check_escape_clearance(
        self, escape: EscapeClearance, placements: dict
    ) -> list[ConstraintResult]:
        """Check EscapeClearance - no other components in clearance zone."""
        results = []
        comp = escape.component

        if comp not in placements:
            results.append(
                ConstraintResult(
                    constraint_type="EscapeClearance",
                    status=ConstraintStatus.SKIPPED,
                    tier=escape.tier,
                    components=[comp],
                    message=f"EscapeClearance: {comp} (not placed)",
                )
            )
            return results

        pos = placements[comp]
        clearance = escape.clearance_mm

        if clearance is None:
            # Clearance not computed - skip check
            results.append(
                ConstraintResult(
                    constraint_type="EscapeClearance",
                    status=ConstraintStatus.SKIPPED,
                    tier=escape.tier,
                    components=[comp],
                    message=f"EscapeClearance: {comp} (clearance not computed)",
                )
            )
            return results

        # Check each other component
        violations = []
        for other_ref, other_pos in placements.items():
            if other_ref == comp:
                continue

            distance = self._distance(pos, other_pos)
            if distance < clearance:
                violations.append((other_ref, distance))

        if not violations:
            results.append(
                ConstraintResult(
                    constraint_type="EscapeClearance",
                    status=ConstraintStatus.SATISFIED,
                    tier=escape.tier,
                    components=[comp],
                    message=f"EscapeClearance: {comp} ({clearance:.1f}mm zone clear)",
                )
            )
        else:
            # Report each violation
            for other_ref, distance in violations:
                results.append(
                    ConstraintResult(
                        constraint_type="EscapeClearance",
                        status=ConstraintStatus.VIOLATED,
                        tier=escape.tier,
                        components=[comp, other_ref],
                        message=f"EscapeClearance: {other_ref} in {comp} zone ({distance:.1f}mm < {clearance:.1f}mm)",
                        actual_value=distance,
                        expected_value=clearance,
                    )
                )

        return results

    def _check_routing_corridor(
        self, corridor: RoutingCorridor, placements: dict
    ) -> list[ConstraintResult]:
        """Check RoutingCorridor - no components blocking path."""
        results = []
        from_comp = corridor.from_component
        to_comp = corridor.to_component

        # Check if endpoints are placed
        if from_comp not in placements or to_comp not in placements:
            results.append(
                ConstraintResult(
                    constraint_type="RoutingCorridor",
                    status=ConstraintStatus.SKIPPED,
                    tier=corridor.tier,
                    components=[from_comp, to_comp],
                    message=f"RoutingCorridor: {corridor.name} (endpoints not placed)",
                )
            )
            return results

        if not corridor.keep_clear:
            # Not a keep-clear corridor
            results.append(
                ConstraintResult(
                    constraint_type="RoutingCorridor",
                    status=ConstraintStatus.SATISFIED,
                    tier=corridor.tier,
                    components=[from_comp, to_comp],
                    message=f"RoutingCorridor: {corridor.name} (no keep-clear requirement)",
                )
            )
            return results

        pos_from = placements[from_comp]
        pos_to = placements[to_comp]
        half_width = corridor.width_mm / 2.0

        # Check each other component
        violations = []
        for other_ref, other_pos in placements.items():
            if other_ref in (from_comp, to_comp):
                continue

            distance = self._point_to_segment_distance(other_pos, pos_from, pos_to)
            if distance < half_width:
                violations.append((other_ref, distance))

        if not violations:
            results.append(
                ConstraintResult(
                    constraint_type="RoutingCorridor",
                    status=ConstraintStatus.SATISFIED,
                    tier=corridor.tier,
                    components=[from_comp, to_comp],
                    message=f"RoutingCorridor: {corridor.name} ({corridor.width_mm}mm corridor clear)",
                )
            )
        else:
            # Report each violation
            for other_ref, distance in violations:
                results.append(
                    ConstraintResult(
                        constraint_type="RoutingCorridor",
                        status=ConstraintStatus.VIOLATED,
                        tier=corridor.tier,
                        components=[from_comp, to_comp, other_ref],
                        message=f"RoutingCorridor: {other_ref} in {corridor.name} path ({distance:.1f}mm < {half_width:.1f}mm)",
                        actual_value=distance,
                        expected_value=half_width,
                    )
                )

        return results

    @staticmethod
    def _distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
        """Euclidean distance between two points."""
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    @staticmethod
    def _min_edge_distance(
        pos: tuple[float, float], bounds: tuple[float, float, float, float]
    ) -> float:
        """Minimum distance from point to any board edge."""
        x, y = pos
        x_min, y_min, x_max, y_max = bounds

        distances = [
            x - x_min,  # Left edge
            x_max - x,  # Right edge
            y - y_min,  # Bottom edge
            y_max - y,  # Top edge
        ]

        return min(distances)

    @staticmethod
    def _point_to_segment_distance(
        point: tuple[float, float], seg_start: tuple[float, float], seg_end: tuple[float, float]
    ) -> float:
        """Minimum distance from point to line segment."""
        px, py = point
        x1, y1 = seg_start
        x2, y2 = seg_end

        # Vector from start to end
        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            # Segment is a point
            return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)

        # Parameter t for projection onto line
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))  # Clamp to segment

        # Closest point on segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        return math.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)
