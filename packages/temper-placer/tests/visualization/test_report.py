"""Tests for visualization/report.py - HTML report generation."""

import tempfile
from pathlib import Path

import pytest

from temper_placer.visualization.model import (
    BoardView,
    ComponentStatus,
    ComponentView,
    ConstraintStatus,
    LossDataPoint,
    LossHistory,
    Point,
    Violation,
    ViolationType,
)
from temper_placer.visualization.report import (
    ReportConfig,
    ValidationResults,
    generate_report,
)


# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def sample_board():
    """Create a sample board view."""
    return BoardView(
        width=100.0,
        height=80.0,
        components=(
            ComponentView(
                ref="U1",
                position=Point(20.0, 30.0),
                rotation=0.0,
                width=10.0,
                height=5.0,
                footprint="SOIC-8",
            ),
            ComponentView(
                ref="R1",
                position=Point(50.0, 40.0),
                rotation=90.0,
                width=4.0,
                height=2.0,
                footprint="0603",
            ),
            ComponentView(
                ref="C1",
                position=Point(70.0, 60.0),
                rotation=0.0,
                width=3.0,
                height=2.0,
                footprint="0402",
                status=ComponentStatus.WARNING,
            ),
        ),
    )


@pytest.fixture
def sample_history():
    """Create a sample loss history."""
    history = LossHistory()
    for i in range(10):
        history.add_point(
            LossDataPoint(
                epoch=i,
                total_loss=10.0 - i * 0.5,
                breakdown={
                    "overlap": 5.0 - i * 0.2,
                    "boundary": 3.0 - i * 0.2,
                    "wirelength": 2.0 - i * 0.1,
                },
            )
        )
    return history


@pytest.fixture
def sample_constraints():
    """Create sample constraint status."""
    return ConstraintStatus(
        violations=(
            Violation(
                violation_type=ViolationType.OVERLAP,
                severity=0.3,
                component_refs=("U1", "R1"),
                message="Components overlapping by 0.5mm",
            ),
        ),
        overlap_count=1,
        boundary_violations=0,
        clearance_violations=0,
        thermal_warnings=0,
    )


@pytest.fixture
def sample_validation():
    """Create sample validation results."""
    return ValidationResults(
        drc_passed=True,
        drc_errors=[],
        drc_warnings=["Track width below recommended minimum"],
        spice_passed=False,
        spice_errors=["Node 'VCC' has no DC path to ground"],
        spice_warnings=[],
    )


# ============================================================================
# Tests for ReportConfig
# ============================================================================


class TestReportConfig:
    """Tests for ReportConfig dataclass."""

    def test_default_config(self):
        config = ReportConfig()
        assert config.title == "Placement Optimization Report"
        assert config.include_timestamp is True
        assert config.board_chart_height == 600
        assert config.loss_chart_height == 400
        assert config.max_components_in_table == 100
        assert config.include_board_view is True
        assert config.include_loss_curves is True
        assert config.include_constraint_summary is True
        assert config.include_component_table is True
        assert config.include_validation_results is True

    def test_custom_config(self):
        config = ReportConfig(
            title="Custom Report",
            include_timestamp=False,
            board_chart_height=800,
            max_components_in_table=50,
        )
        assert config.title == "Custom Report"
        assert config.include_timestamp is False
        assert config.board_chart_height == 800
        assert config.max_components_in_table == 50


# ============================================================================
# Tests for ValidationResults
# ============================================================================


class TestValidationResults:
    """Tests for ValidationResults dataclass."""

    def test_default_initialization(self):
        results = ValidationResults()
        assert results.drc_passed is None
        assert results.drc_errors == []
        assert results.drc_warnings == []
        assert results.spice_passed is None
        assert results.spice_errors == []
        assert results.spice_warnings == []

    def test_with_drc_results(self):
        results = ValidationResults(
            drc_passed=False, drc_errors=["Error 1", "Error 2"], drc_warnings=["Warning 1"]
        )
        assert results.drc_passed is False
        assert len(results.drc_errors) == 2
        assert len(results.drc_warnings) == 1

    def test_with_spice_results(self):
        results = ValidationResults(
            spice_passed=True, spice_errors=[], spice_warnings=["Minor warning"]
        )
        assert results.spice_passed is True
        assert results.spice_errors == []
        assert len(results.spice_warnings) == 1


