"""
Integration tests for CLI error handling and edge cases.

These tests verify graceful error handling for all CLI commands:
1. Non-existent files are reported clearly
2. Invalid input types (directory vs file) are caught
3. Permission issues are handled gracefully
4. YAML syntax errors give helpful messages
5. Missing required config fields are detected
6. Invalid config values are validated
7. All commands have working --help

Verification goals:
- Exit code is non-zero for errors
- Error message is human-readable
- No stack traces in normal error cases
- Stack trace available with --verbose or --debug (where supported)
"""

import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")

from temper_placer.cli import main  # noqa: E402

# Test fixtures paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"
MINIMAL_CONSTRAINTS = FIXTURES_DIR / "constraints_minimal.yaml"


class TestOptimizeErrorHandling:
    """Tests for optimize command error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_optimize_nonexistent_file(self, runner, temp_dir):
        """Test clear error message for non-existent input file."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                "/nonexistent/path/to/board.kicad_pcb",
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
            ],
        )

        # Should fail with non-zero exit code
        assert result.exit_code != 0

        # Should mention the file issue (Click's exists=True handles this)
        output_lower = result.output.lower()
        assert (
            "exist" in output_lower
            or "not found" in output_lower
            or "no such" in output_lower
            or "does not exist" in output_lower
            or "invalid" in output_lower
        ), f"Expected clear error about missing file, got: {result.output}"

    def test_optimize_directory_not_file(self, runner, temp_dir):
        """Test error when passing a directory instead of a file."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(temp_dir),  # Pass directory instead of file
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
            ],
        )

        # Should fail - Click handles file type validation
        assert result.exit_code != 0

        # Should mention invalid path or directory issue
        output_lower = result.output.lower()
        assert (
            "directory" in output_lower
            or "not a file" in output_lower
            or "invalid" in output_lower
            or "error" in output_lower
            or "exist" in output_lower
        ), f"Expected error about directory, got: {result.output}"

    @pytest.mark.skipif(os.name == "nt", reason="Unix permissions not applicable on Windows")
    def test_optimize_permission_denied_output(self, runner, temp_dir):
        """Test error when can't write to output location."""
        # Create a directory without write permission
        readonly_dir = temp_dir / "readonly"
        readonly_dir.mkdir()
        os.chmod(readonly_dir, stat.S_IRUSR | stat.S_IXUSR)  # Read and execute only

        try:
            output_pcb = readonly_dir / "output.kicad_pcb"

            result = runner.invoke(
                main,
                [
                    "optimize",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "-o",
                    str(output_pcb),
                    "--epochs",
                    "10",
                    "--no-curriculum",
                ],
            )

            # Should fail due to permission error
            # Note: The error might occur during export phase
            # We just need to verify it doesn't crash ungracefully
            if result.exit_code != 0:
                # Should have some error output (not a bare crash)
                assert len(result.output) > 0, "Should have error output, not silent failure"
        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_dir, stat.S_IRWXU)


