"""Tests for visualization/status.py - constraint status panel rendering."""

import json

import pytest

from temper_placer.visualization.model import (
    ConstraintStatus,
    Point,
    Violation,
    ViolationType,
)

# Check if Plotly is available
try:
    import plotly

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def empty_status():
    """Constraint status with no violations."""
    return ConstraintStatus()


@pytest.fixture
def valid_status_with_warnings():
    """Valid status (no errors) but with thermal warnings."""
    violations = (
        Violation(
            violation_type=ViolationType.THERMAL,
            severity=0.3,
            component_refs=("U1", "R5"),
            message="Components too close thermally",
        ),
        Violation(
            violation_type=ViolationType.THERMAL,
            severity=0.2,
            component_refs=("Q1",),
            message="Near heat source",
        ),
    )
    return ConstraintStatus(
        violations=violations,
        thermal_warnings=2,
    )


@pytest.fixture
def invalid_status():
    """Invalid status with overlap and boundary violations."""
    violations = (
        Violation(
            violation_type=ViolationType.OVERLAP,
            severity=0.9,
            component_refs=("U1", "U2"),
            message="Components overlapping",
            location=Point(50.0, 30.0),
        ),
        Violation(
            violation_type=ViolationType.BOUNDARY,
            severity=0.8,
            component_refs=("C10",),
            message="Outside board boundary",
            location=Point(105.0, 50.0),
        ),
        Violation(
            violation_type=ViolationType.CLEARANCE,
            severity=0.5,
            component_refs=("R1", "R2"),
            message="Insufficient clearance",
        ),
        Violation(
            violation_type=ViolationType.DRC,
            severity=0.7,
            component_refs=("U3",),
            message="DRC: track too close to pad",
        ),
    )
    return ConstraintStatus(
        violations=violations,
        overlap_count=1,
        boundary_violations=1,
        clearance_violations=1,
        drc_errors=1,
    )


@pytest.fixture
def many_violations_status():
    """Status with many violations for testing list truncation."""
    violations = tuple(
        Violation(
            violation_type=ViolationType.OVERLAP,
            severity=0.5 + 0.05 * i,
            component_refs=(f"U{i}", f"U{i + 1}"),
            message=f"Overlap between U{i} and U{i + 1}",
        )
        for i in range(20)
    )
    return ConstraintStatus(
        violations=violations,
        overlap_count=20,
    )


# ============================================================================
# Tests for helper functions (no Plotly required)
# ============================================================================


class TestSeverityHelpers:
    """Tests for severity level helper functions."""

    def test_get_severity_level_low(self):
        from temper_placer.visualization.status import get_severity_level

        assert get_severity_level(0.0) == "low"
        assert get_severity_level(0.1) == "low"
        assert get_severity_level(0.24) == "low"

    def test_get_severity_level_medium(self):
        from temper_placer.visualization.status import get_severity_level

        assert get_severity_level(0.25) == "medium"
        assert get_severity_level(0.35) == "medium"
        assert get_severity_level(0.49) == "medium"

    def test_get_severity_level_high(self):
        from temper_placer.visualization.status import get_severity_level

        assert get_severity_level(0.5) == "high"
        assert get_severity_level(0.6) == "high"
        assert get_severity_level(0.74) == "high"

    def test_get_severity_level_critical(self):
        from temper_placer.visualization.status import get_severity_level

        assert get_severity_level(0.75) == "critical"
        assert get_severity_level(0.9) == "critical"
        assert get_severity_level(1.0) == "critical"

    def test_get_severity_color(self):
        from temper_placer.visualization.status import get_severity_color

        # Just check that colors are returned (valid hex)
        for severity in [0.1, 0.3, 0.6, 0.9]:
            color = get_severity_color(severity)
            assert color.startswith("#")
            assert len(color) == 7


class TestAffectedComponentRefs:
    """Tests for get_affected_component_refs function."""

    def test_empty_status(self, empty_status):
        from temper_placer.visualization.status import get_affected_component_refs

        refs = get_affected_component_refs(empty_status)
        assert refs == []

    def test_single_violation(self):
        from temper_placer.visualization.status import get_affected_component_refs

        status = ConstraintStatus(
            violations=(
                Violation(
                    violation_type=ViolationType.OVERLAP,
                    severity=0.5,
                    component_refs=("U1", "U2"),
                ),
            ),
        )
        refs = get_affected_component_refs(status)
        assert sorted(refs) == ["U1", "U2"]

    def test_multiple_violations_unique(self, invalid_status):
        from temper_placer.visualization.status import get_affected_component_refs

        refs = get_affected_component_refs(invalid_status)
        # Should have unique refs
        assert len(refs) == len(set(refs))
        # Check specific refs present
        assert "U1" in refs
        assert "C10" in refs


