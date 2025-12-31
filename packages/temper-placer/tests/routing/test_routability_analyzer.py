"""Tests for routability analyzer."""

import pytest
from temper_placer.routing.routability_analyzer import (
    analyze_pin_escape_routes,
    check_center_pin_accessibility,
    generate_dfm_report,
    RoutabilityIssue,
    RoutabilitySeverity,
)


class TestPinEscapeAnalysis:
    """Tests for pin escape route analysis."""

    def test_isolated_pin_is_routable(self):
        """Single isolated pin should have no issues."""
        pins = [("U1", "1", 10.0, 10.0)]
        bounds = {"U1": (5.0, 5.0, 10.0, 10.0)}
        
        reports = analyze_pin_escape_routes(pins, bounds)
        
        assert len(reports) == 0, "Isolated pin should have no issues"

    def test_widely_spaced_pins_are_routable(self):
        """Pins with sufficient spacing should have no issues."""
        pins = [
            ("U1", "1", 0.0, 0.0),
            ("U1", "2", 5.0, 0.0),  # 5mm spacing
            ("U1", "3", 0.0, 5.0),
            ("U1", "4", 5.0, 5.0),
        ]
        bounds = {"U1": (0.0, 0.0, 5.0, 5.0)}
        
        reports = analyze_pin_escape_routes(pins, bounds, min_clearance=0.2, min_trace_width=0.1)
        
        # No trapped pins
        errors = [r for r in reports if r.severity == RoutabilitySeverity.ERROR]
        assert len(errors) == 0, "Wide spacing should have no errors"

    def test_trapped_pin_detected(self):
        """Pin surrounded on all sides should be detected as trapped."""
        # Center pin surrounded by 4 neighbors at minimal spacing
        spacing = 0.3  # Just barely enough to trap
        pins = [
            ("U1", "CENTER", 0.0, 0.0),  # Trapped pin
            ("U1", "N", 0.0, spacing),   # North
            ("U1", "S", 0.0, -spacing),  # South
            ("U1", "E", spacing, 0.0),   # East
            ("U1", "W", -spacing, 0.0),  # West
        ]
        bounds = {"U1": (-1.0, -1.0, 2.0, 2.0)}
        
        reports = analyze_pin_escape_routes(pins, bounds, min_clearance=0.2, min_trace_width=0.1)
        
        # Should have trapped pin ERROR
        errors = [r for r in reports if r.severity == RoutabilitySeverity.ERROR]
        assert len(errors) > 0, "Trapped pin should be detected"
        
        trapped = [r for r in errors if r.issue == RoutabilityIssue.TRAPPED_PIN]
        assert len(trapped) > 0, "Should specifically identify TRAPPED_PIN issue"

    def test_blocked_escape_warning(self):
        """Pin with only 1 escape route should generate warning."""
        # Pin with 3 sides blocked
        spacing = 0.3
        pins = [
            ("U1", "PIN", 0.0, 0.0),
            ("U1", "N", 0.0, spacing),   # North blocked
            ("U1", "S", 0.0, -spacing),  # South blocked
            ("U1", "E", spacing, 0.0),   # East blocked
            # West is open
        ]
        bounds = {"U1": (-1.0, -1.0, 2.0, 2.0)}
        
        reports = analyze_pin_escape_routes(pins, bounds, min_clearance=0.2, min_trace_width=0.1)
        
        warnings = [r for r in reports if r.severity == RoutabilitySeverity.WARNING]
        assert len(warnings) > 0, "Blocked escape should generate warning"

    def test_dense_cluster_warning(self):
        """Dense cluster of pins should generate warning."""
        # 5 pins clustered together at 0.5mm pitch
        pins = [
            ("U1", "1", 0.0, 0.0),
            ("U1", "2", 0.5, 0.0),
            ("U1", "3", 1.0, 0.0),
            ("U1", "4", 0.5, 0.5),
            ("U1", "5", 0.0, 0.5),
        ]
        bounds = {"U1": (0.0, 0.0, 1.0, 0.5)}
        
        reports = analyze_pin_escape_routes(pins, bounds, min_clearance=0.1, min_trace_width=0.1)
        
        # Should have dense cluster warnings
        cluster_reports = [r for r in reports if r.issue == RoutabilityIssue.DENSE_CLUSTER]
        assert len(cluster_reports) > 0, "Dense cluster should be detected"

    def test_suggested_solutions_provided(self):
        """Trapped pin report should include suggested solutions."""
        pins = [
            ("U1", "CENTER", 0.0, 0.0),
            ("U1", "N", 0.0, 0.3),
            ("U1", "S", 0.0, -0.3),
            ("U1", "E", 0.3, 0.0),
            ("U1", "W", -0.3, 0.0),
        ]
        bounds = {"U1": (-1.0, -1.0, 2.0, 2.0)}
        
        reports = analyze_pin_escape_routes(pins, bounds)
        
        errors = [r for r in reports if r.severity == RoutabilitySeverity.ERROR]
        assert len(errors) > 0
        assert errors[0].suggested_solution is not None
        assert "via-in-pad" in errors[0].suggested_solution.lower()