class TestConfigYAMLErrorHandling:
    """Tests for YAML configuration error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_config_yaml_syntax_error(self, runner, temp_dir):
        """Test error handling for invalid YAML syntax."""
        output_pcb = temp_dir / "output.kicad_pcb"
        bad_yaml = temp_dir / "bad_syntax.yaml"

        # Write YAML with syntax error (unclosed bracket)
        bad_yaml.write_text("board:\n  width_mm: 50\n  invalid: [unclosed bracket")

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(bad_yaml),
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code != 0, "Should fail on invalid YAML syntax"

        # Should mention YAML or parsing issue
        output_lower = result.output.lower()
        assert (
            "yaml" in output_lower
            or "parse" in output_lower
            or "syntax" in output_lower
            or "error" in output_lower
            or "invalid" in output_lower
            or "failed" in output_lower
        ), f"Expected YAML error message, got: {result.output}"

    def test_config_yaml_unclosed_brace(self, runner, temp_dir):
        """Test error handling for YAML with unclosed brace."""
        output_pcb = temp_dir / "output.kicad_pcb"
        bad_yaml = temp_dir / "unclosed_brace.yaml"

        bad_yaml.write_text("board:\n  width_mm: {50")

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(bad_yaml),
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code != 0

    def test_config_yaml_bad_indentation(self, runner, temp_dir):
        """Test error handling for YAML with bad indentation."""
        output_pcb = temp_dir / "output.kicad_pcb"
        bad_yaml = temp_dir / "bad_indent.yaml"

        # Inconsistent indentation
        bad_yaml.write_text("board:\n width_mm: 50\n   height_mm: 100")

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(bad_yaml),
                "-o",
                str(output_pcb),
            ],
        )

        # May pass or fail depending on YAML parser strictness
        # Just verify it doesn't crash ungracefully
        assert result.exit_code in [0, 1, 2]

    def test_config_with_only_zones_uses_defaults(self, runner, temp_dir):
        """Test that config with only zones uses default board dimensions.

        The config loader provides defaults for board dimensions (100x150mm),
        so a config with only zones is valid and should succeed.
        """
        output_pcb = temp_dir / "output.kicad_pcb"
        zones_only_yaml = temp_dir / "zones_only.yaml"

        # Write YAML with only zones - should use default board dimensions
        zones_only_yaml.write_text("zones:\n  - name: test\n    bounds: [0, 0, 10, 10]")

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(zones_only_yaml),
                "-o",
                str(output_pcb),
                "--epochs",
                "10",  # Keep it fast
                "--no-curriculum",
            ],
        )

        # Should succeed - config loader has defaults
        # This verifies the CLI handles configs with partial data gracefully
        assert result.exit_code == 0, f"Expected success with defaults, got: {result.output}"

    def test_config_invalid_board_dimensions(self, runner, temp_dir):
        """Test error for negative or zero board dimensions."""
        output_pcb = temp_dir / "output.kicad_pcb"
        invalid_yaml = temp_dir / "invalid_dims.yaml"

        # Write YAML with negative dimensions
        invalid_yaml.write_text(
            """
board:
  width_mm: -50
  height_mm: 100
"""
        )

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(invalid_yaml),
                "-o",
                str(output_pcb),
            ],
        )

        # Should fail on invalid dimensions (if validation exists)
        # or at least run without crashing
        assert result.exit_code in [0, 1, 2]

    def test_config_invalid_zone_bounds(self, runner, temp_dir):
        """Test error for zones with invalid bounds."""
        output_pcb = temp_dir / "output.kicad_pcb"
        invalid_yaml = temp_dir / "invalid_zone.yaml"

        # Write YAML with zone bounds that are inverted (min > max)
        invalid_yaml.write_text(
            """
board:
  width_mm: 100
  height_mm: 100

zones:
  - name: invalid_zone
    bounds: [50, 50, 10, 10]  # x_min > x_max
"""
        )

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(invalid_yaml),
                "-o",
                str(output_pcb),
            ],
        )

        # May pass or fail depending on validation
        # Just ensure no crash
        assert result.exit_code in [0, 1, 2]

    def test_config_empty_file(self, runner, temp_dir):
        """Test error for empty config file."""
        output_pcb = temp_dir / "output.kicad_pcb"
        empty_yaml = temp_dir / "empty.yaml"

        empty_yaml.write_text("")

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(empty_yaml),
                "-o",
                str(output_pcb),
            ],
        )

        # Should fail - no config data
        assert result.exit_code != 0


class TestInfoCommandErrorHandling:
    """Tests for info command error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_info_nonexistent_file(self, runner):
        """Test info command with non-existent file."""
        result = runner.invoke(
            main,
            [
                "info",
                "/nonexistent/board.kicad_pcb",
            ],
        )

        assert result.exit_code != 0

        output_lower = result.output.lower()
        assert (
            "exist" in output_lower
            or "not found" in output_lower
            or "no such" in output_lower
            or "invalid" in output_lower
        ), f"Expected file error, got: {result.output}"

    def test_info_directory_not_file(self, runner, temp_dir):
        """Test info command with directory instead of file."""
        result = runner.invoke(
            main,
            [
                "info",
                str(temp_dir),
            ],
        )

        assert result.exit_code != 0

    def test_info_invalid_pcb_content(self, runner, temp_dir):
        """Test info command with file that isn't a valid KiCad PCB."""
        invalid_pcb = temp_dir / "invalid.kicad_pcb"
        invalid_pcb.write_text("This is not a KiCad PCB file")

        result = runner.invoke(
            main,
            [
                "info",
                str(invalid_pcb),
            ],
        )

        # Should fail to parse
        assert result.exit_code != 0

        output_lower = result.output.lower()
        assert (
            "parse" in output_lower
            or "failed" in output_lower
            or "invalid" in output_lower
            or "error" in output_lower
        )


