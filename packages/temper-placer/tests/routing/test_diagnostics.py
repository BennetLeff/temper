"""
Tests for routing diagnostic report generator (temper-wna.5).

The diagnostic module generates actionable feedback when routing fails,
identifying what's blocking and suggesting fixes.

Diagnostic Types:
- NO_PATH: Net blocked by component or other route
- CLEARANCE: Trace too close to HV net
- LAYER_CONFLICT: Net assigned to wrong layer
- CONGESTION: Too many nets in an area
"""

import pytest

from temper_placer.core.netlist import Component, Net, Netlist, Pin


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_netlist():
    """Create a sample netlist for diagnostic testing."""
    components = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(16.0, 20.0),
            pins=[Pin("G", "1", (0, 0), net="GATE_H")],
            initial_position=(30.0, 50.0),
        ),
        Component(
            ref="U1",
            footprint="SOIC-16",
            bounds=(10.0, 6.0),
            pins=[Pin("OUT", "1", (0, 0), net="GATE_H")],
            initial_position=(50.0, 50.0),
        ),
        Component(
            ref="C1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0), net="VCC")],
            initial_position=(40.0, 50.0),  # Blocking path
        ),
    ]

    nets = [
        Net("GATE_H", [("Q1", "G"), ("U1", "OUT")], net_class="GateDrive"),
        Net("VCC", [("C1", "1")], net_class="Power"),
    ]

    return Netlist(components=components, nets=nets)


# =============================================================================
# Tests for FailureType Enum
# =============================================================================


class TestFailureType:
    """Tests for FailureType enumeration."""

    def test_failure_types_exist(self):
        """Should have all expected failure types."""
        from temper_placer.routing.diagnostics import FailureType

        assert hasattr(FailureType, "NO_PATH")
        assert hasattr(FailureType, "CLEARANCE")
        assert hasattr(FailureType, "LAYER_CONFLICT")
        assert hasattr(FailureType, "CONGESTION")
        assert hasattr(FailureType, "VIA_COUNT")

    def test_failure_type_values(self):
        """Failure types should have string values."""
        from temper_placer.routing.diagnostics import FailureType

        assert FailureType.NO_PATH.value == "no_path"
        assert FailureType.CLEARANCE.value == "clearance"


# =============================================================================
# Tests for RoutingDiagnostic Dataclass
# =============================================================================


class TestRoutingDiagnostic:
    """Tests for RoutingDiagnostic data structure."""

    def test_diagnostic_creation(self):
        """Should create a valid diagnostic."""
        from temper_placer.routing.diagnostics import RoutingDiagnostic, FailureType

        diag = RoutingDiagnostic(
            net="NET_A",
            failure_type=FailureType.NO_PATH,
            location=(45.0, 50.0),
            severity="critical",
            blocking_elements=["C1", "R1"],
            constraint_violated=None,
            suggested_fix="Move C1 2mm left to clear routing channel",
            fix_confidence=0.7,
            placement_hint=None,
        )

        assert diag.net == "NET_A"
        assert diag.failure_type == FailureType.NO_PATH
        assert diag.location == (45.0, 50.0)
        assert "C1" in diag.blocking_elements
        assert "Move" in diag.suggested_fix

    def test_diagnostic_severity_levels(self):
        """Severity should be critical, warning, or info."""
        from temper_placer.routing.diagnostics import RoutingDiagnostic, FailureType

        for severity in ["critical", "warning", "info"]:
            diag = RoutingDiagnostic(
                net="NET_A",
                failure_type=FailureType.NO_PATH,
                location=(0, 0),
                severity=severity,
                blocking_elements=[],
                constraint_violated=None,
                suggested_fix="Fix it",
                fix_confidence=0.5,
                placement_hint=None,
            )
            assert diag.severity == severity


# =============================================================================
# Tests for RoutingReport Dataclass
# =============================================================================


class TestRoutingReport:
    """Tests for RoutingReport aggregate structure."""

    def test_report_creation(self):
        """Should create a valid routing report."""
        from temper_placer.routing.diagnostics import RoutingReport

        report = RoutingReport(
            feasible=False,
            completion_rate=0.85,
            routed_nets=["NET_A", "NET_B"],
            failed_nets=["NET_C"],
            diagnostics=[],
            congestion_map=None,
            total_wirelength=1234.5,
            total_vias=23,
            worst_congestion=1.5,
        )

        assert report.feasible is False
        assert report.completion_rate == 0.85
        assert len(report.routed_nets) == 2
        assert len(report.failed_nets) == 1

    def test_report_feasible_when_all_routed(self):
        """Report should be feasible when all nets are routed."""
        from temper_placer.routing.diagnostics import RoutingReport

        report = RoutingReport(
            feasible=True,
            completion_rate=1.0,
            routed_nets=["NET_A", "NET_B", "NET_C"],
            failed_nets=[],
            diagnostics=[],
            congestion_map=None,
            total_wirelength=500.0,
            total_vias=10,
            worst_congestion=0.5,
        )

        assert report.feasible is True
        assert len(report.failed_nets) == 0


