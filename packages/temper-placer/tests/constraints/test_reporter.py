"""Tests for constraint satisfaction reporting."""

from temper_placer.constraints.reporter import (
    ConstraintReport,
    ConstraintReporter,
    ConstraintResult,
    ConstraintStatus,
)
from temper_placer.io.config_loader import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    PlacementConstraints,
    ProximityRule,
    RoutingCorridor,
    ThermalConstraint,
)


class TestConstraintResult:
    """Test ConstraintResult dataclass."""

    def test_is_violation_for_hard_violated(self):
        result = ConstraintResult(
            constraint_type="Test",
            status=ConstraintStatus.VIOLATED,
            tier="hard",
            components=["A", "B"],
            message="Test",
        )
        assert result.is_violation() is True

    def test_is_violation_false_for_soft_violated(self):
        result = ConstraintResult(
            constraint_type="Test",
            status=ConstraintStatus.VIOLATED,
            tier="soft",
            components=["A", "B"],
            message="Test",
        )
        assert result.is_violation() is False

    def test_is_warning_for_soft_violated(self):
        result = ConstraintResult(
            constraint_type="Test",
            status=ConstraintStatus.VIOLATED,
            tier="soft",
            components=["A", "B"],
            message="Test",
        )
        assert result.is_warning() is True


class TestConstraintReport:
    """Test ConstraintReport aggregation."""

    def test_violations_filters_hard_violated(self):
        report = ConstraintReport(
            results=[
                ConstraintResult("Test", ConstraintStatus.VIOLATED, "hard", ["A"], "Hard fail"),
                ConstraintResult("Test", ConstraintStatus.VIOLATED, "soft", ["B"], "Soft fail"),
                ConstraintResult("Test", ConstraintStatus.SATISFIED, "hard", ["C"], "OK"),
            ]
        )

        violations = report.violations
        assert len(violations) == 1
        assert violations[0].components == ["A"]

    def test_warnings_filters_soft_violated(self):
        report = ConstraintReport(
            results=[
                ConstraintResult("Test", ConstraintStatus.VIOLATED, "hard", ["A"], "Hard fail"),
                ConstraintResult("Test", ConstraintStatus.VIOLATED, "soft", ["B"], "Soft fail"),
                ConstraintResult("Test", ConstraintStatus.SATISFIED, "soft", ["C"], "OK"),
            ]
        )

        warnings = report.warnings
        assert len(warnings) == 1
        assert warnings[0].components == ["B"]

    def test_has_violations(self):
        report = ConstraintReport(
            results=[
                ConstraintResult("Test", ConstraintStatus.VIOLATED, "hard", ["A"], "Fail"),
            ]
        )
        assert report.has_violations() is True

    def test_has_no_violations_with_only_soft(self):
        report = ConstraintReport(
            results=[
                ConstraintResult("Test", ConstraintStatus.VIOLATED, "soft", ["A"], "Warn"),
            ]
        )
        assert report.has_violations() is False

    def test_to_text_format(self):
        report = ConstraintReport(
            results=[
                ConstraintResult(
                    "ComponentSpacing",
                    ConstraintStatus.SATISFIED,
                    "hard",
                    ["A", "B"],
                    "ComponentSpacing: A - B (15.0mm ≥ 10.0mm)",
                ),
                ConstraintResult(
                    "Proximity",
                    ConstraintStatus.VIOLATED,
                    "soft",
                    ["C", "D"],
                    "Proximity: C - D (25.0mm > 20.0mm)",
                ),
            ]
        )

        text = report.to_text()

        assert "HARD CONSTRAINTS" in text
        assert "SOFT CONSTRAINTS" in text
        assert "SUMMARY" in text
        assert "✓" in text
        assert "⚠" in text or "○" in text

    def test_to_json_structure(self):
        report = ConstraintReport(
            results=[
                ConstraintResult(
                    "ComponentSpacing",
                    ConstraintStatus.VIOLATED,
                    "hard",
                    ["A", "B"],
                    "Test violation",
                    actual_value=5.0,
                    expected_value=10.0,
                ),
            ]
        )

        import json

        data = json.loads(report.to_json())

        assert "summary" in data
        assert "violations" in data
        assert data["summary"]["violations"] == 1
        assert len(data["violations"]) == 1
        assert data["violations"][0]["actual"] == 5.0