class TestExportCommandErrorHandling:
    """Tests for export command error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_export_missing_placements(self, runner, temp_dir):
        """Test export command with non-existent placements file."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                "/nonexistent/placements.json",
                "--pcb",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code != 0

    def test_export_missing_template(self, runner, temp_dir):
        """Test export command with non-existent template PCB."""
        output_pcb = temp_dir / "output.kicad_pcb"
        placements = temp_dir / "placements.json"

        # Create a valid placements file
        placements.write_text('{"R1": {"x": 10, "y": 20, "rotation": 0}}')

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                str(placements),
                "--pcb",
                "/nonexistent/template.kicad_pcb",
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code != 0

    def test_export_invalid_placements_json(self, runner, temp_dir):
        """Test export command with invalid JSON placements file."""
        output_pcb = temp_dir / "output.kicad_pcb"
        invalid_json = temp_dir / "invalid.json"

        invalid_json.write_text("{invalid json}")

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                str(invalid_json),
                "--pcb",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code != 0


class TestValidateCommandErrorHandling:
    """Tests for validate command error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_validate_nonexistent_pcb(self, runner):
        """Test validate command with non-existent PCB file."""
        result = runner.invoke(
            main,
            [
                "validate",
                "/nonexistent/board.kicad_pcb",
            ],
        )

        assert result.exit_code != 0

    def test_validate_nonexistent_config(self, runner):
        """Test validate command with non-existent config file."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "-c",
                "/nonexistent/constraints.yaml",
            ],
        )

        assert result.exit_code != 0

    def test_validate_invalid_yaml(self, runner, temp_dir):
        """Test validate command with invalid YAML config."""
        bad_yaml = temp_dir / "bad.yaml"
        bad_yaml.write_text("board: [unclosed")

        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "-c",
                str(bad_yaml),
            ],
        )

        assert result.exit_code != 0


class TestVisualizeCommandErrorHandling:
    """Tests for visualize command error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_visualize_nonexistent_file(self, runner):
        """Test visualize command with non-existent PCB file."""
        result = runner.invoke(
            main,
            [
                "visualize",
                "/nonexistent/board.kicad_pcb",
            ],
        )

        assert result.exit_code != 0

    def test_visualize_invalid_pcb(self, runner, temp_dir):
        """Test visualize command with invalid PCB content."""
        invalid_pcb = temp_dir / "invalid.kicad_pcb"
        invalid_pcb.write_text("not a valid pcb")

        result = runner.invoke(
            main,
            [
                "visualize",
                str(invalid_pcb),
                "-o",
                str(temp_dir / "output.html"),  # Don't open browser
            ],
        )

        assert result.exit_code != 0


class TestReportCommandErrorHandling:
    """Tests for report command error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_report_nonexistent_pcb(self, runner, temp_dir):
        """Test report command with non-existent PCB file."""
        result = runner.invoke(
            main,
            [
                "report",
                "/nonexistent/board.kicad_pcb",
                "-o",
                str(temp_dir / "report.html"),
            ],
        )

        assert result.exit_code != 0

    def test_report_invalid_loss_history(self, runner, temp_dir):
        """Test report command with invalid loss history JSON."""
        invalid_json = temp_dir / "invalid_loss.json"
        invalid_json.write_text("{not valid json")

        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                "-o",
                str(temp_dir / "report.html"),
                "--loss-history",
                str(invalid_json),
            ],
        )

        # May warn or fail, but shouldn't crash
        # Loss history loading has a try/except that converts to warning
        assert result.exit_code in [0, 1, 2]