# =============================================================================
# Tests for Diagnostic Generation
# =============================================================================


class TestDiagnosticGeneration:
    """Tests for generate_diagnostics function."""

    def test_generate_no_path_diagnostic(self):
        """Should generate diagnostic for blocked path."""
        from temper_placer.routing.diagnostics import (
            generate_no_path_diagnostic,
            FailureType,
        )

        diag = generate_no_path_diagnostic(
            net="GATE_H",
            blocked_at=(45.0, 50.0),
            blocking_components=["C1"],
        )

        assert diag.net == "GATE_H"
        assert diag.failure_type == FailureType.NO_PATH
        assert "C1" in diag.blocking_elements
        assert diag.suggested_fix is not None
        assert len(diag.suggested_fix) > 0

    def test_generate_congestion_diagnostic(self):
        """Should generate diagnostic for congestion."""
        from temper_placer.routing.diagnostics import (
            generate_congestion_diagnostic,
            FailureType,
        )

        diag = generate_congestion_diagnostic(
            net="NET_SENSE",
            location=(30.0, 25.0),
            utilization=1.5,
            components_in_area=["C1", "C2", "R1"],
        )

        assert diag.failure_type == FailureType.CONGESTION
        assert diag.severity == "warning"  # Congestion is usually warning
        assert "spread" in diag.suggested_fix.lower() or "move" in diag.suggested_fix.lower()

    def test_generate_layer_conflict_diagnostic(self):
        """Should generate diagnostic for layer conflicts."""
        from temper_placer.routing.diagnostics import (
            generate_layer_conflict_diagnostic,
            FailureType,
        )

        diag = generate_layer_conflict_diagnostic(
            net="HV_NET",
            assigned_layer=4,  # L4
            required_layer=1,  # L1
            reason="HV nets must be on L1",
        )

        assert diag.failure_type == FailureType.LAYER_CONFLICT
        assert "L1" in diag.suggested_fix or "layer" in diag.suggested_fix.lower()


# =============================================================================
# Tests for Blocking Element Detection
# =============================================================================


class TestBlockingElementDetection:
    """Tests for finding what blocks a routing path."""

    def test_find_blocking_components(self, sample_netlist):
        """Should identify components blocking a path."""
        from temper_placer.routing.diagnostics import find_blocking_components
        import jax.numpy as jnp

        positions = jnp.array(
            [
                [30.0, 50.0],  # Q1
                [50.0, 50.0],  # U1
                [40.0, 50.0],  # C1 - blocking
            ]
        )

        # Path from Q1 to U1 passes through C1's area
        blockers = find_blocking_components(
            start=(30.0, 50.0),
            end=(50.0, 50.0),
            components=sample_netlist.components,
            positions=positions,
        )

        assert "C1" in blockers

    def test_find_no_blockers_clear_path(self, sample_netlist):
        """Should return empty list when path is clear."""
        from temper_placer.routing.diagnostics import find_blocking_components
        import jax.numpy as jnp

        # Move C1 out of the way
        positions = jnp.array(
            [
                [30.0, 50.0],  # Q1
                [50.0, 50.0],  # U1
                [40.0, 80.0],  # C1 - moved away
            ]
        )

        blockers = find_blocking_components(
            start=(30.0, 50.0),
            end=(50.0, 50.0),
            components=sample_netlist.components,
            positions=positions,
        )

        assert "C1" not in blockers


# =============================================================================
# Tests for Suggested Fix Generation
# =============================================================================


class TestSuggestedFixGeneration:
    """Tests for generating actionable fix suggestions."""

    def test_compute_move_direction(self):
        """Should compute direction to move blocking component."""
        from temper_placer.routing.diagnostics import compute_clear_direction

        # Component at (40, 50) blocking path from (30, 50) to (50, 50)
        direction = compute_clear_direction(
            blocker_pos=(40.0, 50.0),
            path_start=(30.0, 50.0),
            path_end=(50.0, 50.0),
        )

        # Should suggest moving perpendicular to path (up or down)
        # Direction should be normalized or give reasonable magnitude
        assert direction is not None
        assert len(direction) == 2
        # Y component should be non-zero (move up or down)
        assert abs(direction[1]) > 0 or abs(direction[0]) > 0

    def test_format_move_suggestion(self):
        """Should format human-readable move suggestion."""
        from temper_placer.routing.diagnostics import format_move_suggestion

        suggestion = format_move_suggestion(
            component="C1",
            direction=(0.0, 3.0),  # Move 3mm up
            reason="clear routing channel for GATE_H",
        )

        assert "C1" in suggestion
        assert "3" in suggestion or "mm" in suggestion.lower()