class TestViolationsByComponent:
    """Tests for get_violations_by_component function."""

    def test_empty_status(self, empty_status):
        from temper_placer.visualization.status import get_violations_by_component

        by_comp = get_violations_by_component(empty_status)
        assert by_comp == {}

    def test_groups_correctly(self, invalid_status):
        from temper_placer.visualization.status import get_violations_by_component

        by_comp = get_violations_by_component(invalid_status)
        # U1 is in overlap violation
        assert "U1" in by_comp
        assert len(by_comp["U1"]) == 1
        assert by_comp["U1"][0].violation_type == ViolationType.OVERLAP


class TestViolationsByType:
    """Tests for get_violations_by_type function."""

    def test_empty_status(self, empty_status):
        from temper_placer.visualization.status import get_violations_by_type

        by_type = get_violations_by_type(empty_status)
        assert by_type == {}

    def test_groups_correctly(self, invalid_status):
        from temper_placer.visualization.status import get_violations_by_type

        by_type = get_violations_by_type(invalid_status)
        assert ViolationType.OVERLAP in by_type
        assert ViolationType.BOUNDARY in by_type
        assert len(by_type[ViolationType.OVERLAP]) == 1
        assert len(by_type[ViolationType.BOUNDARY]) == 1


# ============================================================================
# Tests for JSON export (no Plotly required)
# ============================================================================


class TestConstraintStatusJson:
    """Tests for constraint_status_to_json function."""

    def test_empty_status(self, empty_status):
        from temper_placer.visualization.status import constraint_status_to_json

        json_str = constraint_status_to_json(empty_status)
        data = json.loads(json_str)

        assert data["total_violations"] == 0
        assert data["has_errors"] is False
        assert data["affected_components"] == []

    def test_invalid_status(self, invalid_status):
        from temper_placer.visualization.status import constraint_status_to_json

        json_str = constraint_status_to_json(invalid_status)
        data = json.loads(json_str)

        assert data["total_violations"] == 4
        assert data["has_errors"] is True
        assert "overlap" in data["violations_by_type"]
        assert data["summary"]["overlap"] == 1
        assert data["summary"]["boundary"] == 1

    def test_json_is_valid(self, invalid_status):
        from temper_placer.visualization.status import constraint_status_to_json

        json_str = constraint_status_to_json(invalid_status)
        # Should not raise
        data = json.loads(json_str)
        assert isinstance(data, dict)


# ============================================================================
# Tests for Plotly rendering (skipped without Plotly)
# ============================================================================


@pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="Plotly not installed")
class TestStatusIndicatorRendering:
    """Tests for render_status_indicator function."""

    def test_valid_status(self, empty_status):
        from temper_placer.visualization.status import render_status_indicator

        fig = render_status_indicator(empty_status)
        assert fig is not None
        # Should have annotations for symbol and label
        assert len(fig.layout.annotations) == 2

    def test_warning_status(self, valid_status_with_warnings):
        from temper_placer.visualization.status import render_status_indicator

        fig = render_status_indicator(valid_status_with_warnings)
        assert fig is not None

    def test_invalid_status(self, invalid_status):
        from temper_placer.visualization.status import render_status_indicator

        fig = render_status_indicator(invalid_status)
        assert fig is not None

    def test_custom_size(self, empty_status):
        from temper_placer.visualization.status import render_status_indicator

        fig = render_status_indicator(empty_status, width=300, height=300)
        assert fig.layout.width == 300
        assert fig.layout.height == 300


@pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="Plotly not installed")
class TestViolationSummaryBar:
    """Tests for render_violation_summary_bar function."""

    def test_empty_status(self, empty_status):
        from temper_placer.visualization.status import render_violation_summary_bar

        fig = render_violation_summary_bar(empty_status)
        assert fig is not None
        assert len(fig.data) == 1  # One bar trace
        assert fig.data[0].type == "bar"

    def test_invalid_status(self, invalid_status):
        from temper_placer.visualization.status import render_violation_summary_bar

        fig = render_violation_summary_bar(invalid_status)
        assert fig is not None
        # Check that bar data matches status
        bar_data = fig.data[0]
        # y values should include our counts
        y_values = list(bar_data.y)
        assert 1 in y_values  # overlap_count

    def test_custom_title(self, empty_status):
        from temper_placer.visualization.status import render_violation_summary_bar

        fig = render_violation_summary_bar(empty_status, title="Custom Title")
        assert "Custom Title" in fig.layout.title.text


@pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="Plotly not installed")
class TestViolationList:
    """Tests for render_violation_list function."""

    def test_empty_violations(self):
        from temper_placer.visualization.status import render_violation_list

        fig = render_violation_list([])
        assert fig is not None
        assert len(fig.data) == 1  # One table trace
        assert fig.data[0].type == "table"

    def test_violations_displayed(self, invalid_status):
        from temper_placer.visualization.status import render_violation_list

        fig = render_violation_list(list(invalid_status.violations))
        assert fig is not None
        table = fig.data[0]
        # Check columns exist
        assert len(table.header.values) == 4  # Type, Components, Message, Severity

    def test_truncation(self, many_violations_status):
        from temper_placer.visualization.status import render_violation_list

        violations = list(many_violations_status.violations)
        fig = render_violation_list(violations, max_items=5)
        assert fig is not None
        # Title should mention truncation
        assert "5 of 20" in fig.layout.title.text

    def test_sorted_by_severity(self, invalid_status):
        from temper_placer.visualization.status import render_violation_list

        fig = render_violation_list(list(invalid_status.violations))
        table = fig.data[0]
        # First item should be highest severity (0.9 overlap)
        # Severity column is index 3
        severities = table.cells.values[3]
        assert float(severities[0]) == 0.90


@pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="Plotly not installed")
class TestConstraintStatusPanel:
    """Tests for render_constraint_status function (main panel)."""

    def test_empty_status(self, empty_status):
        from temper_placer.visualization.status import render_constraint_status

        fig = render_constraint_status(empty_status)
        assert fig is not None

    def test_invalid_status(self, invalid_status):
        from temper_placer.visualization.status import render_constraint_status

        fig = render_constraint_status(invalid_status)
        assert fig is not None

    def test_custom_size(self, empty_status):
        from temper_placer.visualization.status import render_constraint_status

        fig = render_constraint_status(empty_status, width=600, height=400)
        assert fig.layout.width == 600
        assert fig.layout.height == 400

    def test_show_only_indicator(self, empty_status):
        from temper_placer.visualization.status import render_constraint_status

        fig = render_constraint_status(
            empty_status,
            show_indicator=True,
            show_summary=False,
            show_list=False,
        )
        assert fig is not None

    def test_show_only_summary(self, invalid_status):
        from temper_placer.visualization.status import render_constraint_status

        fig = render_constraint_status(
            invalid_status,
            show_indicator=False,
            show_summary=True,
            show_list=False,
        )
        assert fig is not None
        # Should have bar trace
        assert any(trace.type == "bar" for trace in fig.data)

    def test_show_only_list(self, invalid_status):
        from temper_placer.visualization.status import render_constraint_status

        fig = render_constraint_status(
            invalid_status,
            show_indicator=False,
            show_summary=False,
            show_list=True,
        )
        assert fig is not None
        # Should have table trace
        assert any(trace.type == "table" for trace in fig.data)

    def test_all_panels_hidden(self, empty_status):
        from temper_placer.visualization.status import render_constraint_status

        fig = render_constraint_status(
            empty_status,
            show_indicator=False,
            show_summary=False,
            show_list=False,
        )
        assert fig is not None
        # Empty figure
        assert len(fig.data) == 0


@pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="Plotly not installed")
class TestStatusHtmlExport:
    """Tests for constraint_status_to_html function."""

    def test_basic_export(self, invalid_status):
        from temper_placer.visualization.status import constraint_status_to_html

        html = constraint_status_to_html(invalid_status)
        assert isinstance(html, str)
        assert len(html) > 0
        assert "plotly" in html.lower()

    def test_full_html(self, invalid_status):
        from temper_placer.visualization.status import constraint_status_to_html

        html = constraint_status_to_html(invalid_status, full_html=True)
        assert "<html" in html.lower()
        assert "</html>" in html.lower()

    def test_partial_html(self, invalid_status):
        from temper_placer.visualization.status import constraint_status_to_html

        html = constraint_status_to_html(invalid_status, full_html=False)
        # Should be a div, not full document
        assert "<div" in html.lower()


# ============================================================================
# Tests for Plotly not available
# ============================================================================


class TestPlotlyNotAvailable:
    """Tests for behavior when Plotly is not installed."""

    @pytest.mark.skipif(PLOTLY_AVAILABLE, reason="Plotly is installed")
    def test_render_raises_import_error(self, empty_status):
        from temper_placer.visualization.status import render_constraint_status

        with pytest.raises(ImportError, match="Plotly"):
            render_constraint_status(empty_status)

    @pytest.mark.skipif(PLOTLY_AVAILABLE, reason="Plotly is installed")
    def test_html_raises_import_error(self, empty_status):
        from temper_placer.visualization.status import constraint_status_to_html

        with pytest.raises(ImportError, match="Plotly"):
            constraint_status_to_html(empty_status)


# ============================================================================
# Tests for color constants
# ============================================================================


class TestColorConstants:
    """Tests for color constant definitions."""

    def test_violation_colors_defined(self):
        from temper_placer.visualization.status import VIOLATION_COLORS

        # All violation types should have colors
        for vtype in ViolationType:
            assert vtype in VIOLATION_COLORS
            assert VIOLATION_COLORS[vtype].startswith("#")

    def test_severity_colors_defined(self):
        from temper_placer.visualization.status import SEVERITY_COLORS

        for level in ["low", "medium", "high", "critical"]:
            assert level in SEVERITY_COLORS
            assert SEVERITY_COLORS[level].startswith("#")

    def test_status_colors_defined(self):
        from temper_placer.visualization.status import STATUS_COLORS

        for status in ["valid", "invalid", "warning"]:
            assert status in STATUS_COLORS
            assert STATUS_COLORS[status].startswith("#")