class TestComponentSpacingCheck:
    """Test ComponentSpacingRule checking."""

    def test_spacing_satisfied(self):
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule("A", "B", 10.0, tier="hard"),
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {"A": (0.0, 0.0), "B": (15.0, 0.0)}
        report = reporter.check(placements)

        assert len(report.results) == 1
        result = report.results[0]
        assert result.status == ConstraintStatus.SATISFIED
        assert result.actual_value == 15.0
        assert result.expected_value == 10.0

    def test_spacing_violated(self):
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule("A", "B", 10.0, tier="hard"),
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {"A": (0.0, 0.0), "B": (5.0, 0.0)}
        report = reporter.check(placements)

        assert len(report.results) == 1
        result = report.results[0]
        assert result.status == ConstraintStatus.VIOLATED
        assert result.is_violation() is True
        assert result.actual_value == 5.0

    def test_spacing_skipped_if_not_placed(self):
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule("A", "B", 10.0, tier="hard"),
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {"A": (0.0, 0.0)}  # B not placed
        report = reporter.check(placements)

        assert len(report.results) == 1
        assert report.results[0].status == ConstraintStatus.SKIPPED


class TestProximityCheck:
    """Test ProximityRule checking."""

    def test_proximity_satisfied(self):
        constraints = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="test",
                    components=["A", "B"],
                    proximity_rules=[
                        ProximityRule("A", "B", 20.0, tier="soft"),
                    ],
                )
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {"A": (0.0, 0.0), "B": (15.0, 0.0)}
        report = reporter.check(placements)

        # Should have proximity + group spread results
        prox_results = [r for r in report.results if r.constraint_type == "Proximity"]
        assert len(prox_results) == 1
        result = prox_results[0]
        assert result.status == ConstraintStatus.SATISFIED
        assert result.actual_value == 15.0

    def test_proximity_violated(self):
        constraints = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="test",
                    components=["A", "B"],
                    proximity_rules=[
                        ProximityRule("A", "B", 10.0, tier="hard"),
                    ],
                )
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {"A": (0.0, 0.0), "B": (15.0, 0.0)}
        report = reporter.check(placements)

        prox_results = [r for r in report.results if r.constraint_type == "Proximity"]
        assert len(prox_results) == 1
        result = prox_results[0]
        assert result.status == ConstraintStatus.VIOLATED
        assert result.is_violation() is True


class TestThermalCheck:
    """Test ThermalConstraint checking."""

    def test_thermal_edge_satisfied(self):
        constraints = PlacementConstraints(
            thermal_constraints=[
                ThermalConstraint(
                    components=["Q1"],  # List of components
                    prefer_edge=True,
                    max_distance_from_edge_mm=10.0,
                ),
            ]
        )
        board_bounds = (0.0, 0.0, 100.0, 100.0)
        reporter = ConstraintReporter(constraints, board_bounds)

        # Place at (5, 50) - 5mm from left edge
        placements = {"Q1": (5.0, 50.0)}
        report = reporter.check(placements)

        thermal_results = [r for r in report.results if r.constraint_type == "Thermal"]
        assert len(thermal_results) == 1
        result = thermal_results[0]
        assert result.status == ConstraintStatus.SATISFIED
        assert result.actual_value == 5.0

    def test_thermal_edge_violated(self):
        constraints = PlacementConstraints(
            thermal_constraints=[
                ThermalConstraint(
                    components=["Q1"],
                    prefer_edge=True,
                    max_distance_from_edge_mm=10.0,
                ),
            ]
        )
        board_bounds = (0.0, 0.0, 100.0, 100.0)
        reporter = ConstraintReporter(constraints, board_bounds)

        # Place at (50, 50) - 50mm from all edges
        placements = {"Q1": (50.0, 50.0)}
        report = reporter.check(placements)

        thermal_results = [r for r in report.results if r.constraint_type == "Thermal"]
        assert len(thermal_results) == 1
        result = thermal_results[0]
        assert result.status == ConstraintStatus.VIOLATED
        assert result.is_warning() is True  # Thermal is soft


class TestGroupSpreadCheck:
    """Test ComponentGroup max_spread checking."""

    def test_group_spread_satisfied(self):
        constraints = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="test",
                    components=["A", "B", "C"],
                    max_spread_mm=30.0,
                    proximity_rules=[],
                )
            ]
        )
        reporter = ConstraintReporter(constraints)

        # Triangle with diagonal ~28mm
        placements = {
            "A": (0.0, 0.0),
            "B": (20.0, 0.0),
            "C": (10.0, 20.0),
        }
        report = reporter.check(placements)

        spread_results = [r for r in report.results if r.constraint_type == "GroupSpread"]
        assert len(spread_results) == 1
        result = spread_results[0]
        assert result.status == ConstraintStatus.SATISFIED

    def test_group_spread_violated(self):
        constraints = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="test",
                    components=["A", "B"],
                    max_spread_mm=10.0,
                    proximity_rules=[],
                )
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {"A": (0.0, 0.0), "B": (20.0, 0.0)}
        report = reporter.check(placements)

        spread_results = [r for r in report.results if r.constraint_type == "GroupSpread"]
        assert len(spread_results) == 1
        result = spread_results[0]
        assert result.status == ConstraintStatus.VIOLATED
        assert result.actual_value == 20.0