# =============================================================================
# Tests for PlacementAdjustment Generation
# =============================================================================


class TestPlacementAdjustment:
    """Tests for generating placement feedback."""

    def test_create_placement_hint(self):
        """Should create a valid PlacementAdjustment."""
        from temper_placer.routing.diagnostics import PlacementAdjustment

        hint = PlacementAdjustment(
            component="C1",
            adjustment_type="move",
            direction=(2.0, 0.0),
            reason="Clear routing channel for GATE_H",
            priority=1.0,
        )

        assert hint.component == "C1"
        assert hint.adjustment_type == "move"
        assert hint.direction == (2.0, 0.0)

    def test_adjustment_types(self):
        """Should support move, rotate, and swap adjustments."""
        from temper_placer.routing.diagnostics import PlacementAdjustment

        for adj_type in ["move", "rotate", "swap"]:
            hint = PlacementAdjustment(
                component="U1",
                adjustment_type=adj_type,
                direction=(0.0, 0.0) if adj_type != "move" else (1.0, 0.0),
                reason="Test",
                priority=0.5,
            )
            assert hint.adjustment_type == adj_type


# =============================================================================
# Tests for Markdown Report Generation
# =============================================================================


class TestMarkdownReport:
    """Tests for generating markdown diagnostic reports."""

    def test_generate_markdown_report(self):
        """Should generate a valid markdown report."""
        from temper_placer.routing.diagnostics import (
            RoutingReport,
            RoutingDiagnostic,
            FailureType,
            generate_markdown_report,
        )

        diag = RoutingDiagnostic(
            net="GATE_H",
            failure_type=FailureType.NO_PATH,
            location=(45.0, 50.0),
            severity="critical",
            blocking_elements=["C1"],
            constraint_violated=None,
            suggested_fix="Move C1 2mm left",
            fix_confidence=0.7,
            placement_hint=None,
        )

        report = RoutingReport(
            feasible=False,
            completion_rate=0.85,
            routed_nets=["NET_A", "NET_B"],
            failed_nets=["GATE_H"],
            diagnostics=[diag],
            congestion_map=None,
            total_wirelength=1234.5,
            total_vias=23,
            worst_congestion=1.2,
        )

        markdown = generate_markdown_report(report)

        # Should have key sections
        assert "# Routing" in markdown
        assert "Summary" in markdown
        assert "GATE_H" in markdown
        assert "C1" in markdown
        assert "85" in markdown and "%" in markdown  # 85.0% or 85%

    def test_markdown_report_empty_diagnostics(self):
        """Should handle reports with no diagnostics."""
        from temper_placer.routing.diagnostics import (
            RoutingReport,
            generate_markdown_report,
        )

        report = RoutingReport(
            feasible=True,
            completion_rate=1.0,
            routed_nets=["NET_A", "NET_B"],
            failed_nets=[],
            diagnostics=[],
            congestion_map=None,
            total_wirelength=500.0,
            total_vias=10,
            worst_congestion=0.3,
        )

        markdown = generate_markdown_report(report)

        assert "100" in markdown and "%" in markdown  # 100.0% or 100%
        assert "Feasible" in markdown or "Success" in markdown


# =============================================================================
# Tests for Diagnostic Integration
# =============================================================================


class TestDiagnosticIntegration:
    """Tests for generating diagnostics from routing results."""

    def test_diagnostics_from_routing_result(self):
        """Should generate diagnostics from MazeRouter results."""
        from temper_placer.routing.diagnostics import generate_diagnostics_from_results
        from temper_placer.routing.maze_router import RoutePath

        results = {
            "NET_A": RoutePath("NET_A", [], 10.0, 0, True),
            "NET_B": RoutePath("NET_B", [], 0.0, 0, False, "No path from (5,5) to (15,15)"),
        }

        diagnostics = generate_diagnostics_from_results(results)

        # Should have diagnostic for NET_B only
        assert len(diagnostics) == 1
        assert diagnostics[0].net == "NET_B"

    def test_diagnostics_empty_for_success(self):
        """Should return empty list when all routing succeeds."""
        from temper_placer.routing.diagnostics import generate_diagnostics_from_results
        from temper_placer.routing.maze_router import RoutePath

        results = {
            "NET_A": RoutePath("NET_A", [], 10.0, 0, True),
            "NET_B": RoutePath("NET_B", [], 15.0, 1, True),
        }

        diagnostics = generate_diagnostics_from_results(results)

        assert len(diagnostics) == 0
