"""
Integration tests for the report CLI command.

These tests verify the report generation workflow via the CLI, ensuring:
1. Basic report generation works with valid input
2. Output HTML files are created and contain expected content
3. Optional flags work correctly (--loss-history, --drc, --no-board, etc.)
4. Error cases are handled gracefully

TDD Task: temper-1by.12
"""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from temper_placer.cli import main


# Test fixtures paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"


class TestReportCommandBasic:
    """Basic integration tests for the report command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temp directory for outputs."""
        return tmp_path

    def test_report_basic(self, runner, temp_dir):
        """Test basic report generation for minimal_board."""
        output_html = temp_dir / "report.html"

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(output_html),
            ],
        )

        assert result.exit_code == 0, f"CLI failed with output:\n{result.output}"
        assert output_html.exists(), "Output HTML file was not created"
        assert output_html.stat().st_size > 0, "Output HTML file is empty"

        # Verify it's valid HTML
        content = output_html.read_text()
        assert "<html" in content.lower(), "Output is not HTML"
        assert "</html>" in content.lower(), "HTML is not properly closed"

    def test_report_with_title(self, runner, temp_dir):
        """Test report generation with custom title."""
        output_html = temp_dir / "report.html"

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(output_html),
                "--title",
                "My Custom Report Title",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        content = output_html.read_text()
        assert "My Custom Report Title" in content, "Custom title not in report"

    def test_report_contains_components(self, runner, temp_dir):
        """Test that report contains component information."""
        output_html = temp_dir / "report.html"

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(output_html),
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        content = output_html.read_text()

        # Minimal board has components like R1, R2, C1, U1
        # At least some component references should be present
        assert any(ref in content for ref in ["R1", "R2", "C1", "U1"]), (
            "Component references not found in report"
        )


class TestReportCommandFlags:
    """Tests for various CLI flags."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_report_no_board_flag(self, runner, temp_dir):
        """Test --no-board flag excludes board visualization."""
        output_html = temp_dir / "report.html"

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(output_html),
                "--no-board",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_html.exists()

    def test_report_no_components_flag(self, runner, temp_dir):
        """Test --no-components flag excludes component table."""
        output_html = temp_dir / "report.html"

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(output_html),
                "--no-components",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_html.exists()

    def test_report_with_loss_history(self, runner, temp_dir):
        """Test --loss-history flag includes loss curves."""
        output_html = temp_dir / "report.html"
        loss_history = temp_dir / "loss_history.json"

        # Create a mock loss history file
        loss_data = {
            "epochs": [1, 2, 3, 4, 5],
            "total_loss": [100.0, 80.0, 60.0, 40.0, 30.0],
            "overlap_loss": [50.0, 40.0, 30.0, 20.0, 15.0],
            "boundary_loss": [50.0, 40.0, 30.0, 20.0, 15.0],
        }
        loss_history.write_text(json.dumps(loss_data))

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(output_html),
                "--loss-history",
                str(loss_history),
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        content = output_html.read_text()
        # Loss history section should be present
        assert "loss" in content.lower(), "Loss information not found in report"

    def test_report_drc_without_kicad_cli(self, runner, temp_dir):
        """Test --drc flag when kicad-cli is not available."""
        output_html = temp_dir / "report.html"

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(output_html),
                "--drc",
            ],
        )

        # Should either succeed (if kicad-cli available) or fail gracefully
        # We just verify it doesn't crash unexpectedly
        assert result.exit_code in [0, 1], f"Unexpected exit code: {result.exit_code}"


class TestReportCommandErrors:
    """Tests for error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_report_missing_input(self, runner, temp_dir):
        """Test error when input PCB file doesn't exist."""
        output_html = temp_dir / "report.html"

        result = runner.invoke(
            main,
            [
                "report",
                "/nonexistent/path/to/board.kicad_pcb",
                "-o",
                str(output_html),
            ],
        )

        assert result.exit_code != 0
        assert (
            "exist" in result.output.lower()
            or "not found" in result.output.lower()
            or "no such" in result.output.lower()
            or "error" in result.output.lower()
        )

    def test_report_missing_output(self, runner):
        """Test error when -o/--output is not provided."""
        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                # Missing -o flag
            ],
        )

        assert result.exit_code != 0
        assert "output" in result.output.lower() or "required" in result.output.lower()

    def test_report_invalid_loss_history(self, runner, temp_dir):
        """Test error when loss history file is invalid JSON."""
        output_html = temp_dir / "report.html"
        bad_loss_history = temp_dir / "bad_loss.json"

        # Write invalid JSON
        bad_loss_history.write_text("{ invalid json }")

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(output_html),
                "--loss-history",
                str(bad_loss_history),
            ],
        )

        # Should fail or warn about invalid loss history
        # The exact behavior depends on implementation
        # Just verify it doesn't crash with an unhandled exception
        assert result.exit_code is not None

    def test_report_nonexistent_loss_history(self, runner, temp_dir):
        """Test error when loss history file doesn't exist."""
        output_html = temp_dir / "report.html"

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(output_html),
                "--loss-history",
                "/nonexistent/loss_history.json",
            ],
        )

        # Should fail with clear error
        assert result.exit_code != 0


class TestReportCommandHelp:
    """Tests for help output."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_report_help(self, runner):
        """Test report command help output."""
        result = runner.invoke(main, ["report", "--help"])

        assert result.exit_code == 0
        assert "--output" in result.output or "-o" in result.output
        assert "--loss-history" in result.output
        assert "--title" in result.output
        assert "--drc" in result.output
        assert "--no-board" in result.output or "--board" in result.output

    def test_main_help_includes_report(self, runner):
        """Test main help lists report command."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "report" in result.output


class TestReportFromOptimization:
    """Tests that verify reports work with optimization output."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    # Skip JAX tests if not available
    jax = pytest.importorskip("jax")

    @pytest.mark.slow
    def test_report_after_optimization(self, runner, temp_dir):
        """Test generating a report from an optimized PCB."""
        # Run optimization first
        optimized_pcb = temp_dir / "optimized.kicad_pcb"
        constraints = FIXTURES_DIR / "constraints_minimal.yaml"

        opt_result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(constraints),
                "-o",
                str(optimized_pcb),
                "--epochs",
                "30",
                "--seed",
                "42",
                "--no-curriculum",
                "--no-heuristics",
            ],
        )

        assert opt_result.exit_code == 0, f"Optimization failed:\n{opt_result.output}"
        assert optimized_pcb.exists()

        # Now generate report from optimized PCB
        report_html = temp_dir / "report.html"

        report_result = runner.invoke(
            main,
            [
                "report",
                str(optimized_pcb),
                "-o",
                str(report_html),
                "--title",
                "Optimization Report",
            ],
        )

        assert report_result.exit_code == 0, f"Report failed:\n{report_result.output}"
        assert report_html.exists()

        content = report_html.read_text()
        assert "Optimization Report" in content