class TestEscapeClearanceCheck:
    """Test EscapeClearance checking."""

    def test_escape_clearance_satisfied(self):
        constraints = PlacementConstraints(
            escape_clearances=[
                EscapeClearance(
                    component="U_MCU",
                    clearance_mm=10.0,
                    tier="hard",
                ),
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {
            "U_MCU": (50.0, 50.0),
            "C1": (65.0, 50.0),  # 15mm away
        }
        report = reporter.check(placements)

        escape_results = [r for r in report.results if r.constraint_type == "EscapeClearance"]
        assert len(escape_results) == 1
        result = escape_results[0]
        assert result.status == ConstraintStatus.SATISFIED

    def test_escape_clearance_violated(self):
        constraints = PlacementConstraints(
            escape_clearances=[
                EscapeClearance(
                    component="U_MCU",
                    clearance_mm=10.0,
                    tier="hard",
                ),
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {
            "U_MCU": (50.0, 50.0),
            "C1": (55.0, 50.0),  # Only 5mm away
            "C2": (50.0, 65.0),  # 15mm away (OK)
        }
        report = reporter.check(placements)

        escape_results = [r for r in report.results if r.constraint_type == "EscapeClearance"]
        # Should have 1 violation (C1) and not report C2
        violations = [r for r in escape_results if r.status == ConstraintStatus.VIOLATED]
        assert len(violations) == 1
        assert "C1" in violations[0].components
        assert violations[0].actual_value == 5.0


class TestRoutingCorridorCheck:
    """Test RoutingCorridor checking."""

    def test_corridor_satisfied(self):
        constraints = PlacementConstraints(
            routing_corridors=[
                RoutingCorridor(
                    name="usb_path",
                    from_component="J_USB",
                    to_component="U_MCU",
                    width_mm=6.0,
                    keep_clear=True,
                    tier="hard",
                ),
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {
            "J_USB": (0.0, 0.0),
            "U_MCU": (20.0, 0.0),
            "C1": (10.0, 10.0),  # Far from path
        }
        report = reporter.check(placements)

        corridor_results = [r for r in report.results if r.constraint_type == "RoutingCorridor"]
        assert len(corridor_results) == 1
        result = corridor_results[0]
        assert result.status == ConstraintStatus.SATISFIED

    def test_corridor_violated(self):
        constraints = PlacementConstraints(
            routing_corridors=[
                RoutingCorridor(
                    name="usb_path",
                    from_component="J_USB",
                    to_component="U_MCU",
                    width_mm=6.0,
                    keep_clear=True,
                    tier="hard",
                ),
            ]
        )
        reporter = ConstraintReporter(constraints)

        placements = {
            "J_USB": (0.0, 0.0),
            "U_MCU": (20.0, 0.0),
            "C1": (10.0, 2.0),  # Close to path (width=6 → half_width=3)
        }
        report = reporter.check(placements)

        corridor_results = [r for r in report.results if r.constraint_type == "RoutingCorridor"]
        violations = [r for r in corridor_results if r.status == ConstraintStatus.VIOLATED]
        assert len(violations) == 1
        assert "C1" in violations[0].components
        assert violations[0].actual_value == 2.0
        assert violations[0].expected_value == 3.0


class TestIntegratedReport:
    """Test full report with multiple constraint types."""

    def test_full_report_mixed_results(self):
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule("A", "B", 10.0, tier="hard"),
            ],
            component_groups=[
                ComponentGroup(
                    name="test",
                    components=["C", "D"],
                    max_spread_mm=20.0,
                    proximity_rules=[
                        ProximityRule("C", "D", 15.0, tier="soft"),
                    ],
                )
            ],
            escape_clearances=[
                EscapeClearance("U1", 8.0, tier="hard"),
            ],
        )
        reporter = ConstraintReporter(constraints)

        placements = {
            "A": (0.0, 0.0),
            "B": (5.0, 0.0),  # Violates spacing (5 < 10)
            "C": (50.0, 50.0),
            "D": (70.0, 50.0),  # Violates proximity (20 > 15)
            "U1": (100.0, 100.0),
            "R1": (105.0, 100.0),  # Violates escape (5 < 8)
        }

        report = reporter.check(placements)

        # Check violations
        assert len(report.violations) == 2  # Spacing + Escape (both hard)
        assert len(report.warnings) == 1  # Proximity (soft)

        # Check text format includes all sections
        text = report.to_text()
        assert "HARD CONSTRAINTS" in text
        assert "SOFT CONSTRAINTS" in text
        assert "VIOLATIONS: 2" in text