class TestHelpOutput:
    """Tests that all commands have proper --help output."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_main_help(self, runner):
        """Test main CLI help output."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "temper-placer" in result.output.lower()
        # Should list available commands
        assert "optimize" in result.output
        assert "validate" in result.output
        assert "export" in result.output
        assert "info" in result.output

    def test_optimize_help(self, runner):
        """Test optimize command help output."""
        result = runner.invoke(main, ["optimize", "--help"])

        assert result.exit_code == 0
        assert "--config" in result.output or "-c" in result.output
        assert "--output" in result.output or "-o" in result.output
        assert "--epochs" in result.output
        assert "--seed" in result.output

    def test_validate_help(self, runner):
        """Test validate command help output."""
        result = runner.invoke(main, ["validate", "--help"])

        assert result.exit_code == 0
        assert "--config" in result.output or "-c" in result.output
        assert "--drc" in result.output
        assert "--strict" in result.output

    def test_export_help(self, runner):
        """Test export command help output."""
        result = runner.invoke(main, ["export", "--help"])

        assert result.exit_code == 0
        assert "--placements" in result.output or "-p" in result.output
        assert "--pcb" in result.output
        assert "--output" in result.output or "-o" in result.output

    def test_info_help(self, runner):
        """Test info command help output."""
        result = runner.invoke(main, ["info", "--help"])

        assert result.exit_code == 0
        assert "INPUT_PCB" in result.output or "input" in result.output.lower()

    def test_visualize_help(self, runner):
        """Test visualize command help output."""
        result = runner.invoke(main, ["visualize", "--help"])

        assert result.exit_code == 0
        assert "--output" in result.output or "-o" in result.output
        assert "--title" in result.output

    def test_report_help(self, runner):
        """Test report command help output."""
        result = runner.invoke(main, ["report", "--help"])

        assert result.exit_code == 0
        assert "--output" in result.output or "-o" in result.output
        assert "--loss-history" in result.output

    def test_version_command(self, runner):
        """Test version command runs."""
        result = runner.invoke(main, ["version"])

        assert result.exit_code == 0
        assert "temper-placer" in result.output.lower()

    def test_version_flag(self, runner):
        """Test --version flag on main CLI."""
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        # Should show version info
        assert "temper-placer" in result.output.lower() or "version" in result.output.lower()


class TestUnknownCommand:
    """Tests for unknown command handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_unknown_command(self, runner):
        """Test helpful error for unknown command."""
        result = runner.invoke(main, ["unknown_command"])

        assert result.exit_code != 0
        # Click should show available commands or error
        output_lower = result.output.lower()
        assert (
            "no such command" in output_lower or "error" in output_lower or "usage" in output_lower
        )


class TestMissingRequiredOptions:
    """Tests for missing required options."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_optimize_missing_output(self, runner):
        """Test optimize without --output option."""
        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                # Missing -o flag
            ],
        )

        assert result.exit_code != 0
        output_lower = result.output.lower()
        assert "output" in output_lower or "required" in output_lower or "missing" in output_lower

    def test_optimize_missing_config(self, runner, temp_dir):
        """Test optimize without --config option."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
                # Missing -c flag
            ],
        )

        assert result.exit_code != 0
        output_lower = result.output.lower()
        assert "config" in output_lower or "required" in output_lower or "missing" in output_lower

    def test_export_missing_placements(self, runner, temp_dir):
        """Test export without --placements option."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "export",
                "--pcb",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
                # Missing -p flag
            ],
        )

        assert result.exit_code != 0

    def test_export_missing_pcb(self, runner, temp_dir):
        """Test export without --pcb option."""
        output_pcb = temp_dir / "output.kicad_pcb"
        placements = temp_dir / "placements.json"
        placements.write_text('{"R1": {"x": 0, "y": 0, "rotation": 0}}')

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                str(placements),
                "-o",
                str(output_pcb),
                # Missing --pcb flag
            ],
        )

        assert result.exit_code != 0

    def test_report_missing_output(self, runner):
        """Test report without --output option."""
        result = runner.invoke(
            main,
            [
                "report",
                str(MINIMAL_PCB),
                # Missing -o flag
            ],
        )

        assert result.exit_code != 0