class TestCenterPinAccessibility:
    """Tests for center pin accessibility checking."""

    def test_center_pin_flagged(self):
        """Pin in center of component should be flagged."""
        pins = [
            ("U1", "A1", 0.0, 0.0),  # Center
            ("U1", "B1", 5.0, 5.0),  # Outer
        ]
        center = (0.0, 0.0)
        size = (10.0, 10.0)
        
        reports = check_center_pin_accessibility(pins, center, size)
        
        center_reports = [r for r in reports if "A1" in r.pin_name]
        assert len(center_reports) > 0, "Center pin should be flagged"
        assert center_reports[0].issue == RoutabilityIssue.CENTER_PIN_NO_CHANNEL

    def test_outer_pins_not_flagged(self):
        """Pins far from center should not be flagged."""
        pins = [
            ("U1", "A1", 5.0, 5.0),  # Outer
        ]
        center = (0.0, 0.0)
        size = (10.0, 10.0)
        
        reports = check_center_pin_accessibility(pins, center, size)
        
        assert len(reports) == 0, "Outer pins should not be flagged"


class TestDFMReportGeneration:
    """Tests for DFM report generation."""

    def test_clean_design_report(self):
        """Report for clean design should indicate success."""
        reports = []
        
        report_text = generate_dfm_report(reports)
        
        assert "No routability issues" in report_text
        assert "✓" in report_text

    def test_error_report_formatting(self):
        """Report with errors should be properly formatted."""
        from temper_placer.routing.routability_analyzer import RoutabilityReport
        
        reports = [
            RoutabilityReport(
                component_ref="U1",
                pin_name="A1",
                position=(10.0, 10.0),
                issue=RoutabilityIssue.TRAPPED_PIN,
                severity=RoutabilitySeverity.ERROR,
                message="Pin is trapped",
                suggested_solution="Use via-in-pad",
            )
        ]
        
        report_text = generate_dfm_report(reports)
        
        assert "ERRORS" in report_text
        assert "U1.A1" in report_text
        assert "via-in-pad" in report_text
        assert "Action Required" in report_text

    def test_warning_only_report(self):
        """Report with only warnings should not require action."""
        from temper_placer.routing.routability_analyzer import RoutabilityReport
        
        reports = [
            RoutabilityReport(
                component_ref="U1",
                pin_name="A1",
                position=(10.0, 10.0),
                issue=RoutabilityIssue.DENSE_CLUSTER,
                severity=RoutabilitySeverity.WARNING,
                message="Dense cluster",
                suggested_solution="Enable fanout",
            )
        ]
        
        report_text = generate_dfm_report(reports)
        
        assert "WARNINGS" in report_text
        assert "ERRORS" not in report_text
        assert "Recommended" in report_text

    def test_summary_section(self):
        """Report should include summary with counts."""
        from temper_placer.routing.routability_analyzer import RoutabilityReport
        
        reports = [
            RoutabilityReport("U1", "A1", (0, 0), RoutabilityIssue.TRAPPED_PIN, RoutabilitySeverity.ERROR, "err"),
            RoutabilityReport("U2", "B1", (1, 1), RoutabilityIssue.DENSE_CLUSTER, RoutabilitySeverity.WARNING, "warn"),
            RoutabilityReport("U3", "C1", (2, 2), RoutabilityIssue.CENTER_PIN_NO_CHANNEL, RoutabilitySeverity.INFO, "info"),
        ]
        
        report_text = generate_dfm_report(reports)
        
        assert "Summary" in report_text
        assert "Errors: 1" in report_text
        assert "Warnings: 1" in report_text
        assert "Info: 1" in report_text