# ============================================================================
# Tests for generate_report
# ============================================================================


class TestGenerateReport:
    """Tests for generate_report function."""

    def test_minimal_report(self, sample_board):
        """Test generating report with minimal inputs."""
        html = generate_report(board_view=sample_board)

        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
        assert "Placement Optimization Report" in html
        assert len(html) > 1000  # Reasonable size

    def test_report_contains_html_structure(self, sample_board):
        """Test that report has proper HTML structure."""
        html = generate_report(board_view=sample_board)

        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

    def test_report_contains_summary_section(self, sample_board):
        """Test that report contains summary statistics."""
        html = generate_report(board_view=sample_board)

        assert "Summary" in html
        assert "3" in html  # 3 components
        assert "100.0" in html or "100" in html  # Board width

    def test_report_with_loss_history(self, sample_board, sample_history):
        """Test report includes loss curve section."""
        html = generate_report(board_view=sample_board, loss_history=sample_history)

        assert "Loss Curves" in html or "loss" in html.lower()

    def test_report_with_constraints(self, sample_board, sample_constraints):
        """Test report includes constraint summary."""
        html = generate_report(board_view=sample_board, constraints=sample_constraints)

        assert "Constraint" in html
        assert "Overlap" in html or "overlap" in html

    def test_report_with_validation_results(self, sample_board, sample_validation):
        """Test report includes validation section."""
        html = generate_report(board_view=sample_board, validation=sample_validation)

        assert "Validation" in html
        assert "DRC" in html
        assert "SPICE" in html

    def test_report_with_all_sections(
        self, sample_board, sample_history, sample_constraints, sample_validation
    ):
        """Test full report with all sections."""
        html = generate_report(
            board_view=sample_board,
            loss_history=sample_history,
            constraints=sample_constraints,
            validation=sample_validation,
        )

        assert "Summary" in html
        assert "Constraint" in html
        assert "Validation" in html
        assert len(html) > 5000  # Should be substantial

    def test_custom_title(self, sample_board):
        """Test report with custom title."""
        config = ReportConfig(title="My Custom Report Title")
        html = generate_report(board_view=sample_board, config=config)

        assert "My Custom Report Title" in html

    def test_no_timestamp(self, sample_board):
        """Test report without timestamp."""
        config = ReportConfig(include_timestamp=False)
        html = generate_report(board_view=sample_board, config=config)

        # Timestamp format pattern shouldn't appear
        assert 'class="timestamp"' not in html

    def test_disable_sections(self, sample_board, sample_history, sample_constraints):
        """Test disabling specific sections."""
        config = ReportConfig(
            include_board_view=False,
            include_loss_curves=False,
            include_constraint_summary=False,
            include_component_table=False,
        )
        html = generate_report(
            board_view=sample_board,
            loss_history=sample_history,
            constraints=sample_constraints,
            config=config,
        )

        # Should still have summary but not the disabled sections
        assert "Summary" in html

    def test_component_table_truncation(self, sample_board):
        """Test component table truncation for large designs."""
        config = ReportConfig(max_components_in_table=2)
        html = generate_report(board_view=sample_board, config=config)

        # Should mention truncation (3 components, limit 2)
        assert "Showing first" in html or "2 of 3" in html

    def test_write_to_file(self, sample_board):
        """Test writing report to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_report.html"

            html = generate_report(board_view=sample_board, output_path=str(output_path))

            # File should exist
            assert output_path.exists()

            # Content should match
            file_content = output_path.read_text()
            assert file_content == html

    def test_html_escaping(self, sample_board):
        """Test that special characters are properly escaped."""
        config = ReportConfig(title="Test <script>alert('XSS')</script>")
        html = generate_report(board_view=sample_board, config=config)

        # Script tag should be escaped
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# ============================================================================
# Tests for component table generation
# ============================================================================


class TestComponentTable:
    """Tests for component table generation."""

    def test_component_table_content(self, sample_board):
        """Test that component table contains correct data."""
        html = generate_report(board_view=sample_board)

        # Check component refs are present
        assert "U1" in html
        assert "R1" in html
        assert "C1" in html

        # Check positions (should contain coordinate values)
        assert "20.00" in html or "20.0" in html  # U1 x position
        assert "30.00" in html or "30.0" in html  # U1 y position

    def test_component_status_classes(self):
        """Test that status classes are applied to components."""
        board = BoardView(
            width=100.0,
            height=80.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10, 10),
                    rotation=0,
                    width=5,
                    height=5,
                    status=ComponentStatus.OK,
                ),
                ComponentView(
                    ref="U2",
                    position=Point(50, 50),
                    rotation=0,
                    width=5,
                    height=5,
                    status=ComponentStatus.ERROR,
                ),
            ),
        )
        html = generate_report(board_view=board)

        # Status classes should be in the HTML
        assert "status-ok" in html or "ok" in html.lower()
        assert "status-error" in html or "error" in html.lower()


# ============================================================================
# Tests for constraint section
# ============================================================================


class TestConstraintSection:
    """Tests for constraint summary section."""

    def test_no_violations_message(self, sample_board):
        """Test message when there are no violations."""
        constraints = ConstraintStatus()
        html = generate_report(board_view=sample_board, constraints=constraints)

        # Should indicate no violations
        assert "No constraint violations" in html or "0" in html

    def test_violations_listed(self, sample_board, sample_constraints):
        """Test that violations are listed."""
        html = generate_report(board_view=sample_board, constraints=sample_constraints)

        # Should show violation details
        assert "U1" in html  # Component refs from violation
        assert "overlapping" in html.lower() or "overlap" in html.lower()


# ============================================================================
# Tests for validation section
# ============================================================================


class TestValidationSection:
    """Tests for validation results section."""

    def test_drc_passed(self, sample_board):
        """Test DRC passed display."""
        validation = ValidationResults(drc_passed=True, drc_errors=[], drc_warnings=[])
        html = generate_report(board_view=sample_board, validation=validation)

        assert "PASSED" in html
        assert "DRC" in html

    def test_drc_failed(self, sample_board):
        """Test DRC failed display."""
        validation = ValidationResults(
            drc_passed=False, drc_errors=["Track too narrow"], drc_warnings=[]
        )
        html = generate_report(board_view=sample_board, validation=validation)

        assert "FAILED" in html
        assert "Track too narrow" in html

    def test_spice_results(self, sample_board):
        """Test SPICE validation display."""
        validation = ValidationResults(
            spice_passed=True, spice_errors=[], spice_warnings=["Minor issue"]
        )
        html = generate_report(board_view=sample_board, validation=validation)

        assert "SPICE" in html
        assert "Minor issue" in html


# ============================================================================
# Tests for CSS and styling
# ============================================================================


class TestStyling:
    """Tests for report CSS and styling."""

    def test_css_included(self, sample_board):
        """Test that CSS styles are included."""
        html = generate_report(board_view=sample_board)

        assert "<style>" in html
        assert "</style>" in html

    def test_color_variables(self, sample_board):
        """Test that CSS variables are defined."""
        html = generate_report(board_view=sample_board)

        assert "--color-primary" in html
        assert "--color-success" in html
        assert "--color-error" in html

    def test_responsive_styles(self, sample_board):
        """Test that responsive styles are included."""
        html = generate_report(board_view=sample_board)

        assert "@media" in html
